"""Versioned experimental membership views bound to captured analysis inputs."""
import copy

from seremy.architecture import aggregate, structural_views, typed_edges
from seremy.contracts import canonical_bytes, sha256_hex
from seremy.language_profiles import SOURCE_EXTENSIONS

PROFILE = "seremy-membership-v0.1"
PLAN_PROFILE = "seremy-membership-plan-v0.1"
PRIMARY_TARGETS = {"structural_directory", "deployable_package", "semantic_component", "architectural_layer"}


def input_binding(contents):
    return {"repository_id": contents["snapshot"]["repository_id"],
            "inventory_manifest_digest": contents["snapshot"]["inventory_manifest_digest"],
            "policy_digest": sha256_hex(canonical_bytes(contents.get("policy", {"forbidden": [], "reject_cycles": False}))),
            "artifacts": {key: contents[key]["digest"] for key in ("s02", "s03", "s04")}}


def candidate_plan(contents, producer, adapter, *, targets=("semantic_component",), origin="derived"):
    """Call a candidate adapter with isolated input, retaining failed attempts.

    An adapter returns a list of proposed primary view records. Outputs pass the
    same membership validator used by authored input at the product entry point.
    """
    if not isinstance(producer, str) or not producer.strip() or not targets or set(targets) - {"semantic_component", "architectural_layer"} or origin not in {"derived", "model_hypothesis"}:
        raise ValueError("Candidate producer and supported target roster required")
    plan = {"profile": PLAN_PROFILE, "producer": producer, "origin": origin,
            "binds": input_binding(contents), "scheduled_targets": list(targets), "views": [], "role_views": [],
            "execution": "completed", "diagnostics": []}
    try:
        inputs = {key: contents[key] for key in ("snapshot", "inventory", "s02", "s03", "s04", "coverage", "source_texts", "policy")}
        plan["views"] = adapter(copy.deepcopy(inputs))
        build_membership(contents, plan)
    except Exception as error:
        plan.update(execution="failed", views=[], diagnostics=[f"{type(error).__name__}: {error}"])
    return plan


def evidence_records(records, contents, entities, edge_ids):
    if not isinstance(records, list) or not records:
        raise ValueError("Membership interpretation requires supporting evidence")
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Evidence records must be objects")
        kind = record.get("kind")
        if kind == "entity":
            if not isinstance(record.get("entity_id"), str) or record["entity_id"] not in entities:
                raise ValueError("Unknown evidence entity")
        elif kind == "edge":
            if not isinstance(record.get("edge_id"), str) or record["edge_id"] not in edge_ids:
                raise ValueError("Unknown evidence edge")
        elif kind == "source":
            path, span = record.get("file_id"), record.get("span")
            if not isinstance(path, str):
                raise ValueError("Source evidence requires a file identity")
            raw = contents["source_texts"].get(path, "").encode("utf8")
            if path not in contents["source_texts"] or record.get("blob_sha256") != sha256_hex(raw) or not isinstance(span, list) or len(span) != 2:
                raise ValueError("Source evidence does not bind this snapshot")
            start, end = span
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(raw):
                raise ValueError("Invalid membership source range")
            try:
                raw[:start].decode("utf8")
                raw[start:end].decode("utf8")
            except UnicodeDecodeError as error:
                raise ValueError("Membership evidence splits a UTF-8 character") from error
        elif kind == "artifact":
            stage, path = record.get("stage"), record.get("record_path")
            if stage not in ("s02", "s03", "s04") or record.get("artifact_digest") != contents[stage]["digest"] or not isinstance(path, list):
                raise ValueError("Artifact evidence does not bind an upstream input")
            value = contents[stage]["artifact"]
            for part in path:
                if isinstance(value, dict) and isinstance(part, str) and part in value:
                    value = value[part]
                elif isinstance(value, list) and type(part) is int and 0 <= part < len(value):
                    value = value[part]
                else:
                    raise ValueError("Artifact evidence record path is invalid")
        else:
            raise ValueError("Unknown membership evidence kind")
    return copy.deepcopy(records)


