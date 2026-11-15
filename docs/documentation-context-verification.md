# Implementation context for documentation drafting

The local `read_documentation_section` MCP tool now supplies an additive, versioned source packet. It contains the retrieved claims' declaration bodies or explicitly labelled file previews, plus nearby in-snapshot module occurrences. Source bytes, identities, dependencies and omissions bind to the context digest. Explanations retain related body citations for review; exact projections preserve their original claim citations. No new prose is promoted to an accepted architectural fact.

## Executed checks, 14 November 2026

- Full Python regression suite: **286 passed**, 221.21 seconds. This includes the two-case documentation corpus, stale-evidence rejection, draft isolation/revocation, exact projection checks and the new body/context tests.
- New tests cover complete caller/target bodies in the real bridge, UTF-8-safe truncation, file previews without invented ownership, deduplication, packet bounds, omitted source ranges, preserved module direction/kinds and empty subject contexts.
- A real official MCP SDK stdio client retrieved three Redux walkthrough claims at offset 21 and received five complete declaration bodies. No body or source citations were omitted; three module neighbors and 26 section claims remained outside the draft's scope. Three new source-reading explanations were written by the active Codex assistant after retrieval, submitted through the SDK and kept `review_required` / `accepted: false`. An exact retry returned the same receipt.
- A real in-app browser displayed the draft in Inspect and Documentation and followed the full-body source link to `src/utils/isAction.ts:4`. The receipt retains the generation provider as client reported and the model identity as unavailable.
- The same exercise found and fixed a reader ordering bug: only the main guide title is prepended, while later draft titles stay with their text. A fresh page load showed the main guide followed by its draft in the expected order. The final launcher passed Node's syntax check.
- The in-app browser's download-event wait timed out after clicking the draft Markdown button; no error was logged. Browser download completion is therefore unqualified in this run. The exact Markdown from the SDK receipt is supplied as `draft.md` beside its portable source map. The existing earlier browser qualification retains its own download result.

The chat's `outputs/Archdoc-Documentation-Context` directory holds the context, submission, receipt, portable source map, generated guide, review pack, screenshots and test receipt. A separate independent reviewer has not yet assessed factual support, clarity or usefulness. The implementing assistant's real drafting example is an integration and evidence-readability example, not an independent quality score.

## Product boundary

The enrichment is part of the local MCP drafting route and uses the connected client's model. Hosted analysis continues to produce the deterministic validated guide. No hosted LLM provider, public MCP endpoint or autonomous prose acceptance was added. Bodies may be partial or omitted within the documented budgets; module neighbors do not establish runtime execution. Full behavior of callbacks, receivers and external dependencies still needs additional evidence.
