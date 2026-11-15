# Start using the SEREMY beta

## Use the public application

Open [SEREMY](https://seremy-analysis.onrender.com/), choose a repository ZIP or public GitHub URL, and analyze it. A cold start can take time. For a large GitHub repository, enter a source folder such as `src` to analyze only that folder. Configuration outside the chosen folder is excluded. The app shows the supported languages, input limits and analysis coverage.

Use Files or Find to open source. Select a call and follow its target, then use Back to return. Open Documentation to read the cited guide. Download the map, graph and Markdown to keep them. **Save on this device** stores the report in this browser. Server results expire after one hour and can disappear earlier when the free service restarts.

Choose **Generate documentation** for an explanation of a file, folder or map selection. Online AI drafts become available after the owner completes the [model connection setup](hosted-documentation.md). The form identifies the source excerpts sent to the provider. Returned explanations include citations and require review. Save the report after generation to keep its displayed drafts on this device.

During analysis, the loading line shows the current stage and its milestone percentage. Successful publication reaches 100%. Generated pages open directly in Documentation. Use **Choose documentation** to switch between a generated page and the architecture guide. New pages include sections for purpose, interfaces, implementation, dependencies, examples and limitations when evidence supports them.

## Start the local launcher for AI documentation

Install Python 3.12 or later, Node.js 22 and Git. Clone this repository, then run these commands from its root in PowerShell.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-mcp.txt
npm ci --prefix seremy/tools
.venv/Scripts/python.exe -B -m seremy.server --port 8765
```

Open `http://127.0.0.1:8765`. Choose a local source folder or try the full path to `seremy/fixtures/redux-slice` in your checkout.

Configure an MCP server in your agent client. Use your checkout's absolute paths in the following command and arguments. Adapt the surrounding configuration to your client's MCP settings.

```json
{
  "command": "C:/path/to/seremy/.venv/Scripts/python.exe",
  "args": [
    "C:/path/to/seremy/seremy/mcp_server.py",
    "--url",
    "http://127.0.0.1:8765"
  ]
}
```

The agent client should expose `list_views` and `read_documentation_scope`. The server can start from the client's own working directory. If you use another local port, update the MCP URL too. The connected agent supplies the language model and its existing authentication.

## Generate and save documentation

1. Choose **Generate documentation**, select a file or folder and optionally ask a question. **Explain selection** in Inspect starts from the current code or connection.
2. Choose **Copy request for agent**. This shares the verified snapshot locally. Paste the copied request into the connected agent. If clipboard access fails, copy the visible request text.
3. Ask the agent to follow that request and submit its explanation. Return to **Documentation** to see the draft. Opening Documentation also requests an immediate check for returned drafts.
4. Follow citations to inspect the supporting source. Check the draft's coverage and omissions. Review its explanation before using it as authoritative project documentation.
5. Choose **Save Markdown** to download a draft or use the browser's destination picker where supported. **Save to local path** accepts an absolute `.md` filename in an existing folder. It confirms the saved path and preserves existing files with different contents. This atomic save route requires hard-link support in the destination filesystem.

Keep sharing enabled while using local server saves. **Stop sharing selection** revokes MCP access and pending commands. Saved Markdown and portable maps remain available as local files.

## Recover from common problems

| What you see | What to do |
|---|---|
| Online drafting awaits the owner's model connection | The owner can enable browser drafting through the [hosted setup](hosted-documentation.md). The local MCP workflow above is also available. |
| No view, expired view or stale snapshot | Return to the map and create a fresh documentation request. Paste its exact view ID and digest into the intended agent. |
| Agent cannot connect | Check the Python executable, install `requirements-mcp.txt` in that environment, and match the launcher's running port. |
| Returned draft is still queued | Return to Documentation to refresh delivery. Check the map's sharing status if it remains unavailable. |
| Large repository import fails | Choose a source subfolder, upload a smaller source ZIP or analyze the local checkout. |
| GitHub reports an API limit | Branches and tags automatically try the public Git reference endpoint. You can also enter a full 40-character revision SHA, upload a source ZIP or retry later. |
| Save reports a missing folder or existing file | Choose an existing directory and a new filename. An identical repeated save succeeds. |
| Native destination picker is unavailable | Use Save to local path in the local launcher or the download link's browser menu. |
| Zero relationships or unsupported source | Open Coverage. Confirm the files fall within the supported lowercase `.py`, `.ts`, `.js`, `.jsx` and `.tsx` profiles. |

## Beta feedback

Try a repository you know. Record the source commit, selected folder, browser, analysis coverage, the action you attempted, expected result and actual result. Include a failing source example if it can be shared. Keep result URLs and screenshots private when they contain private code. For generated prose, check factual support, citation relevance and whether it helps you complete a concrete reading task.

The current scope covers bounded static analysis. Dynamic callbacks, general receiver dispatch, deeper framework semantics, broad accessibility acceptance and independent prose quality assessment retain separate qualification work.
