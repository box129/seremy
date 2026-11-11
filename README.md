# SEREMY

SEREMY turns a source repository into a graph of observed declarations and static calls, a spatial source map, and cited Markdown documentation. The local pipeline has eight stages covering discovery, parsing, dependency resolution, framework evidence, structural components, relationship views, validation, and documentation.

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

The map, graph, documentation, and validation result are stored together under `.seremy-artifacts/versions/`. The map renders actual source in place as you zoom. Its repository tree expands folders and opens files. Select a call in source and choose Follow target to reach its declaration. Back restores selection, camera position, zoom, tree expansion, and tree scroll. The selected source region stays highlighted. File and symbol search, global canvas folder collapse, and a minimap are also available. Distinct relationships and source sites have separate counts.

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
node seremy/tools/check-review-map.cjs PUBLICATION_DIRECTORY test-results/review-map
node seremy/tools/check-launcher.cjs test-results/launcher
```

The repository contains the standalone SEREMY implementation, fixtures, and tests. The original ArchDoc AI web application lives in the earlier local checkout. Third-party Redux fixture source retains its included MIT license.

Canvas directories contain their child directories and source files. Use a directory heading to collapse or expand it independently. Enter and Space also activate a focused heading. Following a call opens its target ancestors, and Back restores the previous canvas folder state. Collapsed folders show their source file count and receive boundary endpoints for relationships to hidden files.

Outputs remain scoped drafts. Direct calls have qualified language profiles. Unsupported dynamic targets retain explicit outcomes. Semantic component detection, architectural layers, route/DI/ORM rules, comprehensive accessibility, edge aggregation, and representative performance qualification remain implementation work. See [the detailed profile](seremy/README.md) and [the fix record](docs/review-fixes.md).
