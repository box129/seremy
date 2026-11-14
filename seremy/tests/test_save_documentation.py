from concurrent.futures import ThreadPoolExecutor

import pytest

from seremy.save_documentation import save_documentation
from seremy.tests.test_map_bridge import bridge_case, tool


def draft_request(case, destination):
    bridge, identity, _ = case
    context = tool(bridge, identity, "documentation_scope", scope={"kind": "file", "value": "entry.py"})
    claim = context["claims"][0]
    result = tool(bridge, identity, "submit_documentation_draft", request_id="save-test", generation={},
                  context_digest=context["context_digest"], statements=[{
                      "text": "Read entry and helper. Unicode é 🦊.", "kind": "explanation", "claim_ids": [claim["claim_id"]]}])
    return bridge, {**identity, "request_id": "save-test", "destination": str(destination)}, result["draft"]["markdown"]


def test_save_and_concurrent_retries_preserve_exact_markdown(bridge_case, tmp_path):
    path = tmp_path / "chosen documentation.md"
    bridge, request, markdown = draft_request(bridge_case, path)
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: save_documentation(bridge, request), range(3)))
    assert all(result["status"] == "saved" for result in results)
    assert path.read_bytes() == markdown.encode("utf8")
    assert not list(tmp_path.glob(".seremy-*.tmp"))


def test_existing_file_invalid_path_and_revoked_view(bridge_case, tmp_path):
    path = tmp_path / "existing.md"
    path.write_text("Preserve this user document", encoding="utf8")
    bridge, request, _ = draft_request(bridge_case, path)
    with pytest.raises(ValueError, match="different file"):
        save_documentation(bridge, request)
    assert path.read_text() == "Preserve this user document"
    for destination in ("relative.md", str(tmp_path / "wrong.txt"), str(tmp_path / "missing" / "out.md")):
        with pytest.raises(ValueError):
            save_documentation(bridge, {**request, "destination": destination})
    bridge.register({**request, "verified": False})
    with pytest.raises(ValueError, match="unverified"):
        save_documentation(bridge, {**request, "destination": str(tmp_path / "revoked.md")})
    assert not (tmp_path / "revoked.md").exists()
    assert not list(tmp_path.glob(".seremy-*.tmp"))
