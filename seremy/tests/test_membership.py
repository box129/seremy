"""Authored membership mechanics, uncertainty and real product integration."""
import copy
import json
from pathlib import Path

import pytest

from seremy.architecture import typed_edges
from seremy.bundle import BundleLoader
from seremy.contracts import canonical_bytes, sha256_hex
from seremy.membership import PLAN_PROFILE, input_binding, build_membership, candidate_plan
from seremy.product import analyze, seal, validate_graph
from seremy.documentation import validate_document
from seremy.__main__ import main

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/membership-slice"


def authored_plan(contents):
    ids = {entity["name"]: entity["entity_id"] for entity in contents["s03"]["artifact"]["entities"]}
    owners = {"api": "business", "worker": "jobs", "transport": "infrastructure", "policy": "business"}
    assignments = [{"entity_id": ids[name], "group_id": group, "interpretation": "Authored mechanics assignment",
                    "evidence": [{"kind": "entity", "entity_id": ids[name]}]} for name, group in owners.items()]
    view = {"view_id": "authored-components", "target": "semantic_component", "rationale": "Controlled authored mechanics fixture",
            "groups": {"all": "All", "business": "Business", "jobs": "Jobs", "infrastructure": "Shared infrastructure"},
            "parents": {"business": "all", "jobs": "all", "infrastructure": "all"}, "cut_id": "component-level",
            "cut": ["business", "jobs", "infrastructure"], "assignments": assignments,
            "disputed": [{"entity_id": ids["adapter"], "candidates": ["business", "infrastructure"],
                          "reason": "Authored ambiguity", "evidence": [{"kind": "entity", "entity_id": ids["adapter"]}]}]}
    return {"profile": PLAN_PROFILE, "producer": "seremy.authored-input/0.1", "origin": "authored_contract",
            "binds": input_binding(contents), "scheduled_targets": ["semantic_component"], "execution": "completed", "diagnostics": [],
            "views": [view], "role_views": []}


@pytest.fixture(scope="module")
def baseline():
    return analyze(FIXTURE)


def test_partial_source_coverage_isolated_files_shared_infrastructure_and_dispute(baseline):
    contents = baseline[0]["contents"]
    plan = authored_plan(contents)
    plan["views"][0]["assignments"][0]["evidence"].append({"kind": "artifact", "stage": "s04",
        "artifact_digest": contents["s04"]["digest"], "record_path": ["capabilities", "manifest_declarations"]})
    artifact = build_membership(contents, plan)
    plan["diagnostics"].append("caller changed plan")
    assert artifact["diagnostics"] == []
    view = artifact["views"][0]
    assert view["coverage"] == {"eligible": 7, "assigned": 4, "unassigned": 3, "disputed": 1}
    assert len(view["group_entities"]["all"]) == 4
    assert len(view["group_entities"]["infrastructure"]) == 1
    assert len(view["relationships"]["edges"]) == 3
    assert sum(e["site_count"] for e in view["relationships"]["edges"]) == 4
    assert artifact["upstream_coverage"]["s02"]["failed"] == 1
    assert artifact["files_without_observed_entities"] == ["broken.py", "empty.py"]
    assert view["assessment"] == "not_run" and view["origin"] == "authored_contract"


@pytest.mark.parametrize("mutation", ["conflict", "unknown_entity", "unknown_group", "foreign_evidence", "bad_artifact", "bad_record_path", "no_subject_fact", "cycle", "ancestor_cut", "disputed_assigned", "stale_snapshot"])
def test_invalid_membership_plan_is_rejected(baseline, mutation):
    plan = authored_plan(baseline[0]["contents"])
    view = plan["views"][0]
    assignment = view["assignments"][0]
    if mutation == "conflict":
        view["assignments"].append({**assignment, "group_id": "jobs"})
    elif mutation == "unknown_entity":
        assignment["entity_id"] = "foreign"
    elif mutation == "unknown_group":
        assignment["group_id"] = "foreign"
    elif mutation == "foreign_evidence":
        assignment["evidence"].append({"kind": "source", "file_id": "clients.py", "blob_sha256": "0" * 64, "span": [0, 2]})
    elif mutation in ("bad_artifact", "bad_record_path"):
        assignment["evidence"].append({"kind": "artifact", "stage": "s04",
            "artifact_digest": "0" * 64 if mutation == "bad_artifact" else baseline[0]["contents"]["s04"]["digest"],
            "record_path": ["nonexistent"]})
    elif mutation == "no_subject_fact":
        assignment["evidence"] = view["assignments"][1]["evidence"]
    elif mutation == "cycle":
        view["parents"]["all"] = "business"
    elif mutation == "ancestor_cut":
        view["cut"].append("all")
    elif mutation == "disputed_assigned":
        view["disputed"][0]["entity_id"] = assignment["entity_id"]
    else:
        plan["binds"]["artifacts"]["s03"] = "0" * 64
    with pytest.raises(ValueError):
        build_membership(baseline[0]["contents"], plan)


