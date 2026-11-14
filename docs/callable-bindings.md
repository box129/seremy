# Callable bindings and lexical ownership

14 November 2026. Current script analyses use `typescript-callable-checker-v0.1` on pinned TypeScript 5.9.3. Python retains its separately identified AST binder. Mixed snapshots report `mixed-callable-static-v0.1`.

## Supported scope

The binder resolves direct identifier calls to function implementations, named `const` arrow/function-expression values, and immutable aliases through identifiers or imported namespace members. It also resolves namespace calls such as `helpers.run()` through the actual compiler export binding. Type-only imports do not supply runtime targets. Alias traversal is bounded to 128 symbols and cycles have explicit outcomes.

Named function expressions have source identities, including returned functions. Ordinary identifier-named method bodies also have identities. Those identities allow calls *inside* a method to be attributed to its body; they do not establish that an instance/object method call dispatches to that body. A const function expression with an inner name uses the variable identity once, including for self recursion.

The captured snapshot is the complete compiler input universe. Targets require valid parsed declarations, exact file hashes and independently cross-checked UTF-16/UTF-8 source spans. No source package is executed or installed. The binder rejects observed identifier/destructuring/loop assignments and namespace-member writes. Direct eval/with in source or target files prevents acceptance within this profile. Semantic type diagnostics are not run.

## Explicit limits

- Callback argument propagation, event/framework invocation and runtime execution are not inferred. `onClick={handler}` does not create `App CALLS handler`.
- Parameter targets, mutable `let`/`var` callables, conditional/dynamic initializers, factory-return destinations, mutable object/instance methods, computed receivers and optional calls remain outside this target profile.
- Anonymous callable bodies and unsupported owner regions can retain a resolved target **at file level**. They are not attributed to an enclosing creator function. The parser records `source_owner_reason: lexical_callable_owner_not_identified`; map inspection, guide text and MCP context preserve that qualification.
- External modules remain external, unavailable relative/path-mapped modules remain missing, invalid syntax cannot supply accepted targets, and complex tsconfig project graphs retain the previous acquisition limits.
- General dynamic mutation or whole-program runtime correctness is not established by these static observations.

## Consumer behavior

New declarations use `callable_declaration`, `function_expression` or `method_declaration`, with genuine source name spans. The parsing record identifies the extension in `construct_coverage.binding_extension`; S03 stores the actual binder profile and outcomes. The source-language universes remain separately versioned. Low-level adapters default to the prior binder unless explicitly requested; the product analyzer defaults to the new extension. `analyze(root, callable_bindings=False)` retains the frozen legacy comparison lane.

The graph retains CALLS relationship/site conservation and separate module dependency counts. When an owner is unknown, `source_type=file_ref` and the owning file replace a fabricated enclosing function. The portable viewer and local MCP expose the owner reason. Method/returned-function regions remain source identities even when no incoming invocation is established.

Developer guide v0.4 adds a named-callable section with source citations, observed outgoing targets and incoming-site counts. Zero incoming static calls explicitly do not establish that a callback is unused. Existing model-assisted draft tools receive these claims through the same snapshot-bound section contexts. Independent architectural-prose usefulness and semantic acceptance remain open.

## Evidence and verification

- `seremy/fixtures/callable-slice/truth.json` is an independently written six-site truth set. It covers a named event callback's body, immutable namespace alias, imported re-export, namespace member call and function-expression recursion. The forbidden `App → onClick` invocation stays absent.
- Negative cases cover mutable values, callback parameters, object receivers, conditional values, reassignment, loop assignments, namespace-member writes, type-only namespaces, optional calls, alias cycles/depth, external imports and dynamic scope. Unicode/BOM/CRLF spans and legacy mode have separate checks.
- Ownership cases verify returned functions and method bodies, anonymous-body file fallback, portable map metadata, guide disclosure and actual MCP context.
- Final full Python suite: **281 passed** in 219.01 seconds.
- On the same Redux fixture, the legacy profile has 25 relationships / 30 bound sites; this profile has 29 / 34. All 30 previously bound sites retain the same targets, four additional sites resolve, and creator/body ownership is corrected. New regions are `randomString`, `combination`, `unsubscribe` and the observable's `subscribe` method. Module dependencies remain 38 distinct / 39 sites.
- Local browser checks exercise alias and namespace target navigation, the named-callable guide and explicit owner qualification. Release receipts and screenshots are stored in the chat's `outputs/SEREMY-Callable-Bindings` folder.

The Redux count comparison is a same-input profile comparison, not a general accuracy score or a controlled CodeCanvas benchmark. Earlier verification receipts retain their recorded profiles and counts.

## Next implementation work

1. Use the richer graph and existing MCP draft/review workflow to prepare and independently evaluate architectural explanations on representative repositories. Human/free-prose usefulness is not certified by template or citation checks.
2. Add the bounded FastAPI route-evidence profile already planned in the stage ledger, supplying explicit framework source semantics for explanations and grouping.
3. Qualify snapshot-contained tsconfig inheritance/project references and larger full-repository acquisition.
4. Treat callback-argument flow, object receiver dispatch and broader runtime semantics as separate profiles with independent truth cases.
