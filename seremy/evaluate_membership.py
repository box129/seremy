"""Bounded developer-fixture comparison for experimental membership proposals."""
import argparse
import copy
import json
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from seremy.architecture import typed_edges
from seremy.contracts import canonical_bytes, sha256_hex
from seremy.membership import build_membership, candidate_plan
from seremy.membership_candidate import PRODUCER, reciprocal_call_cores
from seremy.membership_metrics import score_partition, alternative_sensitivity, stability, rate, unavailable, membership_matching, normalize_name
from seremy.product import analyze, publish
from seremy.viewer import render_map

CORPUS = Path(__file__).parent / "fixtures/membership-evaluation"
PROFILE = "seremy-membership-comparison-v0.1"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf8")


def fixture_sources(contract, case):
    files = {stable: {**record, "text": (CORPUS / record["source"]).read_text(encoding="utf8")}
             for stable, record in contract["files"].items()}
    for edit in case["edits"]:
        if edit["kind"] == "move":
            files[edit["file"]]["path"] = edit["path"]
        elif edit["kind"] == "replace":
            text = files[edit["file"]]["text"]
            if text.count(edit["old"]) != 1:
                raise ValueError("Declared fixture edit does not match exactly once")
            files[edit["file"]]["text"] = text.replace(edit["old"], edit["new"])
        elif edit["kind"] == "add":
            if edit["file"] in files:
                raise ValueError("New stable identity already exists")
            files[edit["file"]] = {key: edit[key] for key in ("path", "text", "owner")}
        else:
            raise ValueError("Unknown fixture edit")
    paths = [file["path"] for file in files.values()]
    if len(set(paths)) != len(paths) or any(Path(path).is_absolute() or Path(path).drive or ".." in Path(path).parts for path in paths):
        raise ValueError("Source paths must be unique repository-relative paths")
    return files


def project_files(contents, artifact, files):
    if artifact["execution"] == "failed":
        return {"status": "failed", "owners": {}, "recognized": [], "names": {}, "diagnostics": artifact["diagnostics"]}
    entities = {e["entity_id"]: e for e in contents["s03"]["artifact"]["entities"]}
    inverse = {record["path"]: stable for stable, record in files.items()}
    view = artifact["views"][0]
    recognized = sorted({inverse[entities[entity]["file_id"]] for entity in view["universe"]})
    owners = {}
    for entity, group in view["membership"].items():
        stable = inverse[entities[entity]["file_id"]]
        owners.setdefault(stable, set()).add(group)
    return {"status": "completed", "owners": {key: sorted(value) for key, value in sorted(owners.items())},
            "recognized": recognized, "names": view["groups"], "entity_coverage": view["coverage"],
            "source_binding": artifact["binds"], "view_version": view["version"]}


def boundary_retention(case, output):
    owners = output["owners"]
    pairs = {tuple(pair) for pair in case["cross_interactions"]}
    return rate(sum(len(owners.get(a, [])) == len(owners.get(b, [])) == 1 and owners[a] != owners[b] for a, b in pairs), len(pairs))


def observed_interactions(contents, case, files):
    entities = {e["entity_id"]: e for e in contents["s03"]["artifact"]["entities"]}
    stable = {record["path"]: key for key, record in files.items()}
    observed = set()
    for edge in contents["s03"]["artifact"]["edges"]:
        source = entities[edge["source"]]["file_id"] if edge["source_type"] == "entity_ref" else edge["source"].removeprefix("file:")
        target = entities[edge["target"]]["file_id"]
        observed.add((stable[source], stable[target]))
    expected = {tuple(pair) for pair in case["cross_interactions"]}
    return {"declared_cross_interaction_recall": rate(len(expected & observed), len(expected)),
            "observed_unique_file_pairs": [list(pair) for pair in sorted(observed)], "kind": "observed_static_calls"}