def test_overlapping_roles_and_complete_alternatives_stay_distinct(baseline):
    c = baseline[0]["contents"]
    plan = authored_plan(c)
    alternative = copy.deepcopy(plan["views"][0])
    alternative["view_id"] = "alternative-components"
    alternative["assignments"][0]["group_id"] = "jobs"
    plan["views"][0]["alternative_set"] = alternative["alternative_set"] = "complete-alternatives"
    plan["views"].append(alternative)
    role = copy.deepcopy(alternative)
    role.update(view_id="shared-role", target="role", disputed=[], alternative_set=None)
    role["assignments"] = [copy.deepcopy(a) for a in alternative["assignments"] if "transport@" in a["entity_id"]]
    assert len(role["assignments"]) == 1
    role["assignments"].append({**role["assignments"][0], "group_id": "business"})
    plan["role_views"] = [role]
    plan["scheduled_targets"].append("role")
    artifact = build_membership(c, plan)
    assert len(artifact["views"]) == 2
    assert artifact["views"][0]["membership"] != artifact["views"][1]["membership"]
    assert len(next(iter(artifact["role_views"][0]["membership"].values()))) == 2
    assert artifact["role_views"][0]["relationships"]["status"] == "not_applicable"
    plan["views"][1]["cut_id"] = "different-level"
    with pytest.raises(ValueError, match="Alternative"):
        build_membership(c, plan)


def test_unassigned_edge_endpoints_survive_aggregation(baseline):
    c = baseline[0]["contents"]
    plan = authored_plan(c)
    plan["views"][0]["assignments"] = [a for a in plan["views"][0]["assignments"] if "worker@" not in a["entity_id"]]
    result = build_membership(c, plan)["views"][0]["relationships"]
    assert len(result["unassigned_edge_ids"]) == 1
    retained = [edge for edge in typed_edges(c["s03"]["artifact"]["edges"]) if edge["edge_id"] in result["unassigned_edge_ids"]]
    assert len(retained) == 1 and "worker@" in retained[0]["source"]
    assert sum(e["site_count"] for e in result["edges"]) == 3


def test_candidate_callback_is_isolated_and_failures_retain_roster(baseline):
    c = baseline[0]["contents"]
    original = canonical_bytes(c)
    def adapter(inputs):
        assert "s05" not in inputs and "s06" not in inputs
        view = authored_plan(inputs)["views"][0]
        inputs["s03"]["artifact"]["edges"].clear()
        return [view]
    plan = candidate_plan(c, "test-candidate/0.1", adapter)
    assert canonical_bytes(c) == original
    assert build_membership(c, plan)["origin"] == "derived"
    def fail(inputs):
        raise RuntimeError("candidate unavailable")
    failed = candidate_plan(c, "test-candidate/0.1", fail)
    result = build_membership(c, failed)
    assert result["execution"] == "failed" and result["views"] == []
    assert result["targets"]["semantic_component"]["execution"] == "failed"
    assert result["diagnostics"] == ["RuntimeError: candidate unavailable"]


def test_empty_candidate_output_does_not_invent_a_group(baseline):
    c = baseline[0]["contents"]
    plan = authored_plan(c)
    view = plan["views"][0]
    view.update(groups={}, cut=[], parents={}, assignments=[], disputed=[])
    result = build_membership(c, plan)["views"][0]
    assert result["groups"] == {} and result["coverage"]["unassigned"] == 7
    assert len(result["relationships"]["unassigned_edge_ids"]) == 3


