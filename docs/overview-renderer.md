# Overview rendering

Below scale 0.5, occurrences with the same visible source container, target container and relationship kind share a path. The visible container is a file or its collapsed ancestor. Internal occurrences remain represented. Group counts include every occurrence, and the original graph and source evidence remain embedded without modification. Group tooltips report the count and explain that selection inspects the first site. Every individual occurrence remains available through the relationship picker. Selection draws its exact source-to-target path, and Follow target enters the source view. Layout changes invalidate the group cache.

Coarse source previews combine sampled line rectangles into one filled SVG path per file. Sampling is spaced by at least three screen pixels. At scale 0.5 and above, source lines, token controls and individual occurrence paths use the retained SVG renderer.

| Workload | Viewer | Overview handler p95, ms | Overview two-frame p95, ms | Overview SVG elements |
| --- | --- | ---: | ---: | ---: |
| Redux, 17 files, 1,582 lines, 30 source sites | 6a47163 | 26.0 | 59.0 | 925 |
| Redux | Updated | 4.4 | 35.9 | 100 |
| Synthetic, 100 files, 50,000 lines, 5,000 source sites | 6a47163 | 185.0 | 404.1 | 23,421 |
| Synthetic | Updated | 21.3 | 69.9 | 821 |

The comparison uses identical embedded inputs and 20 alternating wheel events per mode. It is a single local headless Chromium 158 run at 1440 by 900 on Windows with an Intel Core i5-10310U, without CPU throttling. Handler timing covers synchronous JavaScript. Two-frame timing includes browser scheduling and remains above a 60 Hz frame budget for the larger workload. Representative production qualification and GPU comparison remain open. Raw results are in overview-render-benchmark.json.

The overview browser check verifies complete occurrence counts, selecting and following an arbitrary occurrence, Back restoration, and recomputing group counts after folder collapse and expansion. Existing navigation, retained source rendering, nested folders, source integrity and long-file checks also passed. The retained-renderer test now compares visible exact paths against all source occurrences because the overview uses aggregated paths.

Verification completed on 2026-11-11 with 130 Python regressions and 31 browser checks passing. Python test repositories were created in the system temporary directory, outside the checkout's Git-ignored output folders.
