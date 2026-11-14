"""Evaluation regression checks, including scoring failures and absent judgments."""
import copy
import json
import shutil

import pytest

from seremy import evaluate_documentation as evaluation


@pytest.fixture(scope="module")
def evaluated(tmp_path_factory):
    return evaluation.evaluate(tmp_path_factory.mktemp("documentation-evaluation"))


def test_real_corpus_metrics_match_independent_source_truth(evaluated):
    assert evaluated["status"] == "passed"
    assert evaluated["case_completion"] == {"numerator": 2, "denominator": 2, "rate": 1.0}
    assert [c["citation_correctness"]["denominator"] for c in evaluated["cases"]] == [2, 4]
    assert sum(c["relationship_recall"]["denominator"] for c in evaluated["cases"]) == 3
    assert sum(len(c["topics"]) for c in evaluated["cases"]) == 12
    assert all(check["passed"] for case in evaluated["cases"] for check in case["checks"])
    human = evaluated["human_review"]
    assert human["status"] == "not_run"
    assert human["supported"]["denominator"] == 0 and human["supported"]["rate"] is None
    assert human["clarity"]["mean"] is None


def test_changed_gold_token_fails_and_retains_case_denominator(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    shutil.copytree(evaluation.CORPUS, corpus)
    truth = json.loads((corpus / "truth.json").read_text())
    truth["cases"][0]["relationships"][0]["call_token"] = "unrelated-token"
    (corpus / "truth.json").write_text(json.dumps(truth))
    monkeypatch.setattr(evaluation, "CORPUS", corpus)
    report = evaluation.evaluate(tmp_path / "results")
    assert report["status"] == "failed"
    assert report["case_completion"]["denominator"] == 2
    assert report["case_completion"]["numerator"] == 1
    assert report["cases"][0]["relationship_recall"]["numerator"] == 0
    assert report["cases"][0]["citation_correctness"]["numerator"] < 2


def test_failed_analysis_is_recorded_without_dropping_cases(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("fixture integration failure")
    monkeypatch.setattr(evaluation, "analyze", fail)
    report = evaluation.evaluate(tmp_path)
    assert report["status"] == "failed"
    assert report["case_completion"] == {"numerator": 0, "denominator": 2, "rate": 0.0}
    assert all(c["error"] == "ValueError: fixture integration failure" for c in report["cases"])
    assert report["human_review"]["reviewed_units"]["denominator"] == 0


def sample_review(report):
    review = evaluation.review_template(report)
    review.update(reviewer_id="synthetic-review-fixture", reviewed_at="2026-11-14T00:00:00+00:00")
    unit = report["cases"][0]["review_units"][0]
    review["assessments"][0].update(support="supported", citation_correctness="correct", clarity=4, usefulness=3,
                                    evidence_checked=[copy.deepcopy(unit["citations"][0])])
    return review


def test_partial_review_uses_only_supplied_judgment_denominators(evaluated):
    result = evaluation.score_review(evaluated, sample_review(evaluated))
    assert result["reviewed_units"]["numerator"] == 1 and result["reviewed_units"]["denominator"] == 5
    assert result["supported"] == {"numerator": 1, "denominator": 1, "rate": 1.0}
    assert result["clarity"] == {"sum": 4, "count": 1, "mean": 4.0}


@pytest.mark.parametrize("change", ["wrong_run", "duplicate_unit", "unknown_unit", "missing_identity", "bad_date", "bool_rating", "wrong_evidence", "missing_evidence", "bad_support"])
def test_malformed_or_unbound_review_is_rejected(evaluated, change):
    review = sample_review(evaluated)
    row = review["assessments"][0]
    if change == "wrong_run":
        review["run_digest"] = "0" * 64
    elif change == "duplicate_unit":
        review["assessments"].append(copy.deepcopy(row))
    elif change == "unknown_unit":
        row["unit_id"] = "unknown"
    elif change == "missing_identity":
        review["reviewer_id"] = None
    elif change == "bad_date":
        review["reviewed_at"] = "2026-11-14"
    elif change == "bool_rating":
        row["clarity"] = True
    elif change == "wrong_evidence":
        row["evidence_checked"][0]["blob_sha256"] = "0" * 64
    elif change == "missing_evidence":
        row["evidence_checked"] = []
    else:
        row["support"] = "probably"
    with pytest.raises(ValueError):
        evaluation.score_review(evaluated, review)


def test_evaluation_is_reproducible_across_temporary_roots(tmp_path, evaluated):
    repeated = evaluation.evaluate(tmp_path)
    assert repeated["run_digest"] == evaluated["run_digest"]


def test_cli_accepts_relative_output_and_writes_review_pack(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert evaluation.main(["--output", "review-output"]) == 0
    report = json.loads((tmp_path / "review-output/evaluation.json").read_text())
    assert report["status"] == "passed"
    assert (tmp_path / "review-output/REVIEW-PACK.md").is_file()
    assert all((tmp_path / "review-output" / case["case_id"] / "map.html").is_file() for case in report["cases"])
