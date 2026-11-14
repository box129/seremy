"""Reproducible documentation evaluation with separately authored source truth."""
import argparse
import copy
from datetime import datetime
import json
from pathlib import Path
import shutil
import tempfile
import uuid

from seremy.bundle import BundleLoader, CorruptBundleError
from seremy.contracts import canonical_bytes, sha256_hex
from seremy.documentation import document_digest, validate_document
from seremy.map_bridge import MapBridge
from seremy.guide import source_link
from seremy.product import analyze, publish, seal
from seremy.viewer import render_map

PROFILE = "seremy-documentation-evaluation-v0.1"
CORPUS = Path(__file__).parent / "fixtures" / "documentation-evaluation"


def fraction(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def source_site(sources, file, span):
    raw = sources[file].encode("utf8")
    return (file, raw[:span[0]].count(b"\n") + 1, raw[slice(*span)].decode("utf8"))


def evaluate_case(root, case, topics, output):
    identity = {"repository_id": "evaluation:" + case["case_id"], "declared_root": "fixture:" + case["folder"]}
    bundle, ir, markdown, validation = analyze(root, use_git=False, snapshot_identity=identity)
    loader = BundleLoader(bundle)
    contents = bundle["contents"]
    sources = contents["source_texts"]
    entities = {e["entity_id"]: e for e in contents["s03"]["artifact"]["entities"]}
    expected, observed = [], []
    for row in case["relationships"]:
        expected.append((row["source_file"], row["source_name"], row["target_file"], row["target_name"],
                         (row["source_file"], row["call_line"], row["call_token"])))
    for edge in loader.edges():
        source = entities.get(edge["source"], {"file_id": edge["source"], "name": edge["source"]})
        target = entities[edge["target"]]
        for site in edge["occurrences"]:
            observed.append((source["file_id"], source["name"], target["file_id"], target["name"],
                             source_site(sources, site["file_id"], site["span"])))

    def check(name, passed):
        checks.append({"check_id": name, "passed": bool(passed)})

    checks = []
    check("exact_relationship_roster", sorted(observed) == sorted(expected))
    witness_correct = 0
    witness_total = 0
    units = []
    walkthroughs = next(s for s in ir["sections"] if s["section_id"] == "walkthroughs")
    claims = {c["claim_id"]: c for c in ir["claims"]}
    for claim_id in walkthroughs["claim_ids"]:
        claim = claims[claim_id]
        source, target = entities[claim["subject"]["source"]], entities[claim["subject"]["target"]]
        row = next((r for r in case["relationships"] if
                    (r["source_file"], r["source_name"], r["target_file"], r["target_name"]) ==
                    (source["file_id"], source["name"], target["file_id"], target["name"])), None)
        for citation in claim["citations"]:
            witness_total += 1
            actual = source_site(sources, citation["file_id"], citation["span"])
            wanted = None
            if row:
                wanted = ((row["source_file"], row["call_line"], row["call_token"]) if citation["role"] == "call_site" else
                          (row["target_file"], row["declaration_line"], row["target_name"]))
            witness_correct += actual == wanted
        units.append(review_unit(case["case_id"], "template/" + claim_id, claim["text"], claim["citations"], ir["binds"]))
    check("walkthrough_call_and_target_citations", witness_total == 2 * len(expected) and witness_correct == witness_total)
    topic_checks = [{"topic": topic, "present": any(s["section_id"] == topic and s["claim_ids"] for s in ir["sections"])} for topic in topics]
    check("required_topic_presence", all(t["present"] for t in topic_checks))
    outcome_correct = 0
    for row in case["outcomes"]:
        matches = [r for r in contents["s03"]["artifact"]["resolutions"] if r["file_id"] == row["file"] and
                   r["name"] == row["name"] and source_site(sources, r["file_id"], r["candidate_span"])[1] == row["line"]]
        outcome_correct += len(matches) == 1 and (matches[0]["outcome"], matches[0]["reason"]) == (row["outcome"], row["reason"])
    check("expected_nonbound_outcomes", outcome_correct == len(case["outcomes"]))
    actual_frameworks = sorted((f["framework"], f["declared"], len(f["usage"])) for f in contents["s04"]["artifact"]["frameworks"])
    expected_frameworks = sorted((f["framework"], f["declared"], f["imports"]) for f in case["frameworks"])
    check("declared_and_imported_frameworks", actual_frameworks == expected_frameworks)
    check("template_post_validation", not validate_document(ir, loader) and validation["post_generation"]["status"] == "pass")
    check("source_comment_not_promoted_to_fact", not case.get("misleading_comment") or case["misleading_comment"] not in markdown)

    # Mutations target real generated artifacts, retaining otherwise valid evidence.
    first = next(c for c in ir["claims"] if c["kind"] == "relationship")
    for name in ("reversed_call", "irrelevant_valid_citation", "runtime_assertion", "cross_snapshot"):
        changed = copy.deepcopy(ir)
        claim = next(c for c in changed["claims"] if c["claim_id"] == first["claim_id"])
        if name == "reversed_call":
            claim["subject"]["source"], claim["subject"]["target"] = claim["subject"]["target"], claim["subject"]["source"]
        elif name == "irrelevant_valid_citation":
            unrelated = next(e for e in entities.values() if e["file_id"].startswith("misc."))
            claim["citations"][0] = {"file_id": unrelated["file_id"], "span": unrelated["name_span"],
                                     "blob_sha256": contents["snapshot"]["source_blobs"][unrelated["file_id"]]["analysis_sha256"]}
            check("irrelevant_citation_is_range_valid", loader.validate_citation(claim["citations"][0]["blob_sha256"], tuple(unrelated["name_span"])))
        elif name == "runtime_assertion":
            claim["text"] = case["forbidden_assertion"]
        else:
            changed["binds"]["content_digest"] = "0" * 64
        check("template_rejects_" + name, bool(validate_document(changed, loader)))

    publication = publish(output, bundle, ir, markdown, validation, render_map(bundle))
    shutil.copyfile(publication / "map.html", output / "map.html")
    bridge = MapBridge(output)
    request = {"view_id": str(uuid.uuid4()), "publication": publication.name, "digest": loader.meta["content_digest"],
               "verified": True, "selection": {}, "ack": 0}
    bridge.register(request)

    def tool(name, **arguments):
        return bridge.tool({"tool": name, "view_id": request["view_id"], "digest": request["digest"], **arguments})

    context = tool("documentation_section", section_id="walkthroughs")
    context_claim = context["claims"][0]
    statement = {"text": "Follow the linked call site and declaration to investigate the recorded static relationship.",
                 "kind": "explanation", "claim_ids": [context_claim["claim_id"]]}
    draft = tool("submit_documentation_draft", request_id="evaluation-draft", context_digest=context["context_digest"],
                 statements=[statement], generation={"provider": None, "model": None, "prompt_version": "authored-evaluation-v1", "settings": None})["draft"]
    check("authored_explanation_keeps_review_state", draft["statements"][0]["status"] == "review_required" and not draft["accepted"])
    write_json(output / "draft.json", draft)
    (output / "draft.md").write_text(draft["markdown"], encoding="utf8")
    citations = [{"file_id": c["file"], "span": [c["start"], c["end"]], "blob_sha256": c["sha256"]} for c in draft["statements"][0]["citations"]]
    units.append(review_unit(case["case_id"], "draft/" + draft["draft_id"], statement["text"], citations, ir["binds"]))
    for kind, outcome in (("projection", "rejected"), ("explanation", "review_required")):
        negative = tool("submit_documentation_draft", request_id="negative-" + kind, context_digest=context["context_digest"],
                        statements=[{"text": case["forbidden_assertion"], "kind": kind, "claim_ids": [context_claim["claim_id"]]}], generation={})["draft"]
        check("unsupported_" + kind + "_withholds_acceptance", negative["statements"][0]["status"] == outcome and not negative["accepted"])
    try:
        tool("submit_documentation_draft", request_id="foreign", context_digest=context["context_digest"],
             statements=[{**statement, "claim_ids": ["foreign-claim"]}], generation={})
    except ValueError:
        check("foreign_claim_rejected", True)
    else:
        check("foreign_claim_rejected", False)
    for stage in ("s03", "s05", "policy"):
        changed = copy.deepcopy(contents)
        if stage == "s03":
            changed[stage]["artifact"]["edges"] = []
        elif stage == "s05":
            changed[stage]["artifact"]["views"][0]["version"] = "changed-membership"
        else:
            changed[stage]["reject_cycles"] = True
        try:
            errors = validate_document(ir, BundleLoader(seal(changed)))
        except CorruptBundleError:
            check("graph_mutation_rejected_at_bundle_loader", stage == "s03")
        else:
            check("stale_" + stage + "_invalidates_document", bool(errors))
    # Re-analyze a real source edit rather than only changing a digest field.
    site = loader.edges()[0]["occurrences"][0]
    source = root / site["file_id"]
    raw = source.read_bytes()
    source.write_bytes(raw[:site["span"][0]] + b"missing_" + raw[site["span"][0]:])
    current, current_ir, _, _ = analyze(root, use_git=False, snapshot_identity=identity)
    check("source_edit_invalidates_document", bool(validate_document(ir, BundleLoader(current))))
    old_digest = request["digest"]
    try:
        bridge.tool({"tool": "documentation_draft", "view_id": request["view_id"], "digest": current["bundle"]["content_digest"], "request_id": "evaluation-draft"})
    except ValueError:
        check("draft_cannot_transfer_to_new_snapshot", old_digest != current["bundle"]["content_digest"])
    else:
        check("draft_cannot_transfer_to_new_snapshot", False)
    if case["folder"] == "tsx":
        (root / "tsconfig.json").write_text('{"compilerOptions":{"strict":true}}', encoding="utf8")
    else:
        manifest = root / "pyproject.toml"
        manifest.write_text(manifest.read_text().replace("fastapi>=0.100", "fastapi>=0.110"), encoding="utf8")
    configured, _, _, _ = analyze(root, use_git=False, snapshot_identity=identity)
    check("configuration_change_invalidates_document", bool(validate_document(current_ir, BundleLoader(configured))))
    return {"case_id": case["case_id"], "status": "passed" if all(c["passed"] for c in checks) else "failed",
            "publication_path": publication.relative_to(output).as_posix(),
            "graph_digest": loader.meta["content_digest"], "document_digest": document_digest(ir), "draft_id": draft["draft_id"],
            "checks": checks, "topics": topic_checks, "relationship_recall": fraction(len(set(expected) & set(observed)), len(expected)),
            "relationship_precision": fraction(len(set(expected) & set(observed)), len(observed)),
            "citation_correctness": fraction(witness_correct, witness_total), "expected_outcomes": fraction(outcome_correct, len(case["outcomes"])),
            "review_units": units}


def review_unit(case_id, unit_id, text, citations, binds):
    return {"unit_id": case_id + "/" + unit_id, "text": text, "citations": citations, "binds": binds}


def review_template(report):
    return {"profile": "seremy-documentation-review-v0.1", "run_digest": report["run_digest"],
            "reviewer_id": None, "reviewed_at": None, "reviewer_basis": "human_self_reported",
            "assessments": [{"unit_id": u["unit_id"], "support": None, "citation_correctness": None,
                             "clarity": None, "usefulness": None, "notes": "", "evidence_checked": []}
                            for case in report["cases"] for u in case.get("review_units", [])]}


def score_review(report, review):
    if not isinstance(review, dict):
        raise ValueError("Review must be an object")
    if review.get("profile") != "seremy-documentation-review-v0.1" or review.get("run_digest") != report["run_digest"]:
        raise ValueError("Review does not bind this evaluation run")
    units = {u["unit_id"]: u for case in report["cases"] for u in case.get("review_units", [])}
    assessments = review.get("assessments")
    if not isinstance(assessments, list):
        raise ValueError("Review assessments must be an array")
    seen, judged = set(), []
    for row in assessments:
        if not isinstance(row, dict) or not isinstance(row.get("unit_id"), str):
            raise ValueError("Review assessment requires a unit identity")
        unit_id = row.get("unit_id")
        if unit_id not in units or unit_id in seen:
            raise ValueError("Unknown or duplicate review unit")
        seen.add(unit_id)
        if row.get("support") not in (None, "supported", "contradicted", "insufficient") or row.get("citation_correctness") not in (None, "correct", "incorrect", "uncertain"):
            raise ValueError("Invalid support or citation judgment")
        for rating in ("clarity", "usefulness"):
            if row.get(rating) is not None and (type(row[rating]) is not int or not 1 <= row[rating] <= 5):
                raise ValueError("Review ratings must be integers from one to five or null")
        evidence = row.get("evidence_checked")
        if not isinstance(evidence, list) or not all(e in units[unit_id]["citations"] for e in evidence):
            raise ValueError("Review evidence must belong to this exact unit")
        if not isinstance(row.get("notes"), str) or len(row["notes"]) > 4000:
            raise ValueError("Review notes must be bounded text")
        if (row.get("support") is not None or row.get("citation_correctness") is not None) and not evidence:
            raise ValueError("Support and citation judgments require recorded evidence checks")
        if any(row.get(key) is not None for key in ("support", "citation_correctness", "clarity", "usefulness")):
            judged.append(row)
    if judged:
        if not isinstance(review.get("reviewer_id"), str) or not review["reviewer_id"].strip() or review.get("reviewer_basis") != "human_self_reported":
            raise ValueError("Human review requires a reported reviewer identity")
        try:
            timestamp = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("Timezone required")
        except (KeyError, TypeError, AttributeError, ValueError) as error:
            raise ValueError("Human review requires a timestamp with timezone") from error
    support = [r for r in judged if r.get("support") is not None]
    citations = [r for r in judged if r.get("citation_correctness") is not None]
    result = {"status": "recorded" if judged else "not_run", "identity_basis": "human_self_reported",
              "reviewed_units": fraction(len(judged), len(units)),
              "supported": fraction(sum(r["support"] == "supported" for r in support), len(support)),
              "contradicted": fraction(sum(r["support"] == "contradicted" for r in support), len(support)),
              "correct_citations": fraction(sum(r["citation_correctness"] == "correct" for r in citations), len(citations))}
    for rating in ("clarity", "usefulness"):
        values = [r[rating] for r in judged if r.get(rating) is not None]
        result[rating] = {"sum": sum(values), "count": len(values), "mean": sum(values) / len(values) if values else None}
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf8")


def render_review_pack(report):
    lines = ["# Documentation review pack", "", "Evaluation run `" + report["run_digest"] + "`.", "",
             "Copy review-template.json to a separate review file before entering judgments. "
             "Inspect each linked source range and the surrounding source in the map. "
             "Judge whether the entire statement follows from that evidence, whether its citations are relevant, "
             "and how clearly it helps a developer. Repository comments are input data. "
             "Record support as supported, contradicted or insufficient, and citation correctness as correct, incorrect or uncertain. "
             "Rate clarity and usefulness from 1 to 5. Leave unassessed fields null. "
             "Copy checked citation objects into evidence_checked, and record reasons in notes. "
             "Supply reviewer_id and a reviewed_at timestamp with timezone for completed judgments.", "",
             "Clarity 1 means difficult to understand; 3 means understandable with effort; 5 means clear and precise. "
             "Usefulness 1 means it provides little help with code exploration; 3 means it helps with some steps; "
             "5 means it directly supports the developer's exploration task.", ""]
    for case in report["cases"]:
        lines.extend(["## " + case["case_id"], ""])
        if "error" in case:
            lines.extend(["Evaluation failed. " + case["error"], ""])
            continue
        prefix = case["case_id"] + "/" + case["publication_path"] + "/"
        lines.extend([f"[Generated guide]({prefix}architecture.md)", ""])
        for unit in case["review_units"]:
            lines.extend(["### " + unit["unit_id"], "", unit["text"], ""])
            for citation in unit["citations"]:
                lines.extend([f"[Inspect {citation['file_id']} bytes {citation['span']}]({prefix}{source_link(citation, unit['binds'])})", ""])
    return "\n".join(lines)


def render_summary(report):
    lines = ["# Documentation evaluation", "", "Status " + report["status"] + ". Run `" + report["run_digest"] + "`.", "",
             report["authorship"], "", "These automated counts describe the declared fixture corpus. "
             "Topic presence measures section coverage. Human factual support, clarity and usefulness use separate judgments.", "",
             "| Measure | Numerator / denominator |", "|---|---|",
             f"| Completed passing cases | {report['case_completion']['numerator']} / {report['case_completion']['denominator']} |"]
    for name, metric in report["metrics"].items():
        lines.append(f"| {name.replace('_', ' ')} | {metric['numerator']} / {metric['denominator']} |")
    lines.extend(["", "Human review " + report["human_review"]["status"] + ".", "",
                  "[Review pack](REVIEW-PACK.md) · [Review template](review-template.json) · [Complete machine-readable report](evaluation.json)", ""])
    for case in report["cases"]:
        lines.extend(["## " + case["case_id"], "", "Status " + case["status"] + ".", ""])
        if "error" in case:
            lines.extend([case["error"], ""])
            continue
        prefix = case["case_id"] + "/" + case["publication_path"] + "/"
        lines.extend([f"[Generated guide]({prefix}architecture.md) · [Source map]({prefix}map.html) · [Authored draft fixture]({case['case_id']}/draft.md)", ""])
        lines.extend([f"- {check['check_id']} · {'pass' if check['passed'] else 'fail'}" for check in case["checks"]])
        lines.append("")
    return "\n".join(lines)


def evaluate(output, reviews=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    truth = json.loads((CORPUS / "truth.json").read_text(encoding="utf8"))
    corpus_hashes = {p.relative_to(CORPUS).as_posix(): sha256_hex(p.read_bytes()) for p in sorted(CORPUS.rglob("*")) if p.is_file()}
    report = {"profile": PROFILE, "corpus_profile": truth["profile"], "authorship": truth["authorship"],
              "evaluator_sha256": sha256_hex(Path(__file__).read_bytes()),
              "corpus_digest": sha256_hex(canonical_bytes(corpus_hashes)), "cases": []}
    with tempfile.TemporaryDirectory(prefix="seremy-documentation-evaluation-") as temporary:
        for case in truth["cases"]:
            root = Path(temporary) / case["folder"]
            shutil.copytree(CORPUS / case["folder"], root)
            destination = output / case["case_id"]
            destination.mkdir(exist_ok=True)
            try:
                result = evaluate_case(root, case, truth["required_topics"], destination)
            except Exception as error:
                result = {"case_id": case["case_id"], "status": "failed", "error": f"{type(error).__name__}: {error}"}
            report["cases"].append(result)
    report["status"] = "passed" if all(c["status"] == "passed" for c in report["cases"]) else "failed"
    report["case_completion"] = fraction(sum(c["status"] == "passed" for c in report["cases"]), len(truth["cases"]))
    report["metrics"] = {
        "expected_relationships": fraction(sum(c.get("relationship_recall", {}).get("numerator", 0) for c in report["cases"]),
                                           sum(len(c["relationships"]) for c in truth["cases"])),
        "required_citations": fraction(sum(min(c.get("citation_correctness", {}).get("numerator", 0), 2 * len(gold["relationships"]))
                                           for c, gold in zip(report["cases"], truth["cases"])),
                                       2 * sum(len(c["relationships"]) for c in truth["cases"])),
        "required_topic_presence": fraction(sum(t["present"] for c in report["cases"] for t in c.get("topics", [])),
                                            len(truth["required_topics"]) * len(truth["cases"])),
        "expected_outcomes": fraction(sum(c.get("expected_outcomes", {}).get("numerator", 0) for c in report["cases"]),
                                      sum(len(c["outcomes"]) for c in truth["cases"]))}
    report["run_digest"] = sha256_hex(canonical_bytes(report))
    template = review_template(report)
    write_json(output / "review-template.json", template)
    report["human_review"] = score_review(report, reviews if reviews is not None else template)
    write_json(output / "evaluation.json", report)
    (output / "REVIEW-PACK.md").write_text(render_review_pack(report), encoding="utf8")
    (output / "EVALUATION.md").write_text(render_summary(report), encoding="utf8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reviews", help="Completed review record bound to the same corpus run")
    args = parser.parse_args(argv)
    reviews = json.loads(Path(args.reviews).read_text(encoding="utf8")) if args.reviews else None
    report = evaluate(args.output, reviews)
    print(json.dumps({"status": report["status"], "case_completion": report["case_completion"], "human_review": report["human_review"]}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
