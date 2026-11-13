# Compact controls and bounded source windows

The map uses one compact toolbar row for Files, Find, Back, Fit, zoom, folder collapse, Arrange and Inspect. Source verification and selection information sit in the footer. The controls retain their accessible names and keyboard behavior. A skip link focuses the source map. Opening or closing a panel leaves the camera and selection unchanged.

Find opens an overlay with file-path and observed-symbol search. `/` or Ctrl/Cmd+K opens it while outside editable controls. Enter opens a result; Escape closes Find and returns focus to its button. Empty results are explicit. Opening a result closes the drawer and focuses the map. Evidence navigation stays disabled while source verification is pending or failed.

Source cards are 650–760 world units wide. File headings show centered basenames; full paths remain in their accessible labels and hover titles. Wide lines use per-file earlier/later-column buttons and the inspector's Long-line position range. The controls support the keyboard. Following a call, a declaration, a search result or an MCP citation reveals the supporting byte range automatically. Hidden-column edge endpoints stop at the source-window boundary until the source is revealed.

Only the visible horizontal source slice and a small overscan are rendered. Line numbers stay fixed. Syntax colors come from the original line's token classification, including strings and comments that begin outside the window. ASCII slicing uses the measured monospace width; Unicode slicing uses measured prefixes and avoids breaking surrogate pairs. Source hashes and the canonical graph still cover the complete original bytes. Slicing does not truncate the stored source or change graph evidence.

SVG uses source-window clip paths. Pixi uses retained masked source groups for readable text and clipped focus geometry. Overview previews are bounded without adding a mask per file. The same controller still handles selection, navigation, arrangement, keyboard actions, saved views and local MCP. GPU objects and idle text allocations retain their existing explicit release behavior.

Back stores per-file horizontal offsets along with camera, selection, folders, folding and arrangement. Saved views include an optional `sourceOffsets` dictionary, scoped to the same repository snapshot. Invalid offsets and unknown files are rejected before restoring view state. Earlier views without offsets reveal and recenter a saved source selection under the new framing, retaining its zoom, and report that source framing was updated. New saved views restore their recorded camera and offsets directly.

## Design audit

| Finding | Change |
|---|---|
| A long verification label and permanent file/search fields made the header wrap. | One toolbar row; verification in the footer; Find on demand. |
| Repeated full paths dominated file headings. | Centered basenames with full-path labels and tooltips. |
| A long source line widened an entire card and its folder layout. | Bounded card widths with explicit horizontal reveal. |
| A width bound alone could hide a caller or declaration. | Navigation reveals exact byte ranges; both renderers clip the source window and preserve offsets. |
| Search needed focus restoration and an empty state. | Keyboard entry/Escape, explicit empty results and disabled navigation before verification. |

The existing local fonts, syntax colors, charcoal surfaces and dependency versions are retained. No framework or font dependency was added. The saved CodeCanvas reference has an unknown source revision and camera. The comparison aligns filename and viewport and records the new card bounds and toolbar height; it does not assert exact visual parity.

## Verification

`check-compact-source.cjs` analyzes a real TypeScript fixture with Unicode, tabs, CRLF, distant caller/declaration columns and a call after 20,000 characters. Both SVG and Pixi must keep exact glyph/hit/highlight alignment, expose only a bounded rendered slice, preserve the complete source/graph, restore offsets through Back and reload, reject invalid saved offsets and migrate earlier views. The Pixi case reads a real framebuffer region in the card padding to check that source text does not paint outside its window.

Existing core browser suites, local stdio MCP checks, three-workload viewport/DPR journeys, WebGL fallback checks and GPU allocation/release checks are rerun. Performance is measured separately with the functional browsers closed. Source-card geometry changed, so older performance records are historical context rather than a controlled before/after comparison.

```powershell
node seremy/tools/check-compact-source.cjs test-results/compact-source/long-lines
$env:SEREMY_RENDERER='pixi'
node seremy/tools/qualify-workflow.cjs REDUX_PUBLICATION test-results/qualification test-results/compact-source/workflow
Remove-Item Env:SEREMY_RENDERER
node seremy/tools/qualify-product-renderers.cjs REDUX_PUBLICATION test-results/qualification test-results/compact-source/performance
```

## Measured qualification

The final run passed 155 Python tests and 135 local browser case groups. Reference capture at 1225×580 measured a 44 px toolbar and a source card about 388×194 px at the reference zoom. The historical CodeCanvas revision/camera remain unknown. SVG stays default. Current renderer timings:

| Workload | Renderer | Ready median, s | Overview handler p95, ms | Source handler p95, ms | Selection handler p95, ms | JS heap median, MiB |
|---|---|---:|---:|---:|---:|---:|
| Redux | SVG | 0.51 | 17.6 | 15.1 | 8.1 | 6.1 |
| Redux | PIXI | 1.06 | 39.1 | 84.8 | 31.3 | 10.6 |
| Synthetic | SVG | 1.19 | 46.1 | 29.6 | 204.7 | 18.5 |
| Synthetic | PIXI | 1.49 | 78.6 | 72.6 | 323.1 | 35.8 |
| Pydantic | SVG | 3.05 | 77.9 | 28.4 | 54.5 | 18.2 |
| Pydantic | PIXI | 3.73 | 145.6 | 66.8 | 78.6 | 46.8 |

These are current-view measurements on one laptop; source-card geometry changed from earlier records. They are not a controlled before/after speed claim. Raw samples, screenshots, framebuffer/alignment checks and resource receipts are in the local SEREMY-Compact-Source-Verification deliverable.

## Verified hosted rollout

Runtime commit `aa8387b` is live at https://seremy-analysis.onrender.com/ (13 November 2026, deploy `dep-dbr98nui0phs73f6b11g`). Both SVG and Pixi passed six hosted case groups, including compact/Find keyboard and empty states, upload/downloads, refresh and recovered device history. The hosted capture measures a 44 px toolbar and bounded cards. Pixi was selected again after refresh and device-history recovery. The 135 local plus twelve hosted groups total 147 browser case groups. No page errors or new runtime error logs appeared during verification. The public browser used SwiftShader software WebGL; the timing and clipping runs used Intel UHD Direct3D11. Live MCP remains local-launcher only.
