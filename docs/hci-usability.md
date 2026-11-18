# Usability improvements

The map supports touchscreen pinch zoom anchored to the fingers' midpoint, one-finger pan, and continuation of panning when one finger leaves a pinch. Gesture cancellation clears the input state. Zoom buttons remain available; focus the map to use +/− for zoom, arrow keys for pan and F to fit. A zoom percentage displays the current scale. Physical touchscreen and trackpad checks remain necessary; Chromium-emulated touch is not a substitute for hardware validation.

On narrow screens Files starts closed. Open it when needed; choosing a file closes it again. The inspector opens as a lower sheet. Primary actions use larger controls and secondary actions, saving and exports remain available in More actions. The optional guided example is available from Help instead of opening automatically.

Generate documentation opens a form with Documentation type and What should this document cover? It describes the expected overview or walkthrough and explains that source excerpts are used. No request is sent until the submit button is activated. Escape returns focus to the invoking action, including the launcher action outside the map iframe.

Analysis complete describes the map and structural guide. Documentation generated — review recommended describes a completed AI request. Documentation contains the structural Analysis overview and a document picker when generated documents exist. Each generated document has a Download this document (.md) action. The structural guide introduces the analyzed repository before its folded Technical evidence section; complete provenance remains in the export.

File search ranks exact paths and file stems before incidental source references. Existing source verification, capability checks, usage limits, citations, saved reports and retry request identities are preserved.

Validation for this change: 314 Python tests passed. The Redux browser check exercises consistent wording, Escape focus return, optional guidance, exact symbol search, mobile drawer/save access, Chromium two-finger input and midpoint anchoring, pinch-to-pan transition, cancellation and keyboard zoom. It also uses a simulated provider to check generation, saving and read-only restoration. The product map browser check covers seven existing source/navigation, mouse-wheel and minimap checks. No paid model call was made.

Remaining work includes physical device tests, representative-user task testing, a complete accessibility audit, richer definition/reference search grouping, document citation reading-position recovery, a separate project Overview destination, and a clearer first-use map summary. Hosting cold-start behaviour also remains unchanged. These changes do not certify WCAG conformance or establish a measured user success rate.

The accessibility follow-up separates directory checkboxes from expandable headings, enlarges their targets, improves text and form-border contrast, labels the search-results region, and honors reduced motion in the launcher. The documentation form now contains forward/reverse Tab navigation across its iframe boundary; the surrounding launcher is inert until the form closes, and Escape restores the trigger. Mobile navigation labels wrap with enlarged text.

The reproducible `seremy/tools/check-accessibility.cjs` accepts a local hosted URL, an output directory and a path to axe-core 4.11.0's `axe.min.js`. It checks visible documents with WCAG A/AA rule tags, records incomplete items separately, and asserts dialog focus, 320px reflow, text-spacing/doubled-text stress and directory visibility/Back behaviour. Real device and screen-reader testing and human trials remain unperformed.
