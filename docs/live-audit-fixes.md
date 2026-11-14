# Follow-up to the live CodeCanvas comparison

14 November 2026. This release addresses concrete failures found by interacting with the hosted application. It does not claim complete CodeCanvas parity or accepted architectural prose.

## Delivered behavior

| Audit finding | Change | Remaining boundary |
|---|---|---|
| Generic GitHub failure | Categorized worker errors for download size, unavailable repository/revision, public API refusal and network failure. The browser receives a fixed actionable message, never a raw subprocess traceback. Unsupported tsconfig project graphs have a specific diagnostic. | Whole-repository GitHub and ZIP uploads retain the 3 MiB compressed / 8 MiB extracted limits. GitHub now accepts an explicit source folder (for example src): up to 16 MiB is downloaded, then only that contained folder is extracted under the existing 8 MiB / 1 MiB-per-file / 1,000-entry bounds. The snapshot, guide and UI disclose this subset and that outer configuration was not used. This is not full-repository ingestion. |
| Disconnected imports/barrels/types | New compiler-resolved file dependency artifact, with IMPORTS, TYPE_IMPORTS, REEXPORTS and TYPE_REEXPORTS; included in the map, guide, exported graph, coverage and local MCP selection. | File-level static module edges, not symbol-reference completeness or runtime calls. Python modules, CommonJS/dynamic import, complex tsconfig graphs and callable-value targets remain outside the new profile. |
| Limited guide | Rendered headings, inline code, lists, tables, source links and a contents navigator. Low-level declaration/relationship/citation appendices collapse. Guide v0.3 adds module reading order, cited source-authored JSDoc descriptions and short observed static paths; repeated overload declarations are grouped for reading. | Comments are explicitly author-provided and unverified. Static paths are not execution traces. Semantic ownership, business-purpose synthesis and independent prose usefulness judgments still need the existing draft/review workflow. |
| Missing source search | File/symbol Find also searches source text, lists exact line previews and navigates to UTF-8 spans. Displays at most 100 match buttons and states when truncated. | Literal case-insensitive text search, not live LSP or arbitrary syntax selection. |
| Poor initial file framing | Opening a file fits the source card into canvas space left by the panels; exact-span navigation still opens the requested line. Focused previews retain source text at overview zoom within a bounded 180-line display budget. | Very large expanded files continue to use the coarse overview until zoomed in. |
| Narrow-window clipping | Wrapping header, accessible Downloads menu, wrapping rendered prose, and mutually exclusive side panels below 900 px. | Verified at 680 × 587; this is not general mobile/accessibility certification. |

## File dependency contract

`contents.module_dependencies` is separately versioned as `typescript-file-dependencies-v0.1`, with a digest, edges, explicit outcomes and coverage. The existing `contents.s03.artifact.edges` remains the direct-call graph, preserving the meaning of call metrics and independent call truth fixtures. Consumers must read the new artifact to obtain file dependencies.

Each resolved module edge stores source/target paths, exact source bytes, source/target blob hashes, relation kind, compiler method and candidate identity. Resolution uses TypeScript 5.9.3 against the captured in-memory source universe and pinned compiler options. Missing relative/path-mapped modules remain MISSING, bare unavailable packages are EXTERNAL, and invalid parse regions remain unsupported. No package code is executed or installed.

The analyzer opts into module extraction; the low-level legacy adapter remains available without that extension. Its construct coverage records the module profile when active. Post-generation graph validation rebuilds the dependency artifact from the bound parser observations, checking the artifact digest and coverage. Documentation validation includes module-artifact lineage and source citations. Local MCP registers module occurrences separately and returns their file-level semantics and citations.

## Verification

- Final full Python suite: 264 passed in 175.27 seconds, including source-folder containment, missing-folder and scope-disclosure cases.
- Final focused module/documentation/MCP suite: 41 passed, including real published module-selection context, document projection and tampered dependency rejection.
- Both inline controller scripts passed Node syntax compilation.
- Real GitHub import: Redux commit 0139377fc8eef33e28afc6e3e939df3f41f939a6, source folder src, completed through the normal GitHub importer. The original full archive measured 15,665,006 compressed bytes / 23,618,371 extracted bytes, largely images and lockfiles; increasing the original extraction limits blindly was avoided.
- Hands-on local and hosted-mode UI: real scoped GitHub import, Redux analysis, source text search and line navigation, guide rendering and citation navigation, outgoing file connections, file framing and narrow-window downloads. Browser error log was empty. A captured comment containing HTML and a javascript URL remained inert text (zero image elements and zero unsafe links).
- Redux fixture result: 17 source files, 25 distinct calls / 30 call sites, 38 distinct module dependencies / 39 module sites. `src/index.ts` outgoing view: 12 relationships / 13 sites, previously empty in the audit.
- `randomString`: four text matches; clicking the declaration reaches line 8.
- At 680 × 587 the document root had `scrollWidth === innerWidth === 680`.

These counts describe the fixture used in this run, not a same-commit accuracy comparison with CodeCanvas's live Redux import. Earlier qualification receipts retain their original scope. Screenshots and the release verification receipt are saved in the chat's `outputs/SEREMY-Live-Audit-Fixes` folder.

## Next work

1. Qualify larger full-repository ingestion and snapshot-contained tsconfig inheritance/references without silently dropping configuration. The explicit source-folder path solves a bounded subset workflow, not these broader cases.
2. Extend callable-value/symbol binding with independent alias, reassignment and callback truth cases.
3. Use module structure, source descriptions and reviewed MCP drafts to build and independently judge actual architectural explanations. More prose is not an acceptance criterion.
4. Continue the previously planned bounded FastAPI route-evidence profile and renderer/accessibility qualification.
