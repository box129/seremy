# SVG folding and rendering measurements

Long files default to an 80-line preview when they exceed 180 lines. File controls expand the full source. Search and call navigation reveal hidden lines, and Back restores the prior expansion state. Source byte positions use cached lookups over a line-offset index. Overview bars sample at pixel spacing and token hitboxes appear at readable source zoom.

The comparison uses identical source blobs and graph data with the viewer at commit bd75e8e and the updated template. Each case has one load and 20 alternating wheel events at overview zoom, followed by 20 at a call source location. The source view in the larger fixture expands a file to reach a call below its preview.

| Workload | Viewer | Ready time, ms | Overview handler p95, ms | Source handler p95, ms | Overview two-frame p95, ms |
| --- | --- | ---: | ---: | ---: | ---: |
| Redux, 17 files, 1,582 lines, 30 call sites | bd75e8e | 421 | 126.8 | 57.2 | 157.5 |
| Redux | Updated | 243 | 22.3 | 6.8 | 50.8 |
| Synthetic, 100 files, 50,000 lines, 5,000 call sites | bd75e8e | 8,667 | 6,870.4 | 3,771.4 | 7,999.3 |
| Synthetic | Updated | 1,252 | 187.4 | 137.2 | 404.1 |

Measured on Windows, Intel Core i5-10310U, eight logical CPUs, headless Chromium 158.0.8127.18 at 1440 by 900 pixels. Ready time includes file navigation and source verification. Handler time measures synchronous wheel processing. Two-frame time also includes browser scheduling and presentation opportunities.

These are single local runs using a synthetic larger workload. A GPU renderer comparison and representative production qualification remain open. The larger updated view exceeds the proposed 33 ms frame budget. The next renderer experiment should measure a retained scene and visible-edge culling on this same workload, retaining the source navigation and folding checks.

`render-benchmark.json` contains the measurements. Browser checks passed 24 cases, including direct navigation to a declaration on line 160,001, automatic expansion through search and relationships, keyboard folding, Back restoration, nested directories, source integrity, and launcher flows.

Run these commands from the standalone Git checkout containing baseline commit bd75e8e.

```powershell
python -B seremy/tools/build_render_fixture.py test-results/render-input
python -B -m seremy analyze test-results/render-input --output test-results/render-publication
python -B -m seremy analyze seremy/fixtures/redux-slice --output test-results/redux-publication
node seremy/tools/benchmark-map.cjs REDUX_VERSION_DIRECTORY SYNTHETIC_VERSION_DIRECTORY EVIDENCE_DIRECTORY SCRATCH_DIRECTORY
```

Pass the generated version directories, each containing map.html. Set CHROME_BIN to an installed Chromium executable when necessary.
