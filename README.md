# SEREMY

SEREMY turns a source repository into a graph of observed declarations and static calls, a spatial source map, and cited Markdown documentation. The local pipeline has eight stages covering discovery, parsing, dependency resolution, framework evidence, structural components, relationship views, validation, and documentation.

The hosted entry point accepts repository ZIP uploads or public GitHub URLs and provides an interactive map, documentation and downloads. Visitors can save reports on their device and reopen them after server results expire. Its Docker image contains both language runtimes. See [hosted analysis](docs/hosted-analysis.md) for limits, device history, temporary server storage and deployment commands.

Lowercase `.py`, `.ts`, `.js`, `.jsx` and `.tsx` source is supported within the [versioned static language profiles](docs/ecmascript-profile.md). JSX tags retain explicit non-runtime outcomes; arrow/callable/member targets remain limited.

Python 3.12 or newer and Node.js 22 are required. The TypeScript compiler is pinned to 5.9.3. Python analysis uses the standard-library AST. Run these commands from this repository's root.

```powershell
npm ci --prefix seremy/tools
python -B -m seremy.server --port 8765
```

Open http://127.0.0.1:8765 and select a folder, ZIP archive, or HTTPS Git repository. Try the full path to `seremy/fixtures/local-demo` for the mixed Python/TypeScript example or `seremy/fixtures/redux-slice` for the recorded Redux source. The server binds to the local computer.

The command-line entry point writes an immutable draft and a current-version pointer.

```powershell
python -B -m seremy analyze seremy/fixtures/local-demo --output .seremy-artifacts
python -B -m seremy analyze --zip C:/path/source.zip --output .seremy-artifacts
```

The map, graph, documentation, and validation result are stored together under `.seremy-artifacts/versions/`. The map renders actual source in place as you zoom. Its repository tree expands folders and opens files. Select a call in source and choose Follow target to reach its declaration. Back restores selection, camera position, zoom, tree expansion, and tree scroll. The selected source region stays highlighted. File and symbol search, global canvas folder collapse, and a minimap are also available. Distinct relationships and source sites have separate counts. Compact controls keep search in the Find drawer (`/`). Source cards have bounded widths with horizontal reveal for long lines; call/declaration navigation and saved views retain per-file offsets. See [the compact source workspace](docs/compact-source-workspace.md).

Install the development dependency and run the Python regressions with the normal product entry points.

```powershell
python -m pip install -r requirements-dev.txt
python -B -m pytest -q -p no:cacheprovider seremy/tests
```

Browser checks use Playwright and Chromium. Install the browser once, generate a Redux publication, and pass its version directory to the checks. Set `CHROME_BIN` to use an existing Chromium executable.

```powershell
npx --prefix seremy/tools playwright install chromium
python -B -m seremy analyze seremy/fixtures/redux-slice --output .seremy-artifacts
node seremy/tools/check-product-map.cjs PUBLICATION_DIRECTORY test-results/map
node seremy/tools/check-navigation.cjs PUBLICATION_DIRECTORY test-results/navigation
node seremy/tools/check-nested-folders.cjs PUBLICATION_DIRECTORY test-results/nested-folders
node seremy/tools/check-retained-renderer.cjs PUBLICATION_DIRECTORY test-results/retained-renderer
node seremy/tools/check-overview.cjs SYNTHETIC_PUBLICATION_DIRECTORY test-results/overview
node seremy/tools/check-review-map.cjs PUBLICATION_DIRECTORY test-results/review-map
node seremy/tools/check-launcher.cjs test-results/launcher
```

The repository contains the standalone SEREMY implementation, fixtures, and tests. The original ArchDoc AI web application lives in the earlier local checkout. Third-party Redux fixture source retains its included MIT license.

Selecting a symbol or connection opens an evidence inspector with caller and target source excerpts. Inspect and Files toggle their panels without changing the camera. See [selection inspector](docs/selection-inspector.md).

The inspector filters incoming, outgoing and neighboring connections by the selected file. It shows relationship and source-site counts, recorded unresolved outcomes and enclosing parser declarations. See [dependency exploration](docs/dependency-exploration.md).

Arrange supports dragging files and folders, Shift selection, named visual groups and keyboard movement. The inspector switches layouts and saves a browser-local view for the current snapshot. Source breadcrumbs support directory navigation. See [arrangement and saved views](docs/arrangement.md).

The local launcher's MCP bridge lets an agent read selected evidence and documentation, focus source and add cited annotations. Install the optional SDK and connect a stdio client using [the MCP setup](docs/mcp.md).

SVG remains the default renderer. Inspect → Arrangement and saved view → Renderer offers a Pixi / WebGL preview using the same navigation, source highlighting, filters, arrangement and MCP controller. Saved views retain the renderer choice. The preview paints through WebGL while SVG supplies accessible elements and pointer targets; WebGL failure returns to SVG. See [the integration and checks](docs/pixi-integration.md).

The renderer qualification compares SVG and Pixi on Redux, a fixed 50,000-line fixture and real Pydantic source. Its first comparison used an isolated prototype. The integration is measured separately with the complete controller. The latest [scene-retention and texture-lifetime work](docs/scene-performance.md) adds stable neutral records, visible-file selection indexing and verified GPU resource release. See [renderer qualification](docs/renderer-qualification.md).

Canvas directories contain their child directories and source files. Use a directory heading to collapse or expand it independently. Enter and Space also activate a focused heading. Following a call opens its target ancestors, and Back restores the previous canvas folder state. Collapsed folders show their source file count and receive boundary endpoints for relationships to hidden files.

Files longer than 180 lines show an 80-line preview. Expand full file reveals the remaining source. Search and call navigation reveal lines beyond the preview automatically. Back restores the folded state.

At readable source zoom the SVG renderer reuses unchanged scene nodes and removes offscreen source content. Below scale 0.5, the overview groups source occurrences by visible file or collapsed folder and relationship kind. Group tooltips report occurrence counts. Selecting a group inspects its first source site, and the relationship picker exposes every individual occurrence. The selected occurrence receives an exact source-to-target overlay. Coarse source previews share one SVG path per file. Unselected relationships outside the viewport are culled using their curve bounds. See [the overview measurements](docs/overview-renderer.md).

Outputs remain scoped drafts. Direct calls have qualified language profiles. Unsupported dynamic targets retain explicit outcomes. Semantic component detection, architectural layers, route/DI/ORM rules, comprehensive accessibility and broader renderer/hardware qualification remain implementation work. See [the detailed profile](seremy/README.md) and [the fix record](docs/review-fixes.md).

The map now exposes the active profile, parse limits, exclusions and resolution coverage through Coverage. Empty and unsupported-only repositories have explicit guidance. See the [feature ledger, eight-stage boundaries and next implementation task](docs/implementation-readiness.md).

Files now has per-file and subtree visibility checkboxes, a visible/total count and Restore all. Hidden sources remain searchable and evidence stays intact; navigation reveals targets, while Back and saved views restore visibility. See [file visibility and working sets](docs/file-visibility.md).
