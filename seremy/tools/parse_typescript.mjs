// S02 syntax parser adapter for the SEREMY Milestone 1 slice.
//
// Uses the TypeScript compiler API (pinned in package.json) to extract
// declaration records and syntax reference candidates with exact source
// ranges.  TypeScript positions are UTF-16 code-unit offsets; the SEREMY
// contract (v1.1 addendum) requires zero-based UTF-8 byte offsets against
// the AnalysisTextBlob.  This adapter therefore emits BOTH the binder-native
// UTF-16 ranges and the normalized byte ranges, under the declared
// identity-utf8-v1 position map (original UTF-8 sources only).
//
// Usage:
//   node parse_typescript.mjs <rootDir> <filesJsonPath>
// filesJsonPath contains {"files": ["src/utils/isAction.ts", ...]} with
// repository-relative POSIX paths.  Output is a JSON document on stdout.
//
// Construct profile (declared): function_declaration, class_declaration,
// import_specifier, import_name, call, member_call.  Unhandled statement
// kinds are counted, never silently dropped.

import * as ts from "typescript";
import { createSnapshotProgram } from "./compiler_binding.mjs";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve, posix, sep } from "node:path";

const PROFILE_ID = "seremy-m1-profile-v0.1";
const PRODUCER = "seremy.parse_typescript/0.1";
const POSITION_MAP = "identity-utf8-v1";

const [, , rootArg, filesArg] = process.argv;
if (!rootArg || !filesArg) {
  console.error("usage: node parse_typescript.mjs <rootDir> <filesJsonPath>");
  process.exit(2);
}

const root = resolve(rootArg);
const { files } = JSON.parse(readFileSync(filesArg, "utf-8"));
const snapshotProgram = createSnapshotProgram(root, files);

// UTF-16 code-unit index -> UTF-8 byte offset table for one text.
// Surrogate pairs occupy two UTF-16 units and four UTF-8 bytes.
function buildUtf16ToByteMap(text) {
  const map = new Int32Array(text.length + 1);
  let byteOffset = 0;
  for (let i = 0; i < text.length; ) {
    map[i] = byteOffset;
    const code = text.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff) {
      map[i + 1] = byteOffset; // low surrogate shares the code point's bytes
      byteOffset += 4;
      i += 2;
    } else {
      byteOffset += utf8Length(code);
      i += 1;
    }
  }
  map[text.length] = byteOffset;
  return map;
}

function utf8Length(code) {
  if (code < 0x80) return 1;
  if (code < 0x800) return 2;
  if (code < 0x10000) return 3;
  return 4; // unreachable for lone BMP units handled above
}

function countUtf16Units(text) {
  // Total UTF-16 code units (== text.length) — recorded for cross-checks.
  return text.length;
}

const decoderFatal = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });

function rangeToUtf16(node, sourceFile) {
  return [node.getStart(sourceFile), node.getEnd()];
}

function utf16ToByte(map, range) {
  const [start, end] = range;
  const bytes = [map[start], map[end]];
  return bytes;
}

function identifierRecord(kind, name, node, sourceFile, map, extra = {}) {
  const utf16 = rangeToUtf16(node, sourceFile);
  return {
    kind,
    name,
    utf16,
    byte: utf16ToByte(map, utf16),
    ...extra,
  };
}

