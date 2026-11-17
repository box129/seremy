# Online documentation drafts

The hosted application supports a browser workflow for file, folder, entity and connection explanations. A visitor chooses **Generate documentation**, selects a scope and question, then chooses **Generate draft**. The service prepares bounded source evidence, calls the configured model and returns a draft with clickable citations and a Markdown download. Explanations retain a review status.

## Owner setup

The first provider adapter uses OpenAI Chat Completions with strict JSON output. In the Render service dashboard, open **Environment** and add these variables, then deploy.

| Variable | Value |
| --- | --- |
| `ARCHDOC_AI_API_KEY` | A dedicated OpenAI API key, entered as a deployment secret |
| `ARCHDOC_AI_MODEL` | An account-accessible model supporting Chat Completions and strict JSON schema output |
| `ARCHDOC_AI_DAILY_REQUEST_LIMIT` | A positive integer chosen by the owner for the daily request allowance |

Until all three are configured, the form explains that the owner's model connection is pending. It continues to offer analysis, the structural guide and downloads. Visitors use the website without installing an agent or opening a terminal. The server calls the existing evidence functions directly. Desktop users can continue using the local MCP workflow.

The provider request sends the selected scope, optional question, claims, coverage and related source excerpts to OpenAI. The form discloses this before generation. Credentials remain on the server. Requests use `store: false`. Consult the provider's data policy for account-specific retention.

The adapter caps serialized evidence at 160 KiB and completion tokens at 2,048, with one active call and at most one queued call. A report permits up to 16 requests. Each attempt reserves one daily allowance unit before dispatch, including failed calls. Retries with the same request ID return the existing job. A completed failure permits a new attempt. Configure a spending limit through the provider account too. Request counts provide a usage bound whose cost depends on the chosen model and evidence size.

The approved pilot configuration uses `gpt-6-luna`, low reasoning and 10 requests per UTC day across the service, with a $3 monthly project spending cap in the OpenAI account. The adapter explicitly sends `reasoning_effort: low` and records it with the returned draft. The account spending cap is configured separately from these deployment variables.

Prompt version `hosted-documentation-v2` asks for a sectioned developer page rather than a short annotation. The document picker displays each generated page separately from the architecture guide. Existing shorter drafts can still be read and saved. See the [DeepWiki comparison](documentation-comparison.md) for the observed quality gaps and remaining repository-wiki work.

## Results and access

Only the browser that submitted the analysis receives its generation capability. That capability is kept in session storage, sent in a request header and excluded from the shared report and public job status. Opening a shared report permits reading its source and guide. Generate a fresh analysis in that browser to obtain generation access.

**Try the Redux example** starts an ordinary analysis of the bundled public Redux source. Its progress, private report and browser generation capability follow the same workflow as an upload. No repository download or AI request is needed to open the example. When the provider is enabled, Generate documentation and Document this selection can generate documentation from it, using the same daily allowance and evidence checks as other analyses. Reopening an older device-saved example remains read-only; choose Try the Redux example again to create a fresh live report.

Results carry the source snapshot identity. Provider output must reference claims from the retrieved context and pass the existing draft validator. Exact citation checks establish the referenced source ranges. Explanatory meaning still requires review. The server records the provider, requested model, prompt version and token cap with a `server_observed` basis. The exact underlying model snapshot is not inferred from an alias.

The writer uses a bounded page of 20 claims, ranked by question terms, entry filenames and observed import frequency. Retrieval includes direct captured static imports and consumers. One evidence-bearing claim per file is selected before additional claims, and implementation bodies are distributed across files within the existing eight-range budget. Draft coverage records omitted claims, partial bodies and the next evidence offset. Large folder requests can therefore produce a partial explanation. Narrow the scope to obtain additional detail.

**Save on this device** stores the displayed drafts alongside the report. Download the Markdown for a separate copy. Device storage can be cleared or evicted. Saved reports remain readable when their server reports expire. Starting a new draft from a saved report requires a new analysis.

Draft jobs and attempt counts use SQLite on the service filesystem. A process restart preserves completed drafts and marks interrupted jobs as failed when that filesystem survives. Render Free discards local changes on redeploy, restart or spin-down. Daily counters can reset along with results in those cases. Use provider-side spending limits for the pilot. Durable storage and coordinated reservations are required before promising restart-safe quotas, cross-device draft history or multiple service processes. The configured deployment uses one process.

## Verification

`seremy/tests/test_hosted_drafts.py` covers the HTTP routes, capability isolation, idempotent retry, daily reservations, surviving-filesystem restart, stale evidence, expired reports, bad model references, disabled inference, provider failure and request formatting. Its provider is simulated. Browser acceptance exercises upload, scope selection, Generate, cited result delivery and device saving without a local MCP client.

After connecting the provider, repeat the real-provider acceptance case from the implementation handoff using Redux's `src/utils/isAction.ts` or `utils/isAction.ts` when scoped to `src`. Review its explanation against the source. This step requires a valid credential and an owner-approved usage allowance.

The adapter follows the [official structured output API](https://developers.openai.com/api/docs/guides/structured-outputs). Hosting retention follows the [Render Free service documentation](https://render.com/docs/free).


## Overview and walkthrough pages

Choose **Start here** for an overview and a reading path through the captured code. Choose **How it works** for a focused feature walkthrough, optionally adding a question. Selecting a map item defaults to a walkthrough. Repository generation defaults to an overview. Each action generates one page and consumes one model request. Generate the second page separately when needed. Both pages remain selectable in Documentation and travel with Save on this device.

Prompt version `hosted-documentation-v3` supplies distinct reader goals for each page type. Purpose is bound to the request identity, so changing page type requires a new request. The Markdown title identifies the page, and the review notice remains visible.

This retrieval uses captured code and direct static neighbors. README and existing prose documentation capture, automatic multi-page planning, semantic validation and executable example checks remain pending. A scoped upload cannot retrieve files outside that upload. The eight-range source budget can still omit relevant bodies in a large scope. Import frequency is an ordering heuristic, not an architecture ranking.


Entry-module imports and exports are prioritized in their source order before import frequency, so an overview can reach core implementations within the body budget. Hosted generation limits supporting claims to three per section and inline citations to two per claim. Additional inline citations are counted as omitted. Transport retains validated citation ranges and hashes while omitting repeated source bodies from section payloads. These limits preserve the existing sixteen-citation contract.
