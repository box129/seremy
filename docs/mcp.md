# Local MCP integration

SEREMY exposes selected architecture evidence to an MCP agent through the local launcher. The official Python SDK runs a stdio MCP server. The agent's language model supplies explanations and can send cited annotations back to the map.

Install the optional MCP dependency in a virtual environment from the repository root.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-mcp.txt
python -B -m seremy.server
```

Configure your MCP client with the virtual environment's Python executable as its command. Pass the absolute path to `seremy/mcp_server.py`, followed by `--url` and `http://127.0.0.1:8765`, as arguments. The script can start from the client's own working directory. Use the launcher's actual port if it was changed.

Open a repository in the local launcher. In Inspect, open MCP and agent notes and choose Share selection with agent. The client can then list available views and choose the matching view ID and graph digest. Stopping sharing revokes evidence access and cancels pending commands. Browser views expire after two minutes without a report.

| Tool | Behavior |
|---|---|
| `list_views` | Lists browser views, digests, current selections and the last acknowledged command. |
| `get_selection` | Returns source and connection evidence, enclosing declarations, structural component views, framework evidence and coverage. Unresolved candidates retain their outcomes and reasons. |
| `read_source` | Reads a verified UTF-8 range with its hash, line and excerpt. |
| `read_documentation` | Returns validated claims for the selection or one claim ID, with source ranges ready for map navigation. |
| `list_documentation_sections` | Lists section identities and claim counts for drafting. |
| `read_documentation_section` | Returns bounded section claims, source excerpts, dependencies, pagination and omissions. |
| `submit_documentation_draft` | Submits statements and reported generation metadata against a retrieved context. New prose retains review labels. |
| `read_documentation_draft` | Reads the submitted draft, Markdown, checks and current delivery acknowledgement. |
| `focus_source` | Queues focusing an exact source range in the chosen browser view. Back restores the prior navigation state. |
| `add_agent_note` | Queues an agent annotation with one to eight validated source citations. Its citation buttons focus source. |

The `explain_selection` prompt guides the client to inspect evidence and documentation, cite source and report limitations. Repository text, documentation and agent notes are untrusted content. The MCP server supplies context and instructions to help the client handle them as data.

Focus and annotation responses report `queued`. Browser reports acknowledge applied command sequence numbers. Commands are bound to the browser view and graph digest, retried until acknowledged, and isolated between tabs. An incompatible digest or unverified source produces a recoverable MCP tool error. Stopping sharing removes pending commands.

Annotations are labelled Agent annotation. Their source citations are validated against the publication. Annotation prose requires review. Save view also stores annotations in the current browser, scoped to the graph snapshot. Restoring the view restores their citation buttons.

Live sharing uses the loopback launcher. Hosted and exported maps display saved annotations and identify the local-launcher requirement for live MCP. The [section drafting workflow](documentation-drafts.md) adds evidence-scoped submissions, separate review labels, draft downloads and saved-view restoration. The `draft_documentation_section` prompt guides a connected model through that workflow.

The dedicated integration check starts the local launcher, analyzes Redux, opens two browser views and uses an official SDK client over an actual stdio connection. It reads the selected call and documentation, checks stale-digest errors, focuses a declaration in one tab, sends a cited annotation, restores it from browser storage and verifies access revocation.

```powershell
node seremy/tools/check-mcp.cjs test-results/mcp/live
```

Set `MCP_PYTHON` to the Python executable containing the pinned MCP SDK if it differs from `.venv/Scripts/python.exe`. The bridge regression tests also exercise invalid UTF-8 ranges, changed publication files, unresolved outcomes, queue acknowledgement, tab isolation, expiry and pending-command cancellation.
