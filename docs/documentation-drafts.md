# Documentation drafting through local MCP

Share a repository snapshot from Inspect in the local launcher. Ask the connected client to draft a guide section. The `draft_documentation_section` prompt supplies the workflow. The client lists sections, retrieves a page of evidence, writes statements and submits them. Drafts appear in Inspect and below the generated guide in Docs. Source buttons focus the exact cited range. Download draft Markdown saves the section with its review labels and relative `map.html` links.

The connected client's model writes the prose. SEREMY's MCP server supplies snapshot-bound evidence and checks the submission. This route uses the client's model connection. The hosted app continues to generate its deterministic guide. Live MCP sharing uses the local launcher.

## Tools

| Tool | Request and result |
|---|---|
| `list_documentation_sections` | Uses the view ID and graph digest. Returns section IDs, claim counts and analysis coverage. |
| `read_documentation_section` | Takes a section ID, offset and limit of 1–20. Returns a context digest, document/graph dependencies, claims, source excerpts, pagination and omissions. |
| `submit_documentation_draft` | Takes the context digest, unique retry request ID, statements and generation metadata. Returns a versioned draft and queued command sequence. |
| `read_documentation_draft` | Takes the original request ID. Returns the receipt and current queued, acknowledged or cancelled delivery state. |

Each statement has `text`, `kind` and `claim_ids`. Kinds are `projection`, `explanation` and `hypothesis`. A projection must copy exactly one retrieved validated claim to earn `verified_projection`. Altered projection prose is rejected. Explanations and hypotheses remain `review_required` because their meaning requires review. All draft publications retain `accepted: false`. Valid source ranges and claim references alone cannot establish the meaning of new prose.

References must belong to the retrieved page in the selected section and browser view. The server derives citations from these references. A valid source range from an unrelated claim cannot be substituted by the client. Graph, document and stage dependencies bind the receipt to the captured facts and policy. Stopping sharing blocks tool access, clears contexts and cancels pending commands. A new evidence read is needed for a new submission after sharing resumes. Retries of an existing request return its receipt; changing the payload under that request ID fails. Each submission and enqueue happen under the bridge lock.

Generation metadata contains `provider`, `model`, `prompt_version` and `settings`. Use null for unavailable values. Metadata is explicitly client reported. The server verifies neither the client model identity nor its hidden settings. Requested settings are preserved as supplied.

## Evidence limits and retention

Section retrieval caps the claim payload at 128 KiB and source citations at eight per claim. Large records disclose omitted fields. Source reads return bounded selected text and nearby lines, with truncation flags. Full files and function bodies may require additional reads. Each draft records the number of section claims, retrieved claims, referenced claims, omitted citations and truncated source excerpts. Clients should inspect pagination and omissions before making scope claims.

Drafts allow 1–20 statements of up to 4,000 characters, with 1–8 claim references per statement and at most sixteen distinct source ranges. Receipts cap at 256 KiB. Each browser view holds at most sixteen contexts and sixteen submissions. Contexts may be evicted. Receipts remain in launcher memory until view expiry or server restart. Save view persists displayed drafts in browser storage for the same graph snapshot. Markdown download provides a portable draft copy. Existing saved views restore with an empty draft list.

## Executed qualification

The checks exercise a real official SDK stdio client and real browser. One lane uses prose written by the active Codex model after reading the returned Redux evidence, then submits it through the same SDK bridge. A separate authored fixture lane checks the mechanics. Both lanes test rejected runtime/ownership projections, foreign references, retries, citation focus, downloads, Docs, revocation and Save/Restore. Other browser engines and other configured model clients retain separate qualification.

The model lane is a Codex model with an SDK transport bridge. It provides one integration example. Independent factual-support and usefulness judgments, broader repository coverage and a complete external-client comparison remain open. Human review and semantic-verifier fields remain `not_run` in the receipts.

```powershell
node seremy/tools/check-documentation-drafts.cjs test-results/drafts/mechanics
node seremy/tools/check-documentation-drafts.cjs test-results/drafts/fresh-model --model
```

For the model lane, use a fresh directory. Read `section-context.json` after `MODEL_CONTEXT_READY` and write `model-submission.json` with request_id, context_digest, statements and generation. The browser session waits for that real model submission. The helper provides a five-minute window for this local integration exercise.