def normalize_view(raw, contents, *, producer, origin, role=False):
    if not isinstance(raw, dict):
        raise ValueError("Membership view must be an object")
    entities = {e["entity_id"]: e for e in contents["s03"]["artifact"]["entities"]}
    edge_ids = {e["edge_id"] for e in typed_edges(contents["s03"]["artifact"]["edges"])}
    required = {"view_id", "target", "rationale", "groups", "cut_id", "cut", "parents", "assignments", "disputed"}
    if set(raw) - (required | {"alternative_set"}) or not required <= set(raw):
        raise ValueError("Membership view has missing or unsupported fields")
    if not isinstance(raw["target"], str) or raw["target"] not in ({"role"} if role else PRIMARY_TARGETS - {"structural_directory", "deployable_package"}):
        raise ValueError("Authored/candidate views require semantic, layer or separate role targets")
    for field in ("view_id", "rationale", "cut_id"):
        if not isinstance(raw[field], str) or not 0 < len(raw[field].strip()) <= 4000:
            raise ValueError("View identity and rationale required")
    groups = raw["groups"]
    if not isinstance(groups, dict) or not all(isinstance(g, str) and g and isinstance(label, str) and label.strip() for g, label in groups.items()):
        raise ValueError("Groups require unique identities and names")
    parents, cut = raw["parents"], raw["cut"]
    if not isinstance(parents, dict) or not set(parents) <= set(groups) or not all(isinstance(p, str) and p in groups for p in parents.values()):
        raise ValueError("Hierarchy parents must reference declared groups")
    if not isinstance(cut, list) or not all(isinstance(g, str) and g in groups for g in cut) or len(set(cut)) != len(cut):
        raise ValueError("Cut must contain distinct declared groups")
    ancestors = {}
    for group in groups:
        chain, parent = [], group
        while parent in parents:
            parent = parents[parent]
            if parent == group or parent in chain:
                raise ValueError("Membership hierarchy contains a cycle")
            chain.append(parent)
        ancestors[group] = chain
    if not role and any(set(ancestors[g]) & set(cut) for g in cut):
        raise ValueError("Primary cut cannot contain both a group and its ancestor")
    assignments = raw["assignments"]
    disputed = raw["disputed"]
    if not isinstance(assignments, list) or not isinstance(disputed, list):
        raise ValueError("Assignments and disputes require arrays")
    membership, facts = {}, []
    for assignment in assignments:
        if not isinstance(assignment, dict) or set(assignment) != {"entity_id", "group_id", "evidence", "interpretation"}:
            raise ValueError("Assignments require entity, group, evidence and interpretation")
        entity, group = assignment["entity_id"], assignment["group_id"]
        if not isinstance(entity, str) or entity not in entities or not isinstance(group, str) or group not in cut:
            raise ValueError("Assignment is outside the entity universe or declared cut")
        if not isinstance(assignment["interpretation"], str) or not assignment["interpretation"].strip():
            raise ValueError("Assignment interpretation required")
        evidence = evidence_records(assignment["evidence"], contents, entities, edge_ids)
        if {"kind": "entity", "entity_id": entity} not in evidence:
            raise ValueError("Assignment must reference its own observed entity")
        if group in membership.get(entity, []) or (not role and entity in membership):
            raise ValueError("Duplicate or conflicting owner at this cut")
        membership.setdefault(entity, []).append(group)
        facts.append({**assignment, "evidence": evidence, "support": "unassessed"})
    disputed_entities = set()
    for dispute in disputed:
        if not isinstance(dispute, dict) or set(dispute) != {"entity_id", "candidates", "reason", "evidence"}:
            raise ValueError("Dispute requires entity, candidates, reason and evidence")
        entity, candidates = dispute["entity_id"], dispute["candidates"]
        if not isinstance(entity, str) or entity not in entities or entity in membership or entity in disputed_entities:
            raise ValueError("Disputed entity must be unique and unassigned")
        if not isinstance(candidates, list) or len(candidates) < 2 or not all(isinstance(g, str) and g in cut for g in candidates) or len(set(candidates)) != len(candidates):
            raise ValueError("Dispute requires distinct candidate groups at the cut")
        if not isinstance(dispute["reason"], str) or not dispute["reason"].strip():
            raise ValueError("Dispute reason required")
        evidence = evidence_records(dispute["evidence"], contents, entities, edge_ids)
        if {"kind": "entity", "entity_id": entity} not in evidence:
            raise ValueError("Dispute must reference its own observed entity")
        disputed_entities.add(entity)
    mapping = {entity: sorted(owners) if role else owners[0] for entity, owners in sorted(membership.items())}
    unassigned = sorted(set(entities) - set(mapping))
    group_entities = {g: set() for g in groups}
    for entity, owners in membership.items():
        for group in owners:
            for owner in [group, *ancestors[group]]:
                group_entities[owner].add(entity)
    view = {"view_id": raw["view_id"], "target": raw["target"], "mode": "overlapping_roles" if role else "primary_partition",
            "producer": producer, "origin": origin, "binds": input_binding(contents), "cut_id": raw["cut_id"],
            "rationale": raw["rationale"], "alternative_set": raw.get("alternative_set"),
            "universe": sorted(entities), "universe_semantics": "observed_declarations",
            "groups": dict(sorted(groups.items())), "cut": sorted(cut), "parents": dict(sorted(parents.items())),
            "membership": mapping, "assignments": sorted(facts, key=lambda a: (a["entity_id"], a["group_id"])),
            "unassigned": unassigned, "disputed": sorted(copy.deepcopy(disputed), key=lambda d: d["entity_id"]),
            "unassigned_reasons": {entity: "disputed" if entity in disputed_entities else "no_assignment_supplied" for entity in unassigned},
            "group_entities": {g: sorted(members) for g, members in sorted(group_entities.items())},
            "coverage": {"eligible": len(entities), "assigned": len(mapping), "unassigned": len(unassigned), "disputed": len(disputed_entities)},
            "assessment": "not_run", "capability": "exploratory"}
    view["membership_map_version"] = sha256_hex(canonical_bytes(mapping))
    view["version"] = sha256_hex(canonical_bytes(view))
    view["relationships"] = ({"status": "not_applicable", "reason": "overlapping_role_view_requires_role_specific_relation_semantics"}
                             if role else aggregate(contents["s03"]["artifact"]["edges"], view))
    return view


