# Dependency and source exploration

Inspect contains four connection views. All files shows the repository. Incoming, outgoing and neighborhood views use the selected file, identified above the counts. Select a file through navigation or source selection to change that scope. Following a relationship retains the filter scope. Back restores its mode and scope along with the camera, selected occurrence, source region and folder state.

Counts distinguish deduplicated relationships from individual source sites. The connection picker uses the same filtered occurrences as the canvas. Arrowheads mark the target direction. At overview zoom, groups count the filtered occurrences. A selected relationship retains its inspection evidence when a filter hides it from the canvas.

Unresolved and other outcomes exposes S03 records that have no bound call occurrence in the map. The viewer displays the recorded outcome, reason, target reference, operation, attempted flag, source byte range and bundle digest. Show source locates the original candidate. Follow target is disabled for these records. A failed source hash check disables evidence navigation and displays verification failure.

Source regions lists parser declarations enclosing the selected span, from the innermost declaration outward. Choosing one highlights its exact UTF-8 byte range across visible source lines. Back restores the call selection. Region selection uses the declarations already available from the language adapters. Statement-level syntax regions remain a possible extension. String and literal colors use line-based lexical highlighting. Multiline string/comment state has further work ahead.

Source anchors and token hitboxes measure the rendered text. The dedicated browser fixture combines Python Unicode, emoji, tabs and CRLF, nested declarations, two calls sharing one relationship, a missing call and TypeScript unsupported and external calls. It checks offsets against rendered glyph positions, direction filters, empty results, counts, Back restoration, recorded outcome reasons and stale-source handling.

Run the dedicated check with `node seremy/tools/check-connections.cjs test-results/connections/exploration`. Its temporary input is created outside Git-ignored output folders and removed after analysis.
