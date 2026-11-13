# File visibility and saved working sets

The Files tree has a checkbox beside each source file and directory. Unchecking a file hides its card and connections from the map. Its source, declarations, resolution outcomes and canonical graph records remain available. Open the file through Files or Find to reveal it again.

Directory checkboxes operate on every source file beneath that directory. A mixed checkbox means some descendants are included; checking it includes the entire subtree, and unchecking it hides the subtree. This is independent of expanding the Files tree and collapsing canvas folders. The footer counts included/displayable source files, including those inside collapsed folders. Coverage retains the broader discovery and parsing counts. Restore all brings back all source files without resetting the camera, folder collapse or arrangement.

When every file is hidden, the map explains the empty view and offers Restore all files. A repository with no supported/displayable source retains its separate analysis-coverage state.

## Navigation and relationships

Following a bound target, Show source, opening a file/symbol or focusing a citation through local MCP reveals that source file and its collapsed ancestors. Other hidden files stay hidden. Focusing a wholly hidden directory through breadcrumbs reveals that subtree. Back restores the previous visible set together with camera, selection, tree expansion, folder collapse, arrangement and horizontal source offsets.

Both endpoints must be included before a relationship is drawn. Hiding a target never redirects its connection to another file or to an otherwise visible folder. Included sources inside a collapsed folder still use that folder's boundary. Collapsed counts distinguish included files from total files when necessary.

The connection picker retains the graph's occurrences within the current direction/neighborhood filter, including hidden endpoints, so they remain inspectable and navigable. Its counts describe the visible projection and disclose hidden source sites. The map's original source/relationship totals describe the complete snapshot; the separate visible-file count describes the view. Selected evidence remains inspectable while its source is hidden.

## Persistence and integrity

Use Inspect → Arrangement and saved view → Save view, then Restore view after reopening the same snapshot. Visibility is saved alongside the existing view state. A fresh map initially includes every displayable source file; restoration is explicit.

The optional `hiddenFiles` field contains unique source paths belonging to the current snapshot. Restore rejects a non-array, null, non-string/unknown path or duplicate before modifying the current view. Older saved views without this field restore all files. Back also undoes a valid restoration.

Visibility is browser-local view state. It does not change analysis, source hashes, evidence identities, exported graph bytes or the full source embedded in portable HTML. An exported HTML map opened at a different origin does not inherit the original page's browser storage.

## Implementation

`scene-model.js` keeps explicit user-hidden paths separate from layout's `node.hidden` flag, which also represents collapsed ancestry. Layout measures/places included children and calculates descendant counts without rewriting the source tree. Empty subtrees have no canvas placeholder. Existing saved/manual positions are retained for later revelation.

The shared controller builds the file/subtree controls and preserves visibility in Back and Save/Restore. It caches scoped/visible edge projections until scope or layout/visibility changes; camera-only drawing reuses that projection. SVG and Pixi consume the same retained scene and navigation state. The local MCP focus command uses the same reveal path as ordinary source navigation.

## Verification

`check-file-visibility.cjs` analyzes a real four-file TypeScript fixture: two files in each of two folders, two callers, three source occurrences and one cross-folder target. Both renderers run the following five case groups in each tested browser:

1. Individual hide/show, sibling preservation, native mixed subtree controls and exact collapsed-boundary aggregation/counts.
2. Keyboard checkbox interaction, hidden-target reveal and complete one-step Back restoration.
3. Subtree visibility, hidden-directory breadcrumbs, all-hidden recovery, Find revealing a hidden file, Restore all and Back.
4. Explicit persistence across reload, atomic malformed/duplicate/unknown-path rejection and older-view compatibility.
5. Three desktop viewport sizes, retained renderer selection and unchanged canonical source/graph bytes.

The real stdio MCP regression now hides the selected target before an acknowledged focus command, verifies revelation only in the intended browser, and verifies that Back hides it again. Hosted checks exercise working sets across documentation switching, refresh and saved-device report recovery after simulated server expiry. Execution counts and actual runtime details are recorded in [visibility verification](file-visibility-verification.json).

```powershell
node seremy/tools/check-file-visibility.cjs test-results/file-visibility
```

Set `CHROME_BIN` to test an installed Chromium browser. SVG remains the default; wider browser/engine, mobile and comprehensive assistive-technology qualification remain separate work.
