"""Snapshot-bound file dependencies, separate from runtime call observations."""
from seremy.contracts import canonical_bytes, sha256_hex

KINDS = {"IMPORTS", "TYPE_IMPORTS", "REEXPORTS", "TYPE_REEXPORTS"}


def build_module_dependencies(parsed_files):
    files = {record["file_id"]: record for record in parsed_files}
    expected = sorted([path, record["analysis_sha256"]] for path, record in files.items() if not path.endswith(".py"))
    edges, outcomes = [], []
    for path, record in sorted(files.items()):
        for candidate in record["candidates"]:
            observation = candidate.get("module_binding")
            if observation is None:
                continue
            context = observation.get("context", {})
            if context.get("snapshot_files") != expected or observation.get("method") != "typescript-module-resolution-v0.1":
                raise ValueError("module observation does not bind the parsed snapshot")
            kind = candidate.get("dependency_kind")
            if kind not in KINDS or candidate["kind"] not in {"import_specifier", "export_specifier"}:
                raise ValueError("invalid module dependency kind")
            candidate_id = f"cand:{path}#{candidate['kind']}:{candidate['name']}@{candidate['span'][0]}"
            outcome = {"candidate_id":candidate_id,"file_id":path,"candidate_span":candidate["span"],
                       "name":candidate["name"],"kind":kind,"outcome":observation["outcome"],
                       "reason":observation.get("reason"),"attempted":True}
            if observation["outcome"] == "RESOLVED_SINGLE":
                target = observation["target"]
                target_file = files.get(target["file_id"])
                if not target_file or target_file["analysis_sha256"] != target["content_sha256"]:
                    raise ValueError("module target is outside the parsed snapshot")
                edge = {"source_file":path,"target_file":target["file_id"],"kind":kind,
                        "origin":"compiler_module_observation","candidate_id":candidate_id,
                        "span":candidate["span"],"blob_sha256":record["analysis_sha256"],
                        "target_blob_sha256":target["content_sha256"],"method":observation["method"]}
                edge["edge_id"] = sha256_hex(canonical_bytes(edge))
                edges.append(edge)
                outcome["target_file"] = target["file_id"]
            outcomes.append(outcome)
    counts = {name:sum(record["outcome"] == name for record in outcomes) for name in sorted({r["outcome"] for r in outcomes})}
    return {"profile":"typescript-file-dependencies-v0.1","producer":"seremy.module_dependencies/0.1",
            "semantics":"static_module_dependency_not_runtime_execution","edges":edges,"outcomes":outcomes,
            "coverage":{"candidate_count":len(outcomes),"site_count":len(edges),
                        "distinct_edge_count":len({(e["source_file"],e["kind"],e["target_file"]) for e in edges}),
                        "outcome_counts":counts},
            "limits":["Python module dependencies are outside this profile.",
                      "Module edges do not establish symbol reference or runtime call targets.",
                      "Dynamic imports, CommonJS require and external package contents are outside this profile."]}