def traceability(contents, artifact, normalized, files):
    entities = {e["entity_id"]: e for e in contents["s03"]["artifact"]["entities"]}
    assignments = artifact["views"][0]["assignments"] if artifact["views"] else []
    assigned_files = [key for key, owners in normalized["owners"].items() if len(owners) == 1]
    path_correct = sum(files[key]["path"] in contents["source_texts"] for key in assigned_files)
    location_correct = 0
    for assignment in assignments:
        entity = entities[assignment["entity_id"]]
        raw = contents["source_texts"][entity["file_id"]].encode("utf8")
        location_correct += raw[slice(*entity["name_span"])].decode("utf8") == entity["name"]
    rationale_correct = 0
    for key in assigned_files:
        rows = [a for a in assignments if entities[a["entity_id"]]["file_id"] == files[key]["path"]]
        rationale_correct += bool(rows) and all(a["interpretation"] and {"kind": "entity", "entity_id": a["entity_id"]} in a["evidence"]
                                               and any(e["kind"] == "edge" for e in a["evidence"]) for a in rows)
    relations = [edge for view in artifact["views"] for edge in view["relationships"]["edges"] if edge["source"] != edge["target"]]
    edge_ids = {edge["edge_id"] for edge in typed_edges(contents["s03"]["artifact"]["edges"])}
    return {"path": rate(path_correct, len(assigned_files)), "location": rate(location_correct, len(assignments)),
            "assignment": rate(rationale_correct, len(assigned_files)),
            "relationship": rate(sum(bool(edge["edge_ids"]) and set(edge["edge_ids"]) <= edge_ids for edge in relations), len(relations)),
            "snapshot": {**rate(0, 1), "reason": "plain_fixture_captures_content_hashes_without_git_commit"},
            "content_snapshot_binding": artifact["binds"], "scope": "Resolvable paths, spans and rule links. Ownership meaning remains unassessed."}


