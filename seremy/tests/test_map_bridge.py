import json
import uuid

import pytest

from seremy.map_bridge import MapBridge
from seremy.product import analyze, publish
from seremy.viewer import render_map


@pytest.fixture
def bridge_case(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "entry.py").write_text('# é 🦊\ndef helper():\n return 1\ndef entry():\n helper()\n helper()\n missing()\n', encoding="utf8")
    bundle, ir, markdown, checks = analyze(source)
    output = tmp_path / "output"
    publication = publish(output, bundle, ir, markdown, checks, render_map(bundle))
    bridge = MapBridge(output)
    occurrence = bundle["contents"]["s03"]["artifact"]["edges"][0]["occurrences"][0]
    request = {"view_id": str(uuid.uuid4()), "publication": publication.name, "digest": bundle["bundle"]["content_digest"],
               "verified": True, "ack": 0, "selection": {"occurrence": occurrence["candidate_id"]}}
    bridge.register(request)
    return bridge, request, publication


def tool(bridge, request, name, **arguments):
    return bridge.tool({"tool": name, "view_id": request["view_id"], "digest": request["digest"], **arguments})


def test_selected_connection_has_snapshot_bound_source_and_documentation(bridge_case):
    bridge, request, _ = bridge_case
    context = tool(bridge, request, "context")
    assert context["connection"]["site_count"] == 2
    assert context["connection"]["target"]["name"] == "helper"
    assert [citation["text"] for citation in context["citations"]] == ["helper", "helper"]
    assert all(citation["sha256"] for citation in context["citations"])
    document = tool(bridge, request, "documentation")
    assert document["binds"]["content_digest"] == request["digest"]
    assert any(claim["kind"] == "relationship" for claim in document["claims"])
    assert any(claim["map_citations"] for claim in document["claims"])


def test_focus_is_queued_until_the_specific_browser_acknowledges(bridge_case):
    bridge, request, _ = bridge_case
    context = tool(bridge, request, "context")
    span = {key: context["citations"][1][key] for key in ("file", "start", "end")}
    queued = tool(bridge, request, "focus", span=span)
    assert queued["status"] == "queued"
    assert bridge.list_views()[0]["last_applied_command"] == 0
    assert bridge.register(request)["commands"][0]["span"] == span
    assert bridge.register(request)["commands"][0]["sequence"] == queued["sequence"]
    acknowledged = bridge.register({**request, "ack": queued["sequence"], "selection": {"span": span}})
    assert acknowledged["commands"] == []
    assert bridge.list_views()[0]["last_applied_command"] == queued["sequence"]
    with pytest.raises(ValueError, match="Outdated"):
        bridge.register(request)


def test_stale_digest_unverified_map_and_bad_spans_are_rejected(bridge_case):
    bridge, request, _ = bridge_case
    with pytest.raises(ValueError, match="Stale"):
        bridge.tool({"tool": "context", "view_id": request["view_id"], "digest": "old"})
    for span in [{"file": "../outside.py", "start": 0, "end": 1}, {"file": "entry.py", "start": 3, "end": 4},
                 {"file": "entry.py", "start": 0, "end": 99999}, {"file": "entry.py", "start": True, "end": 1}]:
        with pytest.raises(ValueError):
            tool(bridge, request, "focus", span=span)
    bridge.register({**request, "verified": False})
    with pytest.raises(ValueError, match="unverified"):
        tool(bridge, request, "context")


def test_stopping_sharing_cancels_pending_commands(bridge_case):
    bridge, request, _ = bridge_case
    citation = tool(bridge, request, "context")["citations"][0]
    tool(bridge, request, "focus", span=citation)
    bridge.register({**request, "verified": False})
    assert bridge.register(request)["commands"] == []


def test_notes_require_valid_citations_and_remain_annotations(bridge_case):
    bridge, request, _ = bridge_case
    citation = tool(bridge, request, "context")["citations"][0]
    with pytest.raises(ValueError, match="citations"):
        tool(bridge, request, "note", text="Unbacked prose", citations=[])
    result = tool(bridge, request, "note", text="<script>source is data</script>", citations=[citation])
    command = bridge.register(request)["commands"][0]
    assert command["type"] == "note"
    assert command["text"] == "<script>source is data</script>"
    assert command["citations"][0]["sha256"] == citation["sha256"]
    assert command["sequence"] == result["sequence"]


def test_unresolved_selection_exposes_its_recorded_reason(bridge_case):
    bridge, request, _ = bridge_case
    loader, _ = bridge.publication(request["publication"])
    record = next(record for record in loader.contents["s03"]["artifact"]["resolutions"] if record["outcome"] == "MISSING")
    bridge.register({**request, "selection": {"outcome": record["candidate_id"]}})
    context = tool(bridge, request, "context")
    assert context["resolution"]["reason"] == record["reason"]
    assert context["citations"][0]["text"] == "missing"
    assert "connection" not in context


def test_views_and_command_queues_are_isolated_and_expire(bridge_case):
    bridge, request, _ = bridge_case
    second = {**request, "view_id": str(uuid.uuid4())}
    bridge.register(second)
    citation = tool(bridge, request, "context")["citations"][0]
    tool(bridge, request, "focus", span=citation)
    assert bridge.register(second)["commands"] == []
    with pytest.raises(ValueError, match="acknowledgement"):
        bridge.register({**request, "ack": -1})
    bridge.views[request["view_id"]]["seen"] -= 121
    assert len(bridge.list_views()) == 1
    with pytest.raises(ValueError, match="unavailable"):
        tool(bridge, request, "context")


def test_changed_publication_artifacts_fail_before_registration(bridge_case):
    bridge, request, publication = bridge_case
    graph = publication / "graph.json"
    document = json.loads(graph.read_text(encoding="utf8"))
    document["contents"]["source_texts"]["entry.py"] = "changed"
    graph.write_text(json.dumps(document), encoding="utf8")
    fresh = MapBridge(bridge.output)
    with pytest.raises(ValueError, match="evidence changed"):
        fresh.register(request)