def test_real_product_cli_and_consumer_projections(tmp_path, baseline):
    plan = authored_plan(baseline[0]["contents"])
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    out = tmp_path / "out"
    assert main(["analyze", str(FIXTURE), "--membership-plan", str(path), "--output", str(out)]) == 0
    publication = out / json.loads((out / "current.json").read_text())["path"]
    bundle = json.loads((publication / "graph.json").read_text(encoding="utf8"))
    ir = json.loads((publication / "document-ir.json").read_text(encoding="utf8"))
    loader = BundleLoader(bundle)
    assert validate_graph(loader) == [] and validate_document(ir, loader) == []
    assert "Experimental membership views" in (publication / "architecture.md").read_text(encoding="utf8")
    assert '"membership"' in (publication / "map.html").read_text(encoding="utf8")
    assert len(bundle["contents"]["s06"]["artifact"]["membership_views"]) == 1
    assert bundle["contents"]["s03"] == baseline[0]["contents"]["s03"]
    import uuid
    from seremy.map_bridge import MapBridge
    bridge = MapBridge(out)
    request = {"publication": publication.name, "view_id": str(uuid.uuid4()), "digest": loader.meta["content_digest"],
               "verified": True, "selection": {}, "ack": 0}
    bridge.register(request)
    context = bridge.tool({"tool": "context", "view_id": request["view_id"], "digest": request["digest"]})
    assert context["experimental_membership"]["views"][0]["coverage"]["disputed"] == 1
    section = bridge.tool({"tool": "documentation_section", "view_id": request["view_id"], "digest": request["digest"],
                           "section_id": "experimental-membership"})
    assert any("not_run" in c["text"] for c in section["claims"])
    original_pointer = (out / "current.json").read_bytes()
    plan["binds"]["policy_digest"] = "0" * 64
    path.write_text(json.dumps(plan))
    assert main(["analyze", str(FIXTURE), "--membership-plan", str(path), "--output", str(out)]) == 1
    assert (out / "current.json").read_bytes() == original_pointer


def test_tampering_membership_and_relations_fails_graph_validation(baseline):
    bundle, ir, _, _ = analyze(FIXTURE, membership_plan=authored_plan(baseline[0]["contents"]))
    for stage in ("s05", "s06"):
        changed = copy.deepcopy(bundle["contents"])
        if stage == "s05":
            changed[stage]["artifact"]["experimental_membership"]["artifact"]["views"][0]["unassigned"] = []
        else:
            changed[stage]["artifact"]["membership_views"] = []
        changed[stage]["digest"] = sha256_hex(canonical_bytes(changed[stage]["artifact"]))
        loader = BundleLoader(seal(changed))
        assert validate_graph(loader)
        assert validate_document(ir, loader)


def test_absent_plan_preserves_legacy_graph_identity(baseline):
    assert analyze(FIXTURE, membership_plan=None)[0] == baseline[0]
    assert "experimental_membership" not in baseline[0]["contents"]["s05"]["artifact"]


def test_source_witness_uses_exact_utf8_boundaries_with_crlf(tmp_path):
    import shutil
    root = tmp_path / "source"
    shutil.copytree(FIXTURE, root)
    path = root / "clients.py"
    path.write_bytes(("# é 🦊\n" + path.read_text()).replace("\n", "\r\n").encode("utf8"))
    c = analyze(root)[0]["contents"]
    plan = authored_plan(c)
    evidence = {"kind": "source", "file_id": "clients.py", "blob_sha256": sha256_hex(path.read_bytes()), "span": [2, 4]}
    plan["views"][0]["assignments"][0]["evidence"].append(evidence)
    assert build_membership(c, plan)["views"][0]["coverage"]["assigned"] == 4
    evidence["span"] = [3, 4]
    with pytest.raises(ValueError, match="UTF-8"):
        build_membership(c, plan)


def test_extended_language_profile_retains_nonbound_outcomes(baseline):
    root = FIXTURE.parent / "ecmascript-slice"
    original = analyze(root)[0]
    c = original["contents"]
    plan = authored_plan(baseline[0]["contents"])
    plan["binds"] = input_binding(c)
    app = next(e for e in c["s03"]["artifact"]["entities"] if e["name"] == "App")
    view = plan["views"][0]
    view["assignments"] = [{"entity_id": app["entity_id"], "group_id": "business", "interpretation": "Authored profile mechanics",
                            "evidence": [{"kind": "entity", "entity_id": app["entity_id"]}]}]
    view["disputed"] = []
    bundle, _, _, _ = analyze(root, membership_plan=plan)
    assert bundle["contents"]["s03"] == c["s03"]
    membership = bundle["contents"]["s05"]["artifact"]["experimental_membership"]["artifact"]
    assert membership["views"][0]["coverage"]["assigned"] == 1
    assert len(membership["views"][0]["relationships"]["unassigned_edge_ids"]) == 3
    assert membership["upstream_coverage"] == c["coverage"]
