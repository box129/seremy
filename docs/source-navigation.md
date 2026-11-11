# Source navigation milestone

The repository tree opens real source files. A selected call has a visible highlight and its bound relationship can be followed to the declaration. Back restores the source selection, selected relationship, camera translation and scale, expanded tree folders, and tree scroll position. Following a target reveals its containing folders.

Opening a file directly through the tree, search, or canvas title clears the selected relationship and disables Follow target and Show source. Back recovers the prior relationship. Following an explicitly selected relationship keeps its source and target available.

SVG source text preserves indentation and uses the measured monospace character width for source hitboxes, selection highlights, and relationship anchors. Source regions support Enter and Space selection.

`seremy/tools/check-navigation.cjs` exercises the recorded 17-file Redux fixture at 1440 by 900 pixels. It expands src and utils, opens isAction.ts through the tree, clicks the actual isPlainObject call, zooms and pans, follows the declaration, and compares the restored state after Back. It also measures highlight alignment against the rendered text and checks that Back restores folders opened while following a target.

The workspace now opens with No folder, a repository connection action, and centered Docs. Folder paths, ZIP uploads, and HTTPS Git repositories use a connection dialog. The loaded map occupies the window below the workspace toolbar. Documentation switching preserves its camera. A failed replacement repository keeps the existing map available.

Canvas layout now nests directories and files using their repository paths. Each directory heading controls its own collapsed state, including through Enter and Space. Collapsing a parent preserves its children's independent states. Following a relationship opens the target's ancestors, while Back restores the prior canvas layout and camera. Relationships to hidden files terminate at the visible collapsed ancestor. Internal relationships whose endpoints share the same collapsed ancestor are hidden until expansion. The minimap reflects the visible layout. Directory labels remain readable at overview zoom.

Files longer than 180 lines initially show an 80-line preview. Their file control expands or folds the full source through a click, Enter, or Space. Relationships into folded source end at its summary. Search and relationship navigation automatically expand source beyond the preview, and Back restores the previous file expansion state. Source bytes and line numbers remain available in the publication.

The viewer caches source positions using a byte-offset line index. Overview source bars sample lines at screen-pixel spacing, and source-region hitboxes appear at readable code zoom.

This milestone uses the existing SVG renderer. GPU rendering, MCP integration, and representative performance qualification remain planned work. Panel controls and the source toolbar still require further visual refinement. The local SVG comparison against the previous version is recorded in `render-benchmark.json` alongside the saved browser evidence.

The original `verification.json` records the source hashes and test results of baseline commit 8763352. The navigation milestone has its own `navigation-verification.json` receipt.

`workspace-verification.json` records the subsequent selection fix and workspace checks. The launcher check covers first visit, connection, documentation, failed replacement, and 1280 by 800 layout.

`nested-canvas-verification.json` records the nested layout milestone. The dedicated browser check verifies directory containment, independent collapse, boundary endpoints, keyboard controls, and restoration through Back on Redux.