def build_membership(contents, plan):
    plan = copy.deepcopy(plan)
    if not isinstance(plan, dict) or set(plan) != {"profile", "producer", "origin", "binds", "scheduled_targets", "execution", "diagnostics", "views", "role_views"}:
        raise ValueError("Membership plan requires the versioned adapter contract")
    if plan["profile"] != PLAN_PROFILE or plan["binds"] != input_binding(contents):
        raise ValueError("Membership plan binds different snapshot or stage inputs")
    if plan["origin"] not in ("authored_contract", "derived", "model_hypothesis") or not isinstance(plan["producer"], str) or not plan["producer"].strip():
        raise ValueError("Experimental membership producer and origin required")
    if plan["execution"] not in ("completed", "failed") or not isinstance(plan["diagnostics"], list) or not all(isinstance(d, str) for d in plan["diagnostics"]):
        raise ValueError("Membership execution and diagnostics invalid")
    targets = plan["scheduled_targets"]
    if not isinstance(targets, list) or not all(isinstance(t, str) and t in {"semantic_component", "architectural_layer", "role"} for t in targets) or len(set(targets)) != len(targets):
        raise ValueError("Invalid scheduled membership targets")
    if not isinstance(plan["views"], list) or not isinstance(plan["role_views"], list):
        raise ValueError("Primary and role view rosters required")
    if plan["execution"] == "failed" and (plan["views"] or plan["role_views"] or not plan["diagnostics"]):
        raise ValueError("Failed membership attempt requires diagnostics and empty predictions")
    views = [normalize_view(v, contents, producer=plan["producer"], origin=plan["origin"]) for v in plan["views"]]
    roles = [normalize_view(v, contents, producer=plan["producer"], origin=plan["origin"], role=True) for v in plan["role_views"]]
    ids = [v["view_id"] for v in [*views, *roles]]
    if len(set(ids)) != len(ids) or set(ids) & {"structural_directory", "deployable_package"} or any(v["target"] not in targets for v in [*views, *roles]):
        raise ValueError("View identities must be unique and belong to scheduled targets")
    alternatives = {}
    for view in views:
        alternative = view["alternative_set"]
        if alternative is not None:
            if not isinstance(alternative, str) or not alternative:
                raise ValueError("Alternative set requires an identity")
            signature = (view["target"], view["cut_id"], view["universe"])
            if alternative in alternatives and alternatives[alternative] != signature:
                raise ValueError("Alternative views must retain the same target and universe")
            alternatives[alternative] = signature
    structural = structural_views(contents["s03"]["artifact"]["entities"], contents["s04"]["artifact"], contents["source_texts"])
    baseline = []
    for view in structural["views"]:
        descriptor = {**view, "view_id": view["target"], "producer": structural["producer"],
                         "universe": sorted(e["entity_id"] for e in contents["s03"]["artifact"]["entities"]),
                         "cut_id": view["target"], "cut": view["groups"], "parents": {}, "origin": "derived",
                         "mode": "primary_partition", "membership_map_version": view["version"],
                         "coverage": {"eligible": len(view["membership"]) + len(view["unassigned"]),
                                      "assigned": len(view["membership"]), "unassigned": len(view["unassigned"]), "disputed": 0},
                         "capability": "supported", "execution": "completed", "assessment": "not_run",
                         "evidence": {"method": "source_directory_or_nearest_manifest", "binds": input_binding(contents)}}
        descriptor["version"] = sha256_hex(canonical_bytes(descriptor))
        baseline.append(descriptor)
    files = {record["file_id"] for record in contents["inventory"]["eligible"] if record["file_id"].endswith(SOURCE_EXTENSIONS)}
    artifact = {"profile": PROFILE, "binds": input_binding(contents), "producer": plan["producer"], "origin": plan["origin"],
                "execution": plan["execution"], "assessment": "not_run", "diagnostics": plan["diagnostics"],
                "structural_views": baseline, "views": sorted(views, key=lambda v: v["view_id"]), "role_views": sorted(roles, key=lambda v: v["view_id"]),
                "scheduled_targets": sorted(targets), "file_universe": sorted(files),
                "targets": {target: {"capability": "exploratory", "execution": plan["execution"] if target in targets else "not_started",
                                     "assessment": "not_run", "attempted": target in targets,
                                     "eligible_entity_count": len(contents["s03"]["artifact"]["entities"]),
                                     "output_view_count": sum(v["target"] == target for v in [*views, *roles])}
                            for target in ("semantic_component", "architectural_layer", "role")},
                "upstream_coverage": copy.deepcopy(contents["coverage"]),
                "files_without_observed_entities": sorted(files - {e["file_id"] for e in contents["s03"]["artifact"]["entities"]}),
                "plan_digest": sha256_hex(canonical_bytes(plan))}
    return artifact
