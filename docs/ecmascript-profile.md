# JavaScript, JSX and TSX static profile

The product entry points now include lowercase `.js`, `.jsx` and `.tsx` source alongside `.ts` and `.py`. Selection, parsing, direct-call binding, coverage, documentation and map navigation are qualified under the boundaries below. This profile does not infer a React component tree or runtime behavior from JSX syntax.

## Identities and compatibility

| Layer | Extended profile |
|---|---|
| Discovery and S02/S03 contract | `seremy-ecmascript-static-v0.1` |
| Connected product/bundle/validation/publication | `seremy-local-ecmascript-v0.1` |
| Script binding observations | `typescript-ecmascript-checker-v0.1` |
| Mixed Python/script binding roster | `mixed-ecmascript-static-v0.1` |

The extended profile is selected when the enumerated, non-excluded source universe contains a lowercase `.js`, `.jsx` or `.tsx` path. Discovery still records skipped input and byte-limit reasons. A declared extended input that cannot be read does not silently downgrade the remaining parser/binder stages. The declared stage profile is passed explicitly, including when only TS/Python inputs remain readable or no source is processed.

TS/Python-only repositories retain the prior discovery policy, profile IDs and binding observations. Existing bundles load without mutation. A fresh analysis of the stored 17-file Redux fixture was compared with its pre-change bundle: the entire graph document, manifest identity, S02/S03 artifacts and canonical digest `e812a13f976ee861824a68a9d6a24717783849eec29501483d005458c48aa289` are unchanged. Its repository/digest view key is unchanged, so existing saved working sets remain compatible. Adding an extended-language source changes the snapshot/profile and appropriately gives the new graph its own saved-view identity.

## Frozen compiler route

TypeScript **5.9.3** remains pinned and checked at runtime. The compiler host reads only frozen, selected source files and the pinned standard libraries. Unselected disk files and repository dependencies cannot provide declarations. Repository code, plugins and build commands are not executed.

| Extension | Explicit script kind |
|---|---|
| `.ts` | TS |
| `.js` | JS |
| `.jsx` | JSX |
| `.tsx` | TSX |

The extended compiler program enforces `allowJs: true`, `checkJs: false`, `jsx: Preserve` and `noEmit: true` after converting the direct root tsconfig options. Other supported root options, such as path aliases, remain captured in the observation context. The raw config hash, compiler version/options, selected source hashes and script kinds are recorded. Multi-project `extends`/`references` are explicitly rejected; this is not a build-system or project-reference resolver.

The [allowJs](https://www.typescriptlang.org/tsconfig/allowJs.html), [JSX emit modes](https://www.typescriptlang.org/tsconfig/jsx.html) and [noEmit](https://www.typescriptlang.org/tsconfig/noEmit.html) references describe those compiler options. SEREMY does not call emit or inspect lowered JSX calls. Its tests also verify that analysis leaves source files unchanged.

The pinned parser accepts JSX syntax in `.js` as well as `.jsx`/`.tsx`; `.ts` retains TS grammar. Extended parsing uses compiler syntactic diagnostics, including illegal TS annotations in JS. Invalid syntax is partial; invalid UTF-8 is failed. Original UTF-8 bytes, BOM, Unicode and CRLF positions are independently cross-checked against compiler UTF-16 spans. Semantic type diagnostics are not run. A complete record means syntax extraction within this profile, not type correctness or complete architectural understanding.

## Direct-call and JSX semantics

Supported relationships have a direct identifier callee and an observed, named function declaration with a body in the frozen program. Renamed imports, re-export aliases and root-config aliases use checker symbols rather than filename suffix matching. Named function-style JSX components are ordinary declarations; an explicit `App()` can be a call, while `<App/>` remains a JSX observation.

Opening/self-closing JSX tag names produce `jsx_tag` candidates with exact source spans. Their S03 outcome is `NOT_PROCESSED`, reason `jsx_runtime_semantics_outside_profile`, and `attempted: false`. Tag names do not create `CALLS`, component, route, hook or data-flow edges. Expression calls inside JSX can bind when their lexical source owner and target meet the direct-function profile.

The extended source owner must be an observed named function declaration or module-level scope. Arrow callbacks, function-expression/method/class-initializer owners remain `UNSUPPORTED` with `source_owner_not_established`; they are not silently attributed to an enclosing component function. Direct identifier calls to callable values or type-only/declaration-only/anonymous destinations, and simple property member calls, retain explicit unsupported outcomes. Other callee shapes, such as computed members and immediately invoked expressions, remain counted in syntax coverage; v0.1 does not fully enumerate them as S03 candidates or create resolved edges from them. CommonJS module acquisition, additional script extensions (`.mjs`, `.cjs`, `.mts`, `.cts`), source maps and runtime framework interpretation are not qualified by this release.

A conservative whole-snapshot write scan rejects directly reassigned lexical bindings, including destructuring writes, as `binding_reassigned_in_snapshot`. It does not establish control-flow-sensitive runtime targets. Shadowed parameter writes and property writes on a function do not replace that function's lexical binding; the compiler's auxiliary JS expando identifiers are handled separately. This remains static binding evidence, not an execution trace or proof against arbitrary runtime mutation.

## Consumers and validation

All source-file denominators include the five supported source extensions. S02 and S03 artifact/profile digests remain cross-bound to the same frozen inventory. JSX tags count as candidates without inflating call-binding attempts or relationships. The document IR, publication manifest, map and Coverage panel expose the actual profile. The older profile still describes older exports; current input guidance lists the supported lowercase extensions.

Config changes invalidate an extended snapshot even when it has only JSX observations and no call binding. Source/dependency/policy checks and the post-generation template checks still run. Documentation remains cited templates; this release does not qualify generated LLM prose.

## Independent qualification

`seremy/fixtures/ecmascript-slice/truth.json` specifies three relationships, three JSX tags and six limiting outcomes independently of the extractor. Five sources include JS aliases/re-exports, a TSX function component, a JSX function component, a Unicode-prefixed target and external/missing/member/callable/reassigned/callback cases. There must be no `App → Child` relationship from the `<Child/>` tag.

The 25 added Python cases cover that exact truth, actual script kinds/options, BOM/Unicode/CRLF, JS grammar and parse failures, invalid encoding, forced flags/config aliases, frozen input isolation, direct/destructuring writes, property/parameter false positives, callback ownership, mixed Python/script input, legacy flags, skipped extended inputs, config staleness, unsupported multi-project config and publication identity.

The connected browser journey runs both renderers in Edge and Chromium: real folder/ZIP analysis, exact graph truth, TSX-to-JS target/Back, Unicode glyph alignment, hidden target reveal, cited documentation/downloads, JSX/non-bound outcome inspection and saved working sets after map reload or hosted page refresh. Historical core suites are rerun separately. See [execution metadata](ecmascript-verification.json) for completed counts and rollout details.

```powershell
python -B -m pytest -q -p no:cacheprovider seremy/tests/test_ecmascript_profile.py
node seremy/tools/check-ecmascript.cjs test-results/ecmascript
```

An optional second argument to the browser script targets the hosted app and submits the fixture as a ZIP. SVG remains default; browser engine, device and broader semantic/performance acceptance retain their separate scope.
