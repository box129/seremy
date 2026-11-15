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


def test_walkthrough_retrieves_imported_type_and_preserves_scope(tmp_path):
    from seremy.product import analyze
    from seremy.bundle import BundleLoader
    from seremy.documentation import build_document_ir
    from seremy.document_scope import scoped_context
    from seremy.map_bridge import MapBridge
    from seremy.contracts import canonical_bytes, sha256_hex
    (tmp_path / "entry.ts").write_text("import type { Action } from './types';\nexport function check(value: Action) { return value.type }\n")
    (tmp_path / "types.ts").write_text("export interface Action { type: string }\n")
    bundle, document, _, _ = analyze(tmp_path)
    loader = BundleLoader(bundle)
    context = scoped_context(loader, document, {"kind": "file", "value": "entry.ts"},
                             "How is Action used?", 0, 20, lambda span: MapBridge.citation(loader, span),
                             purpose="walkthrough")
    assert context["requested_scope"] == {"kind": "file", "value": "entry.ts"}
    assert context["scope_file_count"] == 1 and context["related_file_count"] == 1
    assert context["documentation_purpose"] == "walkthrough"
    records = context["implementation_context"]["records"]
    assert {r["file"] for r in records} == {"entry.ts", "types.ts"}
    assert any("interface Action" in r["citation"]["text"] for r in records)
    assert context["context_digest"] == sha256_hex(canonical_bytes({k: v for k, v in context.items() if k != "context_digest"}))


def test_large_folder_prioritizes_named_topic_and_usable_claims(tmp_path):
    from seremy.product import analyze
    from seremy.bundle import BundleLoader
    from seremy.document_scope import scoped_context
    from seremy.map_bridge import MapBridge
    for index in range(24):
        (tmp_path / f"a{index:02}.py").write_text(f"def helper_{index}(): return {index}\n")
    (tmp_path / "zpayment.py").write_text("def charge(): return 7\n")
    bundle, document, _, _ = analyze(tmp_path)
    loader = BundleLoader(bundle)
    context = scoped_context(loader, document, {"kind": "folder", "value": "."}, "Explain zpayment", 0, 20,
                             lambda span: MapBridge.citation(loader, span))
    assert context["available_files"][0] == "zpayment.py"
    assert context["claims"][0]["map_citations"]
    assert any(r["file"] == "zpayment.py" for r in context["implementation_context"]["records"])
    assert context["next_offset"] is not None
