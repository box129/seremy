# Map arrangement and saved views

Arrange switches the canvas from source exploration to file and folder arrangement. Drag a file or folder to move it. Shift-click adds or removes items from the selection. Drag a selected item to move the selection together. Arrow keys move selected items by ten source-space units, or fifty with Shift. Switch Arrange off to explore source normally.

The inspector's Arrangement and saved view section offers Packed and Columns layouts. Each layout keeps its own manual positions. Moving a folder carries its descendants, and parent boundaries grow to contain moved children. Movement is bounded by the parent's header and left padding. Existing siblings keep their positions after a manual arrangement. Back restores an earlier arrangement, selection and layout.

Group selection creates a named visual group. Its label selects the members and can be dragged in Arrange mode. Ungroup removes that selected group. Groups store member identities and layout information. The graph payload, relationships and source evidence retain their original values. Folder collapse hides contained members until expansion.

Source breadcrumbs provide repository, directory and file navigation. Directory breadcrumbs focus the directory's bounds. Back returns to the previous camera and source selection.

Save view stores one view in browser localStorage for the repository, graph content digest and view schema version. Restore view explicitly opens it after the map is reopened. Stored state includes both layout position sets, visual groups, camera, source and relationship selection, filters, tree expansion and scroll, canvas folder collapse and long-file folding. Saved views are specific to the browser and snapshot. The saved HTML map carries the analysis data. Browser view preferences are stored separately.

The restore operation validates snapshot identities, scene members, coordinates, source-byte boundaries and state references before applying the view. Incompatible or damaged data produces a status message. Storage failures leave the current map usable. Saving replaces the whole saved view for this snapshot using one localStorage write.

Saved views also retain the optional Pixi/SVG renderer preference. Older views default to SVG, and unavailable WebGL falls back to SVG. Both renderers use the same arrangement controller. See [the renderer integration](pixi-integration.md).

The browser check `seremy/tools/check-arrangement.cjs` exercises real file, nested-folder and named-group drags, Shift selection, keyboard movement, layout switching, call navigation, breadcrumbs, collapse, reload and saved-view recovery. It also checks mismatched snapshots, damaged coordinates, storage failure and unchanged embedded graph data. Existing navigation, rendering, folding, dependency and launcher regressions passed.

Per-file horizontal source offsets are also saved and restored. Earlier views reveal their saved selection under the new bounded framing. See [compact controls and source windows](compact-source-workspace.md).
