import pytest

from seremy.tests.test_map_bridge import bridge_case, tool


def test_file_scope_carries_question_source_and_retry_receipt(bridge_case):
    bridge, request, _ = bridge_case
    scope = {"kind": "file", "value": "entry.py"}
    context = tool(bridge, request, "documentation_scope", scope=scope, question="How does entry use helper?")
    assert context["requested_scope"] == scope
    assert context["scope_file_count"] == 1
    assert any("def entry" in r["citation"]["text"] for r in context["implementation_context"]["records"])
    claim = context["claims"][0]
    submission = dict(request_id="scope-draft", context_digest=context["context_digest"], generation={},
                      statements=[{"text": "Read entry and helper together.", "kind": "explanation", "claim_ids": [claim["claim_id"]]}])
    receipt = tool(bridge, request, "submit_documentation_draft", **submission)
    assert receipt == tool(bridge, request, "submit_documentation_draft", **submission)
    assert receipt["draft"]["question"] == "How does entry use helper?"
    assert receipt["draft"]["requested_scope"] == scope
    assert not receipt["draft"]["accepted"]


def test_folder_entity_and_connection_scopes(bridge_case):
    bridge, request, _ = bridge_case
    loader, _ = bridge.publication(request["publication"])
    entity = next(e for e in loader.contents["s03"]["artifact"]["entities"] if e["name"] == "entry")
    for scope in ({"kind": "folder", "value": "."}, {"kind": "entity", "value": entity["entity_id"]},
                  {"kind": "connection", "value": request["selection"]["occurrence"]}):
        context = tool(bridge, request, "documentation_scope", scope=scope)
        assert context["claims"] and context["requested_scope"] == scope
    for scope in ({"kind": "file", "value": "../entry.py"}, {"kind": "folder", "value": "ent"},
                  {"kind": "entity", "value": "unknown"}, {"kind": "connection", "value": "unknown"}):
        with pytest.raises(ValueError):
            tool(bridge, request, "documentation_scope", scope=scope)
    with pytest.raises(ValueError):
        tool(bridge, request, "documentation_scope", scope={"kind": "file", "value": "entry.py"}, question="x" * 2001)
