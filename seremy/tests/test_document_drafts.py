"""Adversarial section-draft checks against independently written source."""
import copy
from concurrent.futures import ThreadPoolExecutor

import pytest

from seremy.tests.test_map_bridge import bridge_case, tool


def context(case, **options):
    bridge, request, _ = case
    return tool(bridge, request, "documentation_section", section_id="walkthroughs", **options)


def submit(case, ctx, statements=None, **options):
    bridge, request, _ = case
    return tool(bridge, request, "submit_documentation_draft", request_id=options.pop("request_id", "draft-1"),
                context_digest=ctx["context_digest"],
                statements=statements or [{"text": ctx["claims"][0]["text"], "kind": "projection", "claim_ids": [ctx["claims"][0]["claim_id"]]}],
                generation=options.pop("generation", {}), **options)


def test_section_discovery_and_exact_projection_receipt(bridge_case):
    bridge, request, _ = bridge_case
    listed = tool(bridge, request, "documentation_sections")
    assert any(s["section_id"] == "walkthroughs" and s["claim_count"] == 1 for s in listed["sections"])
    ctx = context(bridge_case)
    assert [c["text"] for c in ctx["claims"][0]["map_citations"]] == ["helper", "helper", "helper"]
    assert ctx["next_offset"] is None
    result = submit(bridge_case, ctx)
    draft = result["draft"]
    assert draft["statements"][0]["status"] == "verified_projection"
    assert draft["accepted"] is False and draft["human_review"] == "not_run"
    assert draft["generation"]["unavailable"] == ["provider", "model", "prompt_version", "settings"]
    assert "map.html#seremy-source=" in draft["markdown"]
    assert tool(bridge, request, "documentation_draft", request_id="draft-1") == result
    bridge.register({**request, "ack": result["sequence"]})
    assert tool(bridge, request, "documentation_draft", request_id="draft-1")["delivery"] == "acknowledged"


@pytest.mark.parametrize("kind,status", [("projection", "rejected"), ("explanation", "review_required"), ("hypothesis", "review_required")])
def test_irrelevant_valid_support_cannot_accept_runtime_or_ownership_prose(bridge_case, kind, status):
    ctx = context(bridge_case)
    result = submit(bridge_case, ctx, [{"text": "helper always runs in production and owns the payment layer.",
                                       "kind": kind, "claim_ids": [ctx["claims"][0]["claim_id"]]}])
    draft = result["draft"]
    assert draft["statements"][0]["status"] == status
    assert draft["statements"][0]["support_semantics"] == "unverified"
    assert draft["accepted"] is False
    assert "Human review pending" in draft["markdown"]


def test_arbitrary_citations_and_cross_section_references_fail(bridge_case):
    bridge, request, _ = bridge_case
    ctx = context(bridge_case)
    overview = tool(bridge, request, "documentation_section", section_id="overview")
    for statement in [{"text": "wrong", "kind": "projection", "claim_ids": [overview["claims"][0]["claim_id"]]},
                      {"text": "wrong", "kind": "explanation", "claim_ids": [ctx["claims"][0]["claim_id"]], "citations": []}]:
        with pytest.raises(ValueError):
            submit(bridge_case, ctx, [statement])


def test_concurrent_retry_enqueues_exactly_once_and_changed_request_fails(bridge_case):
    bridge, request, _ = bridge_case
    ctx = context(bridge_case)
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: submit(bridge_case, ctx), range(3)))
    assert results[0] == results[1] == results[2]
    assert len(bridge.register(request)["commands"]) == 1
    with pytest.raises(ValueError, match="different submission"):
        submit(bridge_case, ctx, generation={"model": "changed"})


def test_revocation_invalidates_unsubmitted_context_and_blocks_reads(bridge_case):
    bridge, request, _ = bridge_case
    ctx = context(bridge_case)
    bridge.register({**request, "verified": False})
    with pytest.raises(ValueError, match="unverified"):
        submit(bridge_case, ctx)
    bridge.register(request)
    with pytest.raises(ValueError, match="fresh section"):
        submit(bridge_case, ctx)


def test_foreign_snapshot_context_and_expired_view_are_rejected(bridge_case):
    bridge, request, _ = bridge_case
    ctx = context(bridge_case)
    ctx["context_digest"] = "0" * 64
    with pytest.raises(ValueError, match="fresh section"):
        submit(bridge_case, ctx)
    bridge.views[request["view_id"]]["seen"] -= 121
    with pytest.raises(ValueError, match="unavailable"):
        context(bridge_case)


def test_drafts_and_contexts_are_isolated_between_browser_views(bridge_case):
    import uuid
    bridge, request, _ = bridge_case
    ctx = context(bridge_case)
    submit(bridge_case, ctx)
    other = {**request, "view_id": str(uuid.uuid4())}
    bridge.register(other)
    with pytest.raises(ValueError, match="unavailable"):
        tool(bridge, other, "documentation_draft", request_id="draft-1")
    with pytest.raises(ValueError, match="fresh section"):
        submit((bridge, other, None), ctx)


def test_metadata_and_partial_section_counts_survive_submission(bridge_case):
    ctx = context(bridge_case)
    meta = {"provider": "client-provider", "model": "client-model", "prompt_version": "draft-v1", "settings": {"temperature": 0.2}}
    draft = submit(bridge_case, ctx, generation=meta)["draft"]
    assert draft["generation"]["basis"] == "client_reported"
    assert draft["generation"]["settings"] == meta["settings"]
    assert draft["coverage"]["referenced_claim_count"] == 1
    assert draft["dependencies"]["graph"] == ctx["binds"]["content_digest"]


def test_pagination_limits_and_empty_page(bridge_case):
    ctx = context(bridge_case, offset=1, limit=1)
    assert ctx["claims"] == [] and ctx["omitted_claim_count"] == 1
    for options in ({"offset": -1}, {"limit": 21}, {"offset": True}):
        with pytest.raises(ValueError):
            context(bridge_case, **options)


def test_evidence_budget_and_source_truncation_are_disclosed(bridge_case):
    from seremy.document_drafts import evidence_context, submit_draft
    bridge, request, _ = bridge_case
    _, document = bridge.publication(request["publication"])
    altered = copy.deepcopy(document)
    section = next(s for s in altered["sections"] if s["section_id"] == "walkthroughs")
    claim = next(c for c in altered["claims"] if c["claim_id"] == section["claim_ids"][0])
    claim["citations"] *= 100
    claim["witnesses"] = [{"large": "x" * 100000}]
    ctx = evidence_context(altered, "walkthroughs", 0, 10, lambda span: {**span, "text_truncated": True})
    assert ctx["next_offset"] is None and len(ctx["claims"]) == 1
    assert ctx["claims"][0]["omitted_record_fields"]
    assert ctx["claims"][0]["omitted_citation_count"] == 300
    draft = submit_draft(ctx, [{"text": claim["text"], "kind": "projection", "claim_ids": [claim["claim_id"]]}], {})
    assert draft["coverage"]["omitted_record_count"] == 1
