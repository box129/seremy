// Bind only snapshot inputs and TypeScript's pinned standard libraries.
import * as ts from "typescript";
import { readFileSync, existsSync, realpathSync } from "node:fs";
import { resolve, relative, dirname, isAbsolute } from "node:path";
import { createHash } from "node:crypto";

const hash = data => createHash("sha256").update(data).digest("hex");
export function createSnapshotProgram(root, fileIds, profile=null) {
  if (ts.version !== "5.9.3") throw new Error("unsupported TypeScript version: " + ts.version);
  if(profile!==null&&!['seremy-m1-profile-v0.1','seremy-ecmascript-static-v0.1'].includes(profile))throw new Error('unsupported source profile');
  const extended=profile==='seremy-ecmascript-static-v0.1'||fileIds.some(id=>/\.(js|jsx|tsx)$/.test(id));
  if(extended&&profile==='seremy-m1-profile-v0.1')throw new Error('extended source cannot use the legacy profile');
  const method=extended?"typescript-ecmascript-checker-v0.1":"typescript-checker-v0.2";
  const scriptKind=path=>path.endsWith('.tsx')?ts.ScriptKind.TSX:path.endsWith('.jsx')?ts.ScriptKind.JSX:path.endsWith('.js')?ts.ScriptKind.JS:ts.ScriptKind.TS;
  const inputs = new Map();
  for (const id of fileIds) {
    const path = resolve(root, id);
    const rel = relative(root, path);
    if (isAbsolute(rel) || rel.startsWith("..")) throw new Error("snapshot path escapes root");
    const actual = relative(realpathSync(root), realpathSync(path));
    if (isAbsolute(actual) || actual.startsWith("..")) throw new Error("snapshot link escapes root");
    inputs.set(path, { id, raw: readFileSync(path) });
  }
  const configPath = resolve(root, "tsconfig.json");
  let config = {}, configHash = null;
  if (existsSync(configPath)) {
    const actual = relative(realpathSync(root), realpathSync(configPath));
    if (isAbsolute(actual) || actual.startsWith("..")) throw new Error("tsconfig link escapes root");
    const raw = readFileSync(configPath);
    configHash = hash(raw);
    const parsed = ts.parseConfigFileTextToJson(configPath, raw.toString("utf8"));
    if (parsed.error) throw new Error("invalid tsconfig.json");
    config = parsed.config;
    // Multi-config acquisition needs its own versioned snapshot contract.
    if (config.extends || config.references) throw new Error("extends/references require a multi-project snapshot profile");
  }
  const optionsResult = ts.convertCompilerOptionsFromJson(config.compilerOptions || {}, root);
  if (optionsResult.errors.length) throw new Error(ts.formatDiagnosticsWithColorAndContext(optionsResult.errors, {
    getCanonicalFileName: p => p, getCurrentDirectory: () => root, getNewLine: () => "\n"
  }));
  const options = {
    target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler, strict: true,
    ...optionsResult.options, ...(extended?{allowJs:true,checkJs:false,jsx:ts.JsxEmit.Preserve}:{}), noEmit: true
  };
  const host = ts.createCompilerHost(options, true);
  const originalRead = host.readFile;
  const originalExists = host.fileExists;
  const libraryRoot = dirname(ts.getDefaultLibFilePath(options));
  const isLibrary = path => dirname(path) === libraryRoot && /^lib\..*\.d\.ts$/.test(path.split(/[\\/]/).at(-1));
  host.fileExists = path => inputs.has(resolve(path)) || (isLibrary(resolve(path)) && originalExists(path));
  host.readFile = path => {
    const input = inputs.get(resolve(path));
    if (input) return new TextDecoder("utf-8", {fatal:true, ignoreBOM:true}).decode(input.raw);
    return isLibrary(resolve(path)) ? originalRead(path) : undefined;
  };
  host.directoryExists = path => [...inputs.keys()].some(p => p.startsWith(resolve(path) + "/") || p.startsWith(resolve(path) + "\\"));
  host.getSourceFile = (path, languageVersion) => {
    let text;
    try { text = host.readFile(path); } catch { return undefined; }
    return text === undefined ? undefined : ts.createSourceFile(path, text, languageVersion, true, scriptKind(path));
  };
  host.realpath = path => path;
  const program = ts.createProgram([...inputs.keys()], options, host);
  const checker = program.getTypeChecker();
  const context = {
    method, typescript_version: ts.version,
    config_sha256: configHash,
    compiler_options: JSON.parse(JSON.stringify(options, (key,value) =>
      typeof value === "string" ? value.replaceAll(root,"$SNAPSHOT_ROOT").replaceAll(root.replaceAll("\\","/"),"$SNAPSHOT_ROOT") : value)),
    snapshot_files: [...inputs.values()].map(i => [i.id, hash(i.raw)]).sort()
  };
  if(extended)context.script_kinds=[...inputs.values()].map(i=>[i.id,ts.ScriptKind[scriptKind(i.id)]]).sort();
  const syntaxCache=new Map();
  function syntaxDiagnostics(source){
    if(!syntaxCache.has(source))syntaxCache.set(source,extended?program.getSyntacticDiagnostics(source):source.parseDiagnostics);
    return syntaxCache.get(source);
  }
  function unalias(symbol){
    const seen=new Set();
    while(symbol&&(symbol.flags&ts.SymbolFlags.Alias)&&!seen.has(symbol)){seen.add(symbol);symbol=checker.getImmediateAliasedSymbol(symbol);}
    return symbol;
  }
  const writtenSymbols=new Set();
  if(extended){
    const record=node=>{
      if(ts.isPropertyAccessExpression(node)||ts.isElementAccessExpression(node))return;
      if(ts.isIdentifier(node)){
        const symbol=ts.isShorthandPropertyAssignment(node.parent)?checker.getShorthandAssignmentValueSymbol(node.parent):checker.getSymbolAtLocation(node);
        if(symbol)writtenSymbols.add(unalias(symbol));
      }
      ts.forEachChild(node,record);
    };
    const visit=node=>{
      if(ts.isBinaryExpression(node)&&node.operatorToken.kind>=ts.SyntaxKind.FirstAssignment&&node.operatorToken.kind<=ts.SyntaxKind.LastAssignment)record(node.left);
      if((ts.isPrefixUnaryExpression(node)||ts.isPostfixUnaryExpression(node))&&[ts.SyntaxKind.PlusPlusToken,ts.SyntaxKind.MinusMinusToken].includes(node.operator))record(node.operand);
      ts.forEachChild(node,visit);
    };
    for(const path of inputs.keys()){const source=program.getSourceFile(path);if(source)visit(source);}
  }

  function bind(sourceFile, call, mapRange) {
    const missing = reason => ({ outcome: "MISSING", reason, context });
    if (syntaxDiagnostics(sourceFile).length) return {outcome:"UNSUPPORTED", reason:"syntax_diagnostics",context};
    if(extended)for(let parent=call.parent;parent&&!ts.isSourceFile(parent);parent=parent.parent){
      if(ts.isClassDeclaration(parent)||ts.isClassExpression(parent))return {outcome:"UNSUPPORTED",reason:"source_owner_not_established",context};
      if(ts.isFunctionLike(parent)){
        if(!ts.isFunctionDeclaration(parent)||!parent.name)return {outcome:"UNSUPPORTED",reason:"source_owner_not_established",context};
        break;
      }
    }
    const expression = call.expression;
    if (!ts.isIdentifier(expression)) return {outcome:"UNSUPPORTED",reason:"receiver_unbound_no_type_information",context};
    let symbol = checker.getSymbolAtLocation(expression);
    const importDeclaration = symbol?.declarations?.find(d => ts.isImportClause(d) || ts.isImportSpecifier(d));
    let importNode = importDeclaration;
    while (importNode && !ts.isImportDeclaration(importNode)) importNode = importNode.parent;
    const aliases = new Set();
    while (symbol && symbol.flags & ts.SymbolFlags.Alias) {
      if (aliases.has(symbol)) return {outcome:"UNSUPPORTED",reason:"alias_cycle",context};
      aliases.add(symbol);
      if (symbol.declarations?.some(d => ts.isTypeOnlyImportOrExportDeclaration(d))) {
        return {outcome:"UNSUPPORTED",reason:"type_only_alias_has_no_runtime_value",context};
      }
      symbol = checker.getImmediateAliasedSymbol(symbol);
    }
    // JS expando writes add the property's receiver identifier as an auxiliary
    // declaration. They do not replace the function's lexical binding.
    const declarations = (symbol?.declarations || []).filter(d=>!(extended&&ts.isIdentifier(d)&&
      (ts.isPropertyAccessExpression(d.parent)||ts.isElementAccessExpression(d.parent))&&d.parent.expression===d));
    if(extended&&writtenSymbols.has(symbol))return {outcome:"UNSUPPORTED",reason:"binding_reassigned_in_snapshot",context};
    if (!declarations.length) {
      const specifier = importNode?.moduleSpecifier?.text;
      const mapped = Object.keys(options.paths || {}).some(pattern => {
        const [prefix, suffix] = pattern.split("*");
        return suffix === undefined ? specifier === pattern : specifier?.startsWith(prefix) && specifier.endsWith(suffix);
      });
      if (specifier && !specifier.startsWith(".") && !mapped) {
        const module = checker.getSymbolAtLocation(importNode.moduleSpecifier);
        if (!module) return {outcome:"EXTERNAL",reason:"bare_specifier",target:specifier,context};
      }
      return missing(importNode ? "unresolved_import" : "no_binding_within_profile");
    }
    // Parameters, object values and callable interfaces do not prove runtime destinations.
    if (declarations.some(d => !ts.isFunctionDeclaration(d))) {
      return {outcome:"UNSUPPORTED",reason:"callable_value_target_not_established",context};
    }
    const bodies = declarations.filter(d => d.body);
    if (bodies.length > 1) return {outcome:"AMBIGUOUS",reason:"multiple_implementations",context};
    if (bodies.length === 0) return {outcome:"UNSUPPORTED",reason:"declaration_only_target",context};
    const declaration = bodies[0], targetSource = declaration.getSourceFile();
    if (!declaration.name) return {outcome:"UNSUPPORTED",reason:"anonymous_function_identity_not_supported",context};
    const input = inputs.get(resolve(targetSource.fileName));
    if (!input || syntaxDiagnostics(targetSource).length) return {outcome:"UNSUPPORTED",reason:"target_outside_valid_snapshot",context};
    return {
      outcome:"RESOLVED_SINGLE", context,
      target: { file_id:input.id, content_sha256:hash(input.raw), name:declaration.name.text,
        kind:"function_declaration", name_byte:mapRange(targetSource.text,[declaration.name.getStart(targetSource),declaration.name.end]) }
    };
  }
  function resolveModule(source, specifier) {
    const result={context,method:'typescript-module-resolution-v0.1'};
    if(syntaxDiagnostics(source).length)return {...result,outcome:'UNSUPPORTED',reason:'syntax_diagnostics'};
    const resolved=ts.resolveModuleName(specifier.text,source.fileName,options,host).resolvedModule;
    const input=resolved&&inputs.get(resolve(resolved.resolvedFileName));
    if(input){
      const target=program.getSourceFile(resolve(resolved.resolvedFileName));
      if(!target||syntaxDiagnostics(target).length)return {...result,outcome:'UNSUPPORTED',reason:'target_outside_valid_snapshot'};
      return {...result,outcome:'RESOLVED_SINGLE',target:{file_id:input.id,content_sha256:hash(input.raw)}};
    }
    const mapped=Object.keys(options.paths||{}).some(pattern=>{
      const [prefix,suffix]=pattern.split('*');return suffix===undefined?specifier.text===pattern:specifier.text.startsWith(prefix)&&specifier.text.endsWith(suffix);
    });
    return {...result,outcome:specifier.text.startsWith('.')||mapped?'MISSING':'EXTERNAL',reason:specifier.text.startsWith('.')||mapped?'module_not_in_snapshot':'external_module_not_loaded'};
  }
  return { inputs, program, context, bind, resolveModule, syntaxDiagnostics, extended };
}
