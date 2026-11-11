# Retained SVG source rendering

At readable source zoom, scale 0.5 and above, the scene reuses matching SVG nodes, keeps their drawing order, and evicts content that leaves the viewport. Source lines and regions keep the existing evidence and selection model. Unselected relationships are culled using the bounds of their Bezier control points. The selected relationship remains available for navigation.

The overview rebuilds its coarse scene. Applying retained DOM reconciliation to the full overview caused a measured performance regression during development. Limiting retention to source zoom avoids that regression. GPU renderer comparison remains open.

The dedicated browser check verifies actual file-node identity across zoom, offscreen eviction, restoration through Fit, and call navigation after restoration. All 28 browser checks passed, including nested folders, folding, line 160,001 navigation, Back restoration, source integrity, and launcher flows.

| Workload | Viewer | Ready, ms | Overview handler p95, ms | Source handler p95, ms | Source two-frame p95, ms |
| --- | --- | ---: | ---: | ---: | ---: |
| Redux, 17 files, 1,582 lines, 30 call sites | a191793 | 341 | 29.2 | 8.8 | 44.1 |
| Redux | Updated | 257 | 21.9 | 8.6 | 44.5 |
| Synthetic, 100 files, 50,000 lines, 5,000 call sites | a191793 | 1,015 | 205.1 | 173.0 | 279.2 |
| Synthetic | Updated | 1,143 | 191.1 | 30.8 | 46.7 |

The larger source view rendered 379 SVG nodes at the final sample, compared with 15,229 in the baseline. Its overview still contained 23,421 nodes, and remains above the proposed interaction budget. Further overview work should address edge aggregation and a GPU scene experiment.

These are single local headless Chromium runs with 20 alternating wheel events per mode, without CPU throttling, on Windows and an Intel Core i5-10310U at 1440 by 900. Handler measurements cover synchronous wheel processing. Two-frame measurements also include browser scheduling. They provide a local comparison and leave representative production qualification open. Raw results are stored in retained-render-benchmark.json.

Use the existing benchmark fixture generator and analyzer, then pass baseline commit a191793 as the optional final benchmark argument.

```powershell
node seremy/tools/benchmark-map.cjs REDUX_VERSION_DIRECTORY SYNTHETIC_VERSION_DIRECTORY EVIDENCE_DIRECTORY SCRATCH_DIRECTORY a191793
node seremy/tools/check-retained-renderer.cjs REDUX_VERSION_DIRECTORY EVIDENCE_DIRECTORY
```

Run the comparison from the standalone Git checkout containing the baseline commit. Set CHROME_BIN when using an existing Chromium executable.
