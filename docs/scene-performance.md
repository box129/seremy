# Retained scene and texture lifetime

The controller now emits maintained renderer-neutral records through `seremy/map/scene-records.js`. SVG is the semantic and pointer-input adapter. Pixi consumes record identities, attributes, styles, text and children directly; it no longer traverses and reads the SVG scene to reconstruct its paint objects. Both overview and readable source modes retain records and native nodes. Geometry and selected-state changes update existing records instead of making their entire attribute set the cache identity.

Source selection sites are deduplicated and indexed by file once per snapshot. Each draw inspects the visible files' sites. Caller and outcome lookups use the same first-match semantics through indexes. This avoids reconstructing and scanning every declaration/call span on every frame. Evidence spans, graph data and source text retain their original values.

Pixi shares `TextStyle` instances, caches measured widths with an 8,192-entry bound, and quantizes label stroke arithmetic so inverse-camera rounding does not invalidate unchanged text textures. Stable overview camera updates retain Graphics/Text objects and uploaded textures. Evicted objects are destroyed; after each eviction, idle pooled textures are cleared after rendering, allowing current-frame reuse while releasing unused GPU storage. Switching to SVG releases the GPU scene and idle textures. Re-enabling Pixi rebuilds from the current records and navigation state.

The implementation still maintains SVG semantics and input geometry. It is not a GPU-only renderer or complete CodeCanvas parity. The controls, minimap, inspection, keyboard navigation, saved views and local MCP still use the existing controller. SVG remains the default pending broader renderer/browser qualification.

## Resource verification

`check-scene-resources.cjs` instruments actual WebGL texture allocation, upload and deletion calls independently of Pixi internals. On Redux, synthetic stress and Pydantic, repeated overview zoom leaves node/object creation, text-update and texture-upload counters unchanged. Keyboard source focus, target navigation and Back remain usable. Panning files offscreen releases their allocations; switching to SVG leaves only two built-in 1×1 RGBA textures in these runs.

The resource figures estimate tracked RGBA8 texture-level storage from width, height and explicit mip levels. They exclude buffers, non-RGBA8 formats, driver overhead and the framebuffer. They are not total VRAM readings. Resource instrumentation is separate from the timing run, so its accounting work does not inflate the benchmark samples. Idle text storage is released eagerly; revisiting evicted source can incur fresh upload work.

The complete regression suite passed 155 Python tests. The ten browser suites passed 49 case groups per renderer, including real local MCP clients and saved-view recovery. The full Pixi workflow passed nine workload/viewport/DPR cases, and six fallback/resource-surface groups passed. Twelve additional allocation/lifetime groups cover the three workloads. Browser case groups contain multiple assertions and are not independent unit-test counts.

Reproduce from the repository root:

```powershell
node seremy/tools/check-scene-resources.cjs PUBLICATION_DIRECTORY test-results/scene-resources
$env:SEREMY_RENDERER='pixi'
node seremy/tools/qualify-workflow.cjs REDUX_PUBLICATION test-results/qualification test-results/pixi-workflow
Remove-Item Env:SEREMY_RENDERER
node seremy/tools/qualify-product-renderers.cjs REDUX_PUBLICATION test-results/qualification test-results/product-comparison
```

The existing `prepare_qualification.py --refresh` re-exports the fixed graph/source inputs with the current map assets. Benchmark mode uses the same cameras and source bytes in SVG/Pixi, three alternating trials and 20 samples per mode. Frame timing is a scheduling proxy, not compositor FPS. JavaScript heap excludes GPU storage; the separate resource receipt measures texture lifetime. The original integration baseline and current run use the same laptop/browser and recipe but are separate runs, so they are not a randomized simultaneous before/after comparison.

## Measured result

SVG stays the default. Current timing results against the earlier integration baseline:

| Workload | Renderer | Current ready median, s | Overview p95, ms: before → after | Source p95, ms: before → after | Selection p95, ms: before → after | Current JS heap median, MiB |
|---|---|---:|---:|---:|---:|---:|
| Redux | SVG | 0.32 | 10.1 → 23.2 | 22.7 → 22.5 | 8.5 → 10.9 | 5.4 |
| Redux | PIXI | 1.12 | 84.1 → 21.9 | 62.3 → 56.7 | 36.5 → 25.4 | 13.4 |
| Synthetic | SVG | 0.85 | 49.7 → 35.6 | 54.5 → 25.2 | 251.1 → 142.1 | 15.1 |
| Synthetic | PIXI | 1.47 | 315.8 → 95.4 | 106.2 → 75.9 | 333.5 → 186.0 | 33.6 |
| Pydantic | SVG | 2.93 | 57.7 → 53.1 | 66.4 → 21.3 | 57.5 → 26.3 | 14.8 |
| Pydantic | PIXI | 3.53 | 355.1 → 176.2 | 68.3 → 52.1 | 92.3 → 58.9 | 28.5 |

The gains on the larger inputs do not establish that Pixi beats SVG. Redux SVG overview tails varied: 23.2 ms in the primary run and 12.6 ms in a bounded repeat versus the earlier 10.1 ms; source tails also varied. Both runs are retained. This is not an across-the-board speed improvement. Next product work is compact control rails and source framing with horizontal reveal, while GPU default promotion remains subject to broader performance/browser qualification. Raw measurements, the repeat, actual GL allocation receipts and screenshots are in the local SEREMY-Scene-Performance-Verification deliverable.