def worker(case_id, repeat, output):
    contract = json.loads((CORPUS / "contracts.json").read_text(encoding="utf8"))
    case = next(c for c in contract["cases"] if c["id"] == case_id)
    files = fixture_sources(contract, case)
    reference = {key: record["owner"] for key, record in files.items()}
    # Only source bytes enter the analyzer. Expected owners stay outside the copy
    # and are never supplied to the candidate callback.
    with tempfile.TemporaryDirectory(prefix="seremy-member-comparison-") as temporary:
        root = Path(temporary) / "source"
        root.mkdir()
        for record in files.values():
            path = root / record["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(record["text"], encoding="utf8", newline="")
        identity = {"repository_id": "membership-comparison:" + case_id, "declared_root": "fixture:" + case_id}
        started = time.perf_counter()
        base = analyze(root, use_git=False, snapshot_identity=identity)[0]
        plan = candidate_plan(base["contents"], PRODUCER, reciprocal_call_cores)
        bundle, ir, markdown, checks = analyze(root, membership_plan=plan, use_git=False, snapshot_identity=identity)
        elapsed = time.perf_counter() - started
        write_json(output / "graph.json", bundle)
        write_json(output / "plan.json", plan)
        artifact = bundle["contents"]["s05"]["artifact"]["experimental_membership"]["artifact"]
        normalized = project_files(bundle["contents"], artifact, files)
        write_json(output / "normalized.json", normalized)
        scored = score_partition(list(files), reference, normalized, ambiguous=case.get("ambiguous", []), aliases=contract["aliases"])
        controls = {}
        for name, owners, status in (("all-merged", {key: ["merged"] for key in files}, "completed"),
                                     ("all-singletons", {key: [key] for key in files}, "completed"),
                                     ("all-unassigned", {}, "completed"), ("failed-output", {}, "failed"),
                                     ("structural-target", {}, "unsupported")):
            controls[name] = score_partition(list(files), reference, {"status": status, "owners": owners,
                "recognized": list(files), "names": {}}, ambiguous=case.get("ambiguous", []), aliases=contract["aliases"])
        alternatives = []
        for owner in case.get("alternative_owners", []):
            alternatives.append({**reference, **{stable: owner for stable in case["ambiguous"]}})
        sensitivity = (alternative_sensitivity(list(files), alternatives, normalized, ambiguous=case["ambiguous"])
                       if alternatives else {"status": "not_applicable", "reason": "no_alternative_partitions"})
        result = {"profile": PROFILE, "case_id": case_id, "repeat": repeat, "producer": PRODUCER,
                  "runtime": {"python": sys.version, "platform": platform.platform(), "dependencies": "standard library and existing SEREMY pipeline"},
                  "lane": "source_to_output_developer_fixture", "status": "completed" if normalized["status"] == "completed" and scored["valid_partition"] else "failed",
                  "failure_reason": scored["reason"],
                  "scope": {"source": sorted(files), "support": [], "all": sorted(files), "ambiguous": case.get("ambiguous", [])},
                  "support_recognition": rate(0, 0, "empty_support_scope"),
                  "file_map": {key: record["path"] for key, record in files.items()},
                  "file_hashes": {key: sha256_hex(record["text"].encode("utf8")) for key, record in files.items()},
                  "source_graph_digest": base["bundle"]["content_digest"], "graph_digest": bundle["bundle"]["content_digest"],
                  "output_hash": sha256_hex(canonical_bytes(normalized)), "normalized": normalized,
                  "reference_partition": reference, "author_fixture_agreement": scored, "controls": controls,
                  "alternative_sensitivity": sensitivity, "dependency_retention": boundary_retention(case, normalized),
                  "observation_diagnostics": observed_interactions(base["contents"], case, files),
                  "provenance": traceability(bundle["contents"], artifact, normalized, files),
                  "hierarchy": unavailable("flat_candidate_has_no_hierarchy_producer"),
                  "upstream_coverage": artifact["upstream_coverage"], "semantic_quality": "not_run",
                  "resources": {"wall_seconds": elapsed, "scope": "snapshot capture plus candidate and validated product reanalysis. Fresh process",
                                "cpu": unavailable("not_instrumented"), "peak_rss": unavailable("not_instrumented"),
                                "llm_usage": unavailable("no_model_workflow")}}
        if repeat == 0:
            publication = publish(output / "publication", bundle, ir, markdown, checks, render_map(bundle))
            result["publication"] = publication.relative_to(output).as_posix()
        write_json(output / "result.json", result)
        if case_id == "base" and repeat == 0:
            masked = copy.deepcopy(base["contents"])
            original_edges = masked["s03"]["artifact"]["edges"]
            removed = typed_edges(original_edges)[0]["edge_id"]
            masked["s03"]["artifact"]["edges"] = original_edges[1:]
            masked["s03"]["digest"] = sha256_hex(canonical_bytes(masked["s03"]["artifact"]))
            masked_plan = candidate_plan(masked, PRODUCER, reciprocal_call_cores)
            mechanism = build_membership(masked, masked_plan)
            write_json(output / "observation-mask.json", {"lane": "injected_observation_mechanics", "removed_edge_id": removed,
                "original_source_graph_digest": base["bundle"]["content_digest"], "mutated_s03_digest": masked["s03"]["digest"],
                "group_count": len(mechanism["views"][0]["groups"]), "semantic_scores": unavailable("injected_lane_has_no_source_accuracy_credit"),
                "artifact": mechanism})
    return result


def checked_lineage(old, new, declared):
    if not set(declared) <= set(old["file_map"]) or not set(declared) <= set(new["file_map"]):
        raise ValueError("Lineage IDs are outside the declared inventories")
    if any(old["file_hashes"][stable] != new["file_hashes"][stable] for stable in declared):
        raise ValueError("Lineage marks changed source bytes as unchanged")
    return {stable: stable for stable in declared}


def name_stability(old, new, lineage):
    universe = sorted(lineage)
    refs = old["reference_partition"]
    outputs = [old["normalized"], new["normalized"]]
    if any(output["status"] != "completed" for output in outputs):
        return unavailable("failed_comparison")
    matches = []
    for output in outputs:
        assigned = {key: groups[0] for key, groups in output["owners"].items() if len(groups) == 1}
        matches.append({m["reference"]: m["predicted"] for m in membership_matching(universe, refs, assigned)})
    groups = set(refs[stable] for stable in universe if refs[stable] is not None)
    count = sum(group in matches[0] and group in matches[1] and
                normalize_name(outputs[0]["names"][matches[0][group]]) == normalize_name(outputs[1]["names"][matches[1][group]]) for group in groups)
    return rate(count, len(groups))


def evaluate(output, repeats=3):
    if type(repeats) is not int or repeats < 1:
        raise ValueError("A positive scheduled repeat count is required")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    contract = json.loads((CORPUS / "contracts.json").read_text(encoding="utf8"))
    records = []
    for case in contract["cases"]:
        for repeat in range(repeats):
            directory = output / case["id"] / str(repeat)
            directory.mkdir(parents=True, exist_ok=True)
            command = [sys.executable, "-B", "-m", "seremy.evaluate_membership", "--worker", case["id"], "--repeat", str(repeat), "--output", str(directory)]
            try:
                process = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], capture_output=True, encoding="utf8", timeout=120)
                (directory / "stdout.txt").write_text(process.stdout, encoding="utf8")
                (directory / "stderr.txt").write_text(process.stderr, encoding="utf8")
                result = json.loads((directory / "result.json").read_text(encoding="utf8"))
                if not isinstance(result, dict) or result.get("case_id") != case["id"] or result.get("repeat") != repeat or result.get("status") not in ("completed", "failed"):
                    raise ValueError("Worker returned an invalid run receipt")
                if process.returncode and result["status"] != "failed":
                    raise RuntimeError(f"Worker exited {process.returncode}. See retained stdout/stderr")
            except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
                result = {"case_id": case["id"], "repeat": repeat, "status": "failed", "error": str(error)}
                try:
                    files = fixture_sources(contract, case)
                    failed = {"status": "failed", "owners": {}, "recognized": [], "names": {}}
                    result.update(normalized=failed, author_fixture_agreement=score_partition(list(files),
                                  {key: record["owner"] for key, record in files.items()}, failed, ambiguous=case.get("ambiguous", [])))
                except (OSError, KeyError, ValueError) as corpus_error:
                    result.update(failure_phase="invalid_corpus_input", scoring=unavailable(str(corpus_error)))
                write_json(directory / "result.json", result)
            records.append(result)
    representatives = {record["case_id"]: record for record in records if record["repeat"] == 0}
    comparisons = []
    base = representatives["base"]
    for case in contract["cases"][1:]:
        current = representatives[case["id"]]
        if base["status"] != "completed" or current["status"] != "completed":
            comparisons.append({"case_id": case["id"], "status": "failed", "reason": "failed_source_run"})
            continue
        try:
            lineage = checked_lineage(base, current, case["unchanged"])
            comparisons.append({"case_id": case["id"], "status": "completed", "lane": "full_to_full",
                "lineage": lineage, "paths": {stable: [base["file_map"][stable], current["file_map"][stable]] for stable in lineage},
                "pair_disagreement": stability(list(base["file_map"]), list(current["file_map"]), lineage, base["normalized"], current["normalized"]),
                "name_stability": name_stability(base, current, lineage)})
        except ValueError as error:
            comparisons.append({"case_id": case["id"], "status": "failed", "reason": str(error)})
    deterministic = []
    for case in contract["cases"]:
        runs = [record for record in records if record["case_id"] == case["id"]]
        deterministic.append({"case_id": case["id"], "scheduled": len(runs), "successful": sum(r["status"] == "completed" for r in runs),
            "identical": all(r["status"] == "completed" for r in runs) and len({r["output_hash"] for r in runs}) == 1})
    report = {"profile": PROFILE, "producer": PRODUCER, "authorship": contract["authorship"], "repeats_per_snapshot": repeats,
              "metric_contract_sha256": sha256_hex((CORPUS / "frozen-metric-contract.md").read_bytes()),
              "corpus_sha256": sha256_hex(canonical_bytes({p.name: sha256_hex(p.read_bytes()) for p in sorted(CORPUS.iterdir()) if p.is_file()})),
              "implementation_sha256": {name: sha256_hex(Path(__file__).with_name(name).read_bytes()) for name in
                  ("evaluate_membership.py", "membership_metrics.py", "membership_candidate.py", "membership.py", "architecture.py",
                   "product.py", "python_adapter.py", "resolver.py", "parsing.py", "snapshot.py")},
              "source_runs": records, "repeat_determinism": deterministic, "comparisons": comparisons,
              "run_success": rate(sum(r["status"] == "completed" for r in records), len(records)),
              "semantic_quality": "not_run", "historical_40_snapshot_benchmark": "not_run", "independent_review": "not_run",
              "incremental_replay": unavailable("candidate_has_no_incremental_producer"),
              "recommendation": "Retain experimental status. Dependency cores require responsibility evidence and singleton coverage before promotion."}
    report["execution_status"] = "passed" if all(r["status"] == "completed" for r in records) and all(d["identical"] for d in deterministic) and all(c["status"] == "completed" for c in comparisons) else "failed"
    write_json(output / "comparison.json", report)
    (output / "COMPARISON.md").write_text(render_report(report), encoding="utf8")
    return report


