# File, folder and selection documentation

Open a repository in the local SEREMY launcher. Choose **Generate documentation**, select a file or folder and optionally enter a question. **Copy request for agent** prepares snapshot-bound evidence, enables local MCP sharing and copies a request for your connected agent. A visible text field provides the request when clipboard access is unavailable. Paste the request into the agent to start generation.

For the code currently in view, open Inspect and choose **Explain selection**. The picker offers the selected function or symbol, file or connection. Functions are identified from the selected declaration. Incoming and outgoing facts may include collaborators outside the selected path.

The new `read_documentation_scope` MCP tool takes `scope` with `kind` and `value`, an optional `question`, and pagination parameters. Kinds are `file`, `folder`, `entity` and `connection`. Paths belong to the captured snapshot. The root folder is `.`. Folder matching uses directory boundaries. Both direct call sites and recorded module occurrences can be selected. Empty-symbol files receive a captured-file claim and source preview.

The tool returns the original document identity, requested scope, question, scope file count, claim page and bounded implementation context. Writers inspect all omissions and pagination. The existing `submit_documentation_draft` tool delivers the result to Inspect and Documentation. Receipts and Markdown preserve the scope and question. Explanations retain their review labels and exact source navigation.

Choose **Save Markdown** in Documentation to save a particular draft. The label identifies the file or folder. A supported File System Access picker lets you choose the destination. The ordinary download link is available through the browser's link menu and on browsers without that picker. Active local views use a server-backed Markdown link. Saved views retain a browser-generated Markdown fallback. Sharing must remain active for a server-backed draft link.

For an active local MCP draft, **Save to local path** accepts the complete destination, including the `.md` filename. Choose an existing folder. The dialog confirms the saved path. The server writes the exact draft receipt as UTF-8, publishes the completed file atomically and preserves existing files with different contents. Repeated saves of identical content succeed. This route requires the current verified, shared browser view. The destination filesystem must support hard links for atomic publication.

## Verification

The full regression suite passed 288 tests. After the final module-connection handling change, 15 focused tests passed. Both modified inline browser scripts passed Node syntax checks.

A real browser selected `src/createStore.ts`, entered “How does subscription work?” and copied the request. A second request selected `src/utils/`. The active Codex assistant read fresh evidence through the official MCP SDK, wrote the file and folder explanations and submitted them through the same bridge. Retries returned the same receipts. Both drafts appeared in Documentation. A citation opened `dispatch` at line 270, and Explain selection offered that exact symbol.

Both browser download links saved Markdown files. Their bytes decoded as UTF-8 matched the acknowledged draft Markdown exactly. The native destination picker was not exercised in this browser. Independent prose quality review remains pending. This feature uses the connected agent through the local MCP workflow.

The subsequent local-path saving qualification passed **290 regression tests**. A Chrome UI exercise saved the existing file and folder examples to explicitly entered paths. Both saved files matched their receipt bytes exactly. Tests cover concurrent retries, Unicode text, invalid destinations, preservation of different existing content and revoked-view rejection. Chrome's native destination dialog could not be inspected through the desktop controls, so that separate picker retains its unverified status.
