"""Test helper using the official SDK client over a real stdio transport."""
import asyncio
import json
from pathlib import Path
import sys

from mcp import StdioServerParameters
from mcp.client import Client


async def run():
    root = Path(__file__).resolve().parents[2]
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "seremy.mcp_server", "--url", sys.argv[1]], cwd=root)
    actions = json.loads(Path(sys.argv[2]).read_text(encoding="utf8"))
    results = []
    async with Client(parameters) as client:
        for action in actions:
            result = await client.list_tools() if action["tool"] == "list_tools" else await client.call_tool(action["tool"], action.get("arguments", {}))
            results.append(result.model_dump(mode="json", by_alias=True))
    print(json.dumps(results))


if __name__ == "__main__":
    asyncio.run(run())
