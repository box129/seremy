# Optional Pixi map renderer

The map now has an opt-in PixiJS 8.22.0 / WebGL preview. Open Inspect → Arrangement and saved view → Renderer to try it. SVG remains the default. A portable map also accepts `?renderer=pixi`. Save view includes the renderer preference; older saved views restore SVG. Missing WebGL, context loss and paint failures leave the map usable in SVG.

Both modes use the existing product controller for byte-range selection, target navigation, Back, search, tree expansion, collapse, long-file folding, filters, direction markers, minimap, group movement, layouts, saved views, keyboard actions and local MCP. The scene's geometry and UTF-8 position helpers live in `seremy/map/scene-model.js`. The isolated comparison builder reads that maintained asset instead of extracting controller source by substring boundaries.

The preview is an intermediate integration. `pixi-surface.js` retains Graphics and Text objects corresponding to the controller's SVG scene nodes. Pixi paints source syntax colors, cards, folders, labels, relationship arrows, selection and focus outlines. SVG remains the semantic and pointer-input layer, with its visible scene hidden while Pixi is active. The minimap and surrounding panels retain their existing DOM rendering. Consequently the preview keeps SVG update costs and adds GPU scene reconciliation and text textures. It does not yet establish a large-map speed improvement or full CodeCanvas visual parity.

The exporter embeds the pinned runtime in each map, for portable use without a CDN. It executes only when Pixi is requested. `npm ci --prefix seremy/tools` provides it; the Docker production install includes it. Without that package, Python-only SVG exports work and the Pixi option is disabled. The runtime increases the portable map's payload. GPU texture memory is outside the JavaScript heap measurements.

History capture and Save view now use the tree's scroll-event cache, avoiding a layout read during capture. A regression scrolls a genuinely constrained repository panel, follows a call and uses Back to check restoration. Moving that read removes the identified `save()` hotspot; total interaction latency still needs measurement because drawing and browser layout remain significant.

## Verification and reproduction

The Python regression suite passed all 155 tests. The same ten browser suites run in default SVG and with `SEREMY_RENDERER=pixi`. GPU-mode suites assert the actual Pixi engine, nonempty Graphics/Text objects and no GL error, covering 49 recorded case groups per renderer. The MCP suite uses a real stdio SDK client and two browser views. WebGL-specific checks read real nontransparent framebuffer pixels, switch renderers, restore saved renderer/camera state, deliberately lose a context and disable WebGL in a separate browser. The unchanged graph and source hashes remain the evidence authority.

```powershell
node seremy/tools/check-pixi-surface.cjs PUBLICATION_DIRECTORY test-results/pixi-surface
$env:SEREMY_RENDERER='pixi'
node seremy/tools/check-navigation.cjs PUBLICATION_DIRECTORY test-results/pixi-navigation
node seremy/tools/check-arrangement.cjs PUBLICATION_DIRECTORY test-results/pixi-arrangement
node seremy/tools/check-launcher.cjs test-results/pixi-launcher
node seremy/tools/check-mcp.cjs test-results/pixi-mcp
node seremy/tools/qualify-workflow.cjs REDUX_PUBLICATION test-results/qualification test-results/pixi-workflow
Remove-Item Env:SEREMY_RENDERER
node seremy/tools/qualify-product-renderers.cjs REDUX_PUBLICATION test-results/qualification test-results/product-comparison
```

The complete-product comparison uses three trials with 20 samples per mode on Redux, the fixed 100-file / 50,000-line / 5,000-site fixture and 106-file Pydantic 2.14.3. Both modes use identical geometry and cameras. It records startup, wheel handlers, selection dispatch, native dropdown assignment, frame scheduling proxies, DOM count, JavaScript heap and CPU profiles. First-trial synthetic selections include profiler overhead. These measurements describe this laptop and Chromium; they exclude GPU texture memory and do not measure compositor FPS. See the local `SEREMY-Pixi-Integration-Verification` deliverable for receipts, screenshots and raw results.

## Measured decision

Keep SVG as the default. The complete-product three-trial comparison on this laptop produced:

| Workload | Renderer | Ready median, s | Overview handler p95, ms | Source handler p95, ms | Selection handler p95, ms | JS heap median, MiB |
|---|---|---:|---:|---:|---:|---:|
| Redux | SVG | 0.36 | 10.1 | 22.7 | 8.5 | 6.2 |
| Redux | PIXI | 1.24 | 84.1 | 62.3 | 36.5 | 20.6 |
| Synthetic | SVG | 0.90 | 49.7 | 54.5 | 251.1 | 17.8 |
| Synthetic | PIXI | 1.99 | 315.8 | 106.2 | 333.5 | 36.0 |
| Pydantic | SVG | 2.97 | 57.7 | 66.4 | 57.5 | 23.0 |
| Pydantic | PIXI | 3.79 | 355.1 | 68.3 | 92.3 | 30.8 |

The history cache removes `save()` from the top sampled functions but did not improve total stress-selection latency in the repeated six-sample diagnosis. The remaining hotspot is controller `draw()`. The integrated preview retains SVG update costs; startup, overview and memory measurements do not support making it the default. Next, use renderer-neutral scene records, reuse overview objects and text textures, and quantify GPU allocation/release before repeating qualification.

## Hosted rollout

Runtime commit `e7fd16c` is live at https://seremy-analysis.onrender.com/ (12 November 2026, deploy `dep-dbr2imc9v7es73ehk3s0`). Public checks passed all five upload/download/history case groups in both default SVG and opt-in Pixi, with no page errors. The receipt records real Pixi objects and zero GL error. This hosted browser run used SwiftShader software WebGL; the timing benchmark used Intel UHD Direct3D11. Ten hosted groups are additional to 115 local browser groups. Runtime error logs were empty during the verification window. MCP remains local-launcher only.