function extractFile(relPath) {
  const absolute = resolve(root, relPath);
  const raw = snapshotProgram.inputs.get(absolute).raw;
  const contentSha256 = createHash("sha256").update(raw).digest("hex");
  const base = {
    file_id: relPath.split(sep).join("/"),
    content_sha256: contentSha256,
    byte_count: raw.length,
  };

  let text;
  try {
    text = decoderFatal.decode(raw);
  } catch (error) {
    return {
      ...base,
      decode: { status: "failed", reason: "not_utf8" },
      parse_diagnostics: [],
      declarations: [],
      candidates: [],
      construct_coverage: { extracted_counts: {}, unhandled_statement_kinds: {} },
    };
  }

  const map = buildUtf16ToByteMap(text);
  const sourceFile = snapshotProgram.program.getSourceFile(absolute);

  const declarations = [];
  const candidates = [];
  const extractedCounts = {};
  const unhandled = {};

  const bump = (counts, key) => {
    counts[key] = (counts[key] ?? 0) + 1;
  };

  const visit = (node) => {
    if (ts.isFunctionDeclaration(node) && node.name) {
      bump(extractedCounts, "function_declaration");
      const nameNode = node.name;
      const nameUtf16 = rangeToUtf16(nameNode, sourceFile);
      const declUtf16 = rangeToUtf16(node, sourceFile);
      declarations.push({
        kind: "function_declaration",
        name: nameNode.text,
        name_utf16: nameUtf16,
        name_byte: utf16ToByte(map, nameUtf16),
        decl_utf16: declUtf16,
        decl_byte: utf16ToByte(map, declUtf16),
      });
      node.parameters.forEach(visit);
      if (node.body) visit(node.body);
      return;
    }
    if (ts.isClassDeclaration(node) && node.name) {
      bump(extractedCounts, "class_declaration");
      const nameNode = node.name;
      const nameUtf16 = rangeToUtf16(nameNode, sourceFile);
      const declUtf16 = rangeToUtf16(node, sourceFile);
      declarations.push({
        kind: "class_declaration",
        name: nameNode.text,
        name_utf16: nameUtf16,
        name_byte: utf16ToByte(map, nameUtf16),
        decl_utf16: declUtf16,
        decl_byte: utf16ToByte(map, declUtf16),
      });
      ts.forEachChild(node, visit);
      return;
    }
    if (ts.isImportDeclaration(node)) {
      bump(extractedCounts, "import_declaration");
      const specifier = node.moduleSpecifier;
      // The span addresses the string-literal node itself, so the record
      // name must be the raw literal text (quotes included).  The
      // unquoted module path is carried in module_path.
      candidates.push(
        identifierRecord(
          "import_specifier",
          specifier.getText(sourceFile),
          specifier,
          sourceFile,
          map,
          { module_path: specifier.text }
        )
      );
      const clause = node.importClause;
      if (clause) {
        if (clause.name) {
          candidates.push(identifierRecord("import_name", clause.name.text, clause.name, sourceFile, map));
        }
        const named = clause.namedBindings;
        if (named && ts.isNamedImports(named)) {
          named.elements.forEach((element) => {
            candidates.push(
              identifierRecord(
                "import_name",
                element.name.text,
                element.name,
                sourceFile,
                map,
                { imported_as: (element.propertyName ?? element.name).text }
              )
            );
          });
        }
      }
      ts.forEachChild(node, visit);
      return;
    }
    if (ts.isCallExpression(node)) {
      bump(extractedCounts, "call_expression");
      const callUtf16 = rangeToUtf16(node, sourceFile);
      const expression = node.expression;
      if (ts.isIdentifier(expression)) {
        candidates.push(
          identifierRecord("call", expression.text, expression, sourceFile, map, {
            binding: snapshotProgram.bind(sourceFile, node, (text, range) => utf16ToByte(buildUtf16ToByteMap(text), range)),
            arg_count: node.arguments.length,
            call_utf16: callUtf16,
            call_byte: utf16ToByte(map, callUtf16),
          })
        );
      } else if (ts.isPropertyAccessExpression(expression)) {
        candidates.push(
          identifierRecord(
            "member_call",
            expression.name.text,
            expression.name,
            sourceFile,
            map,
            {
              binding: snapshotProgram.bind(sourceFile, node, (text, range) => utf16ToByte(buildUtf16ToByteMap(text), range)),
            arg_count: node.arguments.length,
              receiver_unbound: true,
              call_utf16: callUtf16,
              call_byte: utf16ToByte(map, callUtf16),
            }
          )
        );
      } else {
        bump(extractedCounts, "call_expression_other_callee");
      }
      node.arguments.forEach(visit);
      visit(expression);
      return;
    }
    if (
      ts.isIdentifier(node) ||
      ts.isTokenKind(node.kind) ||
      node.kind === ts.SyntaxKind.SourceFile
    ) {
      ts.forEachChild(node, visit);
      return;
    }
    // Anything not specially handled: counted as unhandled for coverage
    // visibility, then traversed so nothing is silently dropped.
    bump(unhandled, ts.SyntaxKind[node.kind] ?? String(node.kind));
    ts.forEachChild(node, visit);
  };

  ts.forEachChild(sourceFile, visit);

  const parseDiagnostics = sourceFile.parseDiagnostics.map((diagnostic) => {
    const start = diagnostic.start ?? 0;
    const end = start + (diagnostic.length ?? 0);
    return {
      message: ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n"),
      code: diagnostic.code,
      utf16: [start, end],
      byte: utf16ToByte(map, [start, end]),
    };
  });

  return {
    ...base,
    decode: {
      status: "ok",
      encoding: "utf-8",
      utf16_length: countUtf16Units(text),
    },
    parse_diagnostics: parseDiagnostics,
    declarations,
    candidates,
    construct_coverage: {
      extracted_counts: extractedCounts,
      unhandled_statement_kinds: unhandled,
    },
  };
}

const output = {
  profile: PROFILE_ID,
  producer: PRODUCER,
  position_map: POSITION_MAP,
  typescript_version: ts.version,
  declared_constructs: [
    "function_declaration",
    "class_declaration",
    "import_declaration",
    "call_expression",
    "member_call",
  ],
  files: files.map(extractFile),
};

process.stdout.write(JSON.stringify(output));
