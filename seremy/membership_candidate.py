"""Experimental static-call cores. Ownership interpretations remain unassessed."""
from seremy.architecture import component_cycles, typed_edges

PRODUCER = "seremy.reciprocal-call-core/0.1"


def reciprocal_call_cores(inputs):
    entities = {e["entity_id"]: e for e in inputs["s03"]["artifact"]["entities"]}
    edges = [edge for edge in typed_edges(inputs["s03"]["artifact"]["edges"])
             if edge["origin"] == "binder_observation" and edge["kind"] == "CALLS"
             and edge["source"] in entities and edge["target"] in entities]
    clusters = [members for members in component_cycles(edges)
                if len({entities[entity]["file_id"] for entity in members}) >= 2]
    groups, assignments = {}, []
    for index, members in enumerate(clusters):
        group = f"call-core-{index + 1}"
        groups[group] = f"Call core {index + 1}"
        witnesses = [{"kind": "edge", "edge_id": edge["edge_id"]} for edge in edges
                     if edge["source"] in members and edge["target"] in members]
        for entity in members:
            assignments.append({"entity_id": entity, "group_id": group,
                "evidence": [{"kind": "entity", "entity_id": entity}, *witnesses],
                "interpretation": "Mutually reachable static-call core across source files. Responsibility ownership requires review."})
    return [{"view_id": "reciprocal-call-cores", "target": "semantic_component", "cut_id": "call-core",
             "rationale": "Experimental dependency-only proposal. One-way consumers and isolated declarations retain unassignment.",
             "groups": groups, "parents": {}, "cut": sorted(groups), "assignments": assignments, "disputed": []}]
