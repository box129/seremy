# Renderer qualification

Qualification on 12 November 2026 compared SVG and a PixiJS 8.22.0 prototype on the same graph, source, layout and camera. Three paired trials used 20 wheel and selection samples per mode. Chromium 158.0.8127.18 used the laptop's Intel UHD Direct3D11 adapter. Fixed canvas dimensions were 1440×800. JavaScript heap measurements exclude GPU textures. Results are specific to this hardware and browser.

| Workload | Renderer | Map ready median, s | Overview handler p95, ms | Source handler p95, ms | Source interaction-frame p95, ms | Selection handler p95, ms | JS heap median, MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| Redux | SVG | 0.27 | 9.2 | 17.7 | 50 | 7.5 | 5.7 |
| Redux | PIXI | 0.80 | 11.4 | 17.8 | 16.7 | 6.9 | 9.4 |
| Synthetic | SVG | 0.68 | 34.7 | 43 | 150 | 187.7 | 10.7 |
| Synthetic | PIXI | 1.31 | 40.6 | 37 | 33.4 | 30.3 | 29.9 |
| Pydantic 2.14.3 | SVG | 2.58 | 31.3 | 44.8 | 99.97 | 56.5 | 21.1 |
| Pydantic 2.14.3 | PIXI | 5.85 | 40.8 | 18.5 | 16.7 | 13.4 | 27.4 |

The source-view prototype supports real byte-range selection, target navigation, Back and collapsed folders. It renders plain text and a reduced control set. Production syntax coloring, rich inspection, filters, minimap, arrangement, saved views and MCP remain part of the Pixi port.

The production SVG viewer now caches repeated glyph measurements and avoids reading dropdown selection inside candidate-search callbacks. Its all-files picker preserves its options across source-file selection. The controlled stress startup comparison changed from 18.13 s to 0.78 s. Source panning also suppresses native browser text selection. The current viewer remains SVG.

Pixi is the next migration target for large maps. Begin by removing forced layout from history capture, then extract a shared scene model and add a full-feature Pixi adapter alongside the SVG fallback. Profile Pixi startup and texture allocation on Pydantic before choosing the default. A compact-rail visual pass, bounded source-card framing and broader browser/hardware checks remain ahead.

The hosted application deployed commit `487ebbb` on 12 November 2026. Public checks verified ZIP analysis, documentation, downloads, refresh recovery, device history and the current inspector, filters and saved arrangements. The served HTML contains the performance corrections. Runtime error logs were clear during the verification window. Live MCP continues to use the local launcher.

All 155 Python tests and 65 browser cases passed. Browser journeys covered Redux, fixed stress data and the 106-file Pydantic package at 1440×900, 1280×800 and DPR 2. Historical CodeCanvas captures have an unrecorded revision and camera. The new reference source capture aligns file and viewport, with source-card framing differences documented.

Reproduce from the repository root.

```powershell
npm ci --prefix seremy/tools
python -B seremy/tools/prepare_qualification.py test-results/qualification PATH_TO_PYDANTIC_SOURCE
python -B -m seremy analyze seremy/fixtures/redux-slice --output .seremy-artifacts
node seremy/tools/qualify-renderers.cjs REDUX_PUBLICATION test-results/qualification test-results/qualification/comparison
node seremy/tools/qualify-workflow.cjs REDUX_PUBLICATION test-results/qualification test-results/qualification/workflow
```

`build_renderer_prototype.py` creates a portable Pixi experiment from an existing publication. `check-renderer-prototype.cjs` verifies shared geometry, exact source selection and navigation. Its optional fifth argument sets DPR. `measure-glyph-cache.cjs` compares startup against commit `dc1b014`. `diagnose-selection.cjs` splits native value assignment from change-handler work and records CPU profiles. Raw benchmark samples, screenshots and runnable experiments are saved in the local qualification deliverable.