def render_report(report):
    lines = ["# Experimental membership comparison", "", "Execution " + report["execution_status"] + ".", "",
             report["authorship"], "", "Candidate `" + report["producer"] + "`. Cold repeats per snapshot " + str(report["repeats_per_snapshot"]) + ". Repeats remain diagnostics of the same snapshots.", "",
             "| Snapshot | Pair F1 | Assigned files | Unassigned files | False merge | False split | Alias match |", "|---|---|---|---|---|---|---|"]
    def display(metric):
        return "N/A" if metric["value"] is None else f"{metric['numerator']}/{metric['denominator']}"
    for record in report["source_runs"]:
        if record["repeat"]:
            continue
        if record["status"] != "completed":
            lines.append("| " + record["case_id"] + " | failed | N/A | N/A | N/A | N/A | N/A |")
            continue
        score = record["author_fixture_agreement"]
        lines.append(f"| {record['case_id']} | {display(score['pairs']['metrics']['f1'])} | {display(score['coverage']['assignment'])} | {display(score['coverage']['unassigned'])} | {display(score['pairs']['metrics']['false_merge'])} | {display(score['pairs']['metrics']['false_split'])} | {display(score['alias_accuracy'])} |")
    lines.extend(["", report["recommendation"], "", "Independent semantic qualification, human naming/description ratings and the historical corpus remain not_run. "
                  "All results above describe developer-defined fixture agreement. Controls, ambiguity alternatives, lineage and resource scope are in the complete JSON report.", "",
                  "[Complete report](comparison.json)", ""])
    for record in report["source_runs"]:
        if record["repeat"] == 0 and record.get("publication"):
            prefix = record["case_id"] + "/0/" + record["publication"] + "/"
            lines.extend([f"- {record['case_id']} · [guide]({prefix}architecture.md) · [source map]({prefix}map.html) · [plan]({record['case_id']}/0/plan.json)"])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--worker")
    parser.add_argument("--repeat", type=int, default=0)
    args = parser.parse_args(argv)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.worker:
        result = worker(args.worker, args.repeat, output)
        return 0 if result["status"] == "completed" else 1
    report = evaluate(output)
    print(json.dumps({"execution_status": report["execution_status"], "run_success": report["run_success"], "recommendation": report["recommendation"]}, indent=2))
    return 0 if report["execution_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
