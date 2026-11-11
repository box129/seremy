# Review fixes

The independent review on 11 November 2026 reproduced thirteen defects in the initial local implementation. The corrections are covered by product-level Python regressions and browser checks.

| Finding | Correction and regression |
|---|---|
| Input-selected Git command execution | Input Git commands discard inherited Git configuration and disable filesystem monitors and hooks. ZIP ingestion strips embedded Git metadata and uses plain-folder discovery. A harmless test monitor cannot create its marker through the folder entry point. |
| Multiple Python imports crash | Each alias retains its own original source span and module identity. `import math, os as operating` conserves two distinct candidate records. |
| Anonymous TypeScript default export crashes | The binder records an explicit unsupported identity outcome and continues the scan. |
| Module-level calls crash documentation | File callers use their typed endpoint. Their source directories participate in structural relationship views and forbidden-boundary checks. |
| Python pattern captures create false targets | Named, sequence, mapping, and rest captures shadow global functions. Unknown callable values retain unsupported outcomes. |
| Type-only aliases create factual calls | The compiler adapter follows the alias chain and rejects runtime targets through type-only imports or re-exports. |
| Parse failures reported as successful parses | The document counts complete, partial, failed, and unprocessed source files. Metadata is excluded from the source-file denominator. Stage 7 checks the counts and the final coverage label. Older saved bundles can still generate their coverage labels from stored file outcomes. |
| Framework names conflated across ecosystems | Registry entries and import usage are matched within npm or Python. Collocated manifests have distinct package identities and source membership. |
| Incorrect membership passes validation | Directory and package membership is checked against observed paths and manifests. Re-sealed incorrect mappings fail validation. |
| Corrupt manifests reused | Republishing verifies the stored manifest and every artifact. Corruption retains the previous pointer. Concurrent identical publication reuses verified content. |
| Repeated ZIP imports change identity | The original ZIP hash supplies a stable logical repository identity. The CLI reuses the same version for repeated imports. |
| High-line-count source breaks the map | Layout computes source width iteratively. Chromium opens the function on line 160001 of an input inside the 1 MiB budget. |
| Map confuses edges with source sites | The map reports distinct relationships and source occurrences separately. Redux displays 25 relationships across 30 source sites. |

Verification completed on Windows with Python 3.14, Node 22.20.0, TypeScript 5.9.3, pytest 9.1.1, and Chromium 158.0.8127.18. All **130 Python tests passed**. The seven Redux navigation checks, five local-launcher checks, and two review browser checks also passed.

The Python run includes 19 review regression cases. The launcher exercises a mixed Python/TypeScript repository through the local HTTP application. Browser evidence and generated test publications are excluded from Git. A compact verification receipt records the checked source hashes.

The original research acceptance register has 40 cases awaiting execution under its own requirements. Semantic components, advanced framework semantics, dynamic dispatch, nested folder controls, visual edge aggregation, accessibility qualification, representative performance, and live remote Git ingestion retain their separate implementation or qualification work. Anonymous default-function destinations have a safe unsupported outcome in this profile.
