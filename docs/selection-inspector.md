# Selection inspector

Selecting a source symbol or relationship opens Selection evidence. A resolved call shows the caller and target locations, five-line source excerpts, the evidence method, byte spans and bundle digest. Show source and Follow target use the existing navigation. Unbound symbols show their selected source excerpt. Navigation remains disabled when source verification fails.

Inspect opens and closes the panel. Files controls the repository drawer. Their close buttons support keyboard activation and return focus to their toolbar buttons. Escape dismisses a panel when focus is inside it. Both panels overlay the map, so toggling them preserves the camera, selection and tree expansion. The minimap moves beside the open inspector. Documentation switching through the launcher preserves the map and inspector.

Verification used Chromium 158 and the real 17-file Redux publication. The navigation check verifies caller line 6 in `isAction.ts`, declaration line 5 in `isPlainObject.ts`, source excerpts, keyboard panel toggles, call navigation and exact Back restoration. Layout checks cover 1440×900 and 1280×800. The launcher check exercises the inspector through mixed Python/TypeScript repository ingestion and documentation switching.

Product-map, nested-folder, retained-renderer and deep-source checks also passed. The deep-source fixture is created outside Git-ignored output directories so discovery can include it.

Dependency direction filters, richer syntax selection, graph arrangement, live MCP explanations and the GPU renderer comparison remain in the map implementation plan.
