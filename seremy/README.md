# SEREMY local implementation

Start the local application from the repository root containing the seremy package.

~~~powershell
python -B -m seremy.server --port 8765
~~~

Open http://127.0.0.1:8765. Choose a local folder, a ZIP archive or an HTTPS Git URL. Analysis progress appears on the page. The resulting draft offers a source map, documentation, graph JSON and validation results.

For the included mixed-language example, enter the full path to seremy/fixtures/local-demo. To explore the recorded Redux source, enter the full path to seremy/fixtures/redux-slice. The map supports file/symbol search, source-region selection, relationship navigation, Back, folder collapse, pointer zoom and minimap navigation.

## Runtime

Python 3.12 or newer and Node 22 are required for the local profile. Install Node dependencies with npm ci from seremy/tools. TypeScript is pinned to 5.9.3 in both package files and checked by the adapter. The parser uses a TypeScript Program and TypeChecker over frozen source inputs. Python uses the standard-library AST with a separately identified static lexical/module profile.

The tests require pytest. Browser checks require the Playwright dependency and an installed compatible Chromium browser. Set CHROME_BIN if using a separately installed executable.

## Command-line use

From the repository root:

~~~powershell
python -B -m seremy analyze seremy/fixtures/local-demo --output .seremy-artifacts
python -B -m seremy analyze seremy/fixtures/redux-slice --output .seremy-artifacts
python -B -m seremy analyze --zip C:/path/source.zip --output .seremy-artifacts
python -B -m seremy analyze --git-url https://github.com/owner/repo --revision main --output .seremy-artifacts
~~~

The output contains versions/<content-digest>/map.html, architecture.md, document-ir.json, graph.json, validation.json and manifest.json. Read current.json to find the most recent completed draft. An interrupted or failed analysis retains the previous pointer. Repeated identical content can reuse a verified immutable directory. A draft has explicit profile and coverage information. Full product acceptance remains a separate process.

Use the graph query command for a typed shortest path:

~~~powershell
python -B -m seremy path --graph .seremy-artifacts/versions/DIGEST/graph.json --from-id ENTITY_ID --to-id ENTITY_ID
~~~

The result supplies static edge witnesses, zero-depth results, no-path and truncated states. The default query follows bound CALLS edges. History edges and hypotheses do not enter the default factual path.

## Current stage behavior

| Stage | Implemented profile |
|---|---|
| S01 | Git tracked plus nonignored enumeration, or a bounded plain-folder walk with explicit directory exclusions. Content hashes and skipped reads are retained. |
| S02 | Python functions/classes/imports/calls and TypeScript declarations/imports/call candidates, with original UTF-8 source positions and parse-failure records. |
| S03 | TypeScript symbol/alias binding with a direct root tsconfig, and Python lexical/module binding. A supported direct call targets an observed function implementation. Unsupported dynamic targets retain explicit outcomes. |
| S04 | Exact dependency declarations in every observed package.json and pyproject.toml project.dependencies. Registry-scoped import syntax is independently labelled. Failed manifests and unregistered dependencies are recorded. |
| S05 | Directory membership and nearest observed package membership with versioned mappings and unassigned records. |
| S06 | Typed component aggregation preserving distinct edge IDs and source-site counts, bounded shortest paths and cycle membership. |
| S07 | Snapshot/source/evidence checks, candidate conservation, framework-input and membership/view consistency, optional forbidden-boundary/cycle rules, and exact template-claim checks after generation. |
| S08 | A cited document model and Markdown explanations for declarations, relationships, framework evidence, structural components and coverage. The map and document read the same graph bundle. |

The source map lays out the observed files by nested directory and renders code at reading scale. Rendering culls off-screen source lines. Folders collapse independently. Below scale 0.5, source occurrences are grouped by visible file or folder and relationship kind, with counts in group tooltips. The relationship picker retains every occurrence, and the selected occurrence receives an exact source-to-target overlay. Source-result update streaming, GPU comparison, representative performance qualification and comprehensive accessibility remain further viewer work.

The framework registry currently names React, Preact, Express, Next.js, Vue, Svelte, Django, FastAPI, Flask and SQLAlchemy. A declaration means the manifest declares a dependency. A source import means import syntax was observed. Routes, DI, ORM relations and runtime behavior require separately qualified rule profiles.

## Boundaries and budgets

The initial file profile selects lowercase .ts, .py, .json and .toml paths. Git scope uses the tracked and nonignored file universe. The plain-folder profile applies named directory exclusions and reports pruned subtrees. General plain-folder gitignore parity and file-replacement races across supported platforms remain qualification work.

The initial scan reads up to 5,000 enumerated entries, 1 MiB per file and 64 MiB in total. Skipped source inputs remain visible. Archive extraction has a 5,000-entry, 1 MiB-per-file and 64 MiB-total limit. The browser upload limit is 10 MiB compressed. Unsafe paths, duplicate paths, device paths and archive symlinks are rejected. Embedded Git metadata is skipped and archive discovery uses plain-folder scope. Archive identity uses the original ZIP hash so repeated imports have stable graph identities. Input Git commands disable filesystem-monitor hooks, templates and inherited Git configuration. Git acquisition uses a shallow HTTPS clone, a 120-second timeout and optional branch/tag selection. The automated tests cover local Git scope and ZIP extraction. A live remote-host clone has not been exercised for this release.

TypeScript member calls, callable values, anonymous default-function destinations, type-only aliases, declaration-only destinations and multi-project tsconfig extends/references have explicit unsupported or failed outcomes in the current profile. Python binding supports direct lexical and imported module-function calls. Captured pattern variables are treated as values with unknown call targets. Runtime reassignment, decorators changing call targets, wildcard imports and dynamic object dispatch require additional analysis. Lambda-body destinations remain unsupported. Semantic components, architectural layers, history analysis and optional LLM generation retain independent profiles and qualification work.

Cancellation is cooperative between analysis stages. A compiler process or Git clone already in progress returns before cancellation is observed. The local server binds to loopback and checks request Host/Origin. It is a single-user local launcher.

## Verification

~~~powershell
python -B -m pytest -q -p no:cacheprovider seremy/tests
node seremy/tools/check-product-map.cjs PUBLICATION_DIRECTORY EVIDENCE_DIRECTORY
node seremy/tools/check-launcher.cjs EVIDENCE_DIRECTORY
~~~

The product browser check expects the included full Redux source publication. The launcher check uses the mixed-language example. Browser evidence is stored separately from immutable publication contents. The earlier build_slice.py/check-map.cjs commands remain the two-file regression lane.

The current implementation receipt records executed test counts and source hashes. The original 40 stage acceptance cases, the map research acceptance cases, historical benchmark judgments, independent semantic evaluation, publication fault qualification and representative performance budgets retain their own statuses. The current automated checks establish the scoped local profile.

Earlier milestone receipts remain in the original local checkout. Use the repository README and docs/review-fixes.md for the current entry points and verification record.

