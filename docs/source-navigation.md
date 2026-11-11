# Source navigation milestone

The repository tree opens real source files. A selected call has a visible highlight and its bound relationship can be followed to the declaration. Back restores the source selection, selected relationship, camera translation and scale, expanded tree folders, and tree scroll position. Following a target reveals its containing folders.

Opening a file directly through the tree, search, or canvas title clears the selected relationship and disables Follow target and Show source. Back recovers the prior relationship. Following an explicitly selected relationship keeps its source and target available.

SVG source text preserves indentation and uses the measured monospace character width for source hitboxes, selection highlights, and relationship anchors. Source regions support Enter and Space selection.

`seremy/tools/check-navigation.cjs` exercises the recorded 17-file Redux fixture at 1440 by 900 pixels. It expands src and utils, opens isAction.ts through the tree, clicks the actual isPlainObject call, zooms and pans, follows the declaration, and compares the restored state after Back. It also measures highlight alignment against the rendered text and checks that Back restores folders opened while following a target.

The workspace now opens with No folder, a repository connection action, and centered Docs. Folder paths, ZIP uploads, and HTTPS Git repositories use a connection dialog. The loaded map occupies the window below the workspace toolbar. Documentation switching preserves its camera. A failed replacement repository keeps the existing map available.

This milestone uses the existing SVG renderer. GPU rendering, nested layout on the canvas, MCP integration, and representative performance qualification remain planned work. Panel controls and the source toolbar still require further visual refinement.

The original `verification.json` records the source hashes and test results of baseline commit 8763352. The navigation milestone has its own `navigation-verification.json` receipt.

`workspace-verification.json` records the subsequent selection fix and workspace checks. The launcher check covers first visit, connection, documentation, failed replacement, and 1280 by 800 layout.
