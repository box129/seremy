"""Hand-calculated metric controls and actual candidate/pipeline regressions."""
import json
from types import SimpleNamespace

import pytest

from seremy.membership_metrics import pair_metrics, score_partition, membership_matching, alternative_sensitivity, stability
from seremy.evaluate_membership import worker, evaluate, checked_lineage, CORPUS

UNIVERSE = ["a", "b", "c", "d"]
REFERENCE = {"a": "A", "b": "A", "c": "B", "d": "B"}


def output(mapping, status="completed"):
    return {"status": status, "owners": {key: [group] for key, group in mapping.items() if group is not None},
            "recognized": list(mapping), "names": {"A": "Alpha", "B": "Beta"}}


def test_pair_counts_and_incomplete_output_denominators():
    result = pair_metrics(UNIVERSE, REFERENCE, {"a": "A", "c": "B", "d": "B"})
    assert result["counts"] == {"universe": 4, "pairs": 6, "reference_positive": 2, "reference_negative": 4,
                                "predicted_positive": 1, "tp": 1, "fp": 0, "fn": 1}
    assert result["metrics"]["f1"]["value"] == pytest.approx(2 / 3)
    assert result["metrics"]["false_split"]["value"] == 0.5
    all_merged = pair_metrics(UNIVERSE, REFERENCE, {key: "one" for key in UNIVERSE})
    assert all_merged["counts"]["fp"] == 4 and all_merged["metrics"]["false_merge"]["value"] == 1
    assert all_merged["metrics"]["f1"]["value"] == 0.5


def test_missing_owners_are_distinct_placeholders_and_na_stays_na():
    empty = pair_metrics(UNIVERSE, REFERENCE, {})
    assert empty["counts"]["predicted_positive"] == 0
    assert empty["metrics"]["precision"]["value"] is None
    assert empty["metrics"]["f1"]["value"] == 0
    singleton_truth = pair_metrics(UNIVERSE, dict(zip(UNIVERSE, UNIVERSE)), {})
    assert singleton_truth["metrics"]["f1"]["status"] == "not_applicable"


def test_conflicts_failures_unsupported_targets_and_extras_remain_visible():
    conflict = output(REFERENCE)
    conflict["owners"]["a"].append("B")
    result = score_partition(UNIVERSE, REFERENCE, conflict)
    assert not result["valid_partition"]
    assert result["coverage"]["conflict"]["numerator"] == 1
    assert result["pairs"]["metrics"]["f1"]["value"] is None
    failed = score_partition(UNIVERSE, REFERENCE, output({}, "failed"))
    assert failed["coverage"]["assignment"]["value"] == 0
    assert failed["coverage"]["unassigned"]["value"] == 1
    assert failed["coverage"]["extra"]["value"] is None
    unsupported = score_partition(UNIVERSE, REFERENCE, output(REFERENCE, "unsupported"))
    assert unsupported["coverage"]["assignment"]["value"] is None
    assert unsupported["pairs"]["metrics"]["f1"]["reason"] == "unsupported_target"
    extra = score_partition(UNIVERSE, REFERENCE, output({**REFERENCE, "ghost": "noise"}))
    assert extra["pairs"]["counts"]["universe"] == 4
    assert extra["pairs"]["metrics"]["f1"]["value"] == 1
    assert extra["diagnostics"]["spurious_extra_only_groups"] == ["noise"]


def test_positive_jaccard_matching_uses_membership_and_lexicographic_ties():
    predicted = {"a": "p1", "b": "p2", "c": "p1", "d": "p2"}
    matches = membership_matching(UNIVERSE, REFERENCE, predicted)
    assert [(r["reference"], r["predicted"]) for r in matches] == [("A", "p1"), ("B", "p2")]
    unrelated = membership_matching(UNIVERSE, REFERENCE, {"ghost": "A"})
    assert unrelated == []
    aliases = {"A": ["alpha"], "B": ["beta"]}
    actual = output(REFERENCE)
    actual["names"]["A"] = "  ALPHA  "
    assert score_partition(UNIVERSE, REFERENCE, actual, aliases=aliases)["alias_accuracy"]["value"] == 1
    actual["names"]["A"] = "Alpha!"
    assert score_partition(UNIVERSE, REFERENCE, actual, aliases=aliases)["alias_accuracy"]["value"] == 0.5


def test_alias_matching_bounds_are_explicit():
    ids = [str(i) for i in range(13)]
    with pytest.raises(ValueError, match="twelve"):
        membership_matching(ids, dict(zip(ids, ids)), dict(zip(ids, ids)))


def test_ambiguity_acceptance_keeps_whole_patterns_and_raw_coverage():
    ids = ["a", "b", "p1", "p2"]
    alternatives = [{"a": "A", "b": "B", "p1": owner, "p2": owner} for owner in ("A", "B", None)]
    accepted = output({"a": "x", "b": "y"})
    result = alternative_sensitivity(ids, alternatives, accepted, ambiguous=["p1", "p2"])
    assert result["ambiguity_acceptance"]["value"] == 1
    assert score_partition(ids, alternatives[0], accepted)["coverage"]["recognition"]["value"] == 0.5
    mixed = output({"a": "x", "b": "y", "p1": "x"})
    assert alternative_sensitivity(ids, alternatives, mixed, ambiguous=["p1", "p2"])["ambiguity_acceptance"]["value"] == 0


def test_stability_requires_declared_lineage_and_keeps_failures():
    old = output({"a": "A", "b": "A", "c": "B"})
    new = output({"moved": "renamed", "b": "renamed", "c": "other"})
    result = stability(["a", "b", "c"], ["moved", "b", "c"], {"a": "moved", "b": "b", "c": "c"}, old, new)
    assert result["value"] == 0 and result["denominator"] == 3
    with pytest.raises(ValueError):
        stability(["a", "b"], ["x"], {"a": "x", "b": "x"}, old, new)
    assert stability(["a"], ["moved"], {"a": "moved"}, old, new)["value"] is None
    assert stability(["a"], ["moved"], {"a": "moved"}, old, output({}, "failed"))["reason"] == "failed_or_unsupported_comparison"
    with pytest.raises(ValueError, match="changed source"):
        checked_lineage({"file_map": {"a": "old"}, "file_hashes": {"a": "one"}},
                        {"file_map": {"a": "new"}, "file_hashes": {"a": "two"}}, ["a"])


@pytest.fixture(scope="module")
def actual_runs(tmp_path_factory):
    root = tmp_path_factory.mktemp("membership-candidate")
    return {case: worker(case, 0, root / case) for case in ("base", "one-way", "cross-contract-cycle", "ambiguous-probes")}


def test_actual_source_runs_expose_pair_quality_and_coverage_together(actual_runs):
    base = actual_runs["base"]
    score = base["author_fixture_agreement"]
    assert score["pairs"]["metrics"]["f1"]["value"] == 1
    assert score["coverage"]["assignment"]["value"] == pytest.approx(4 / 6)
    assert score["alias_accuracy"]["value"] == 0
    assert base["semantic_quality"] == "not_run"
    assert base["observation_diagnostics"]["declared_cross_interaction_recall"]["value"] == 1
    assert base["dependency_retention"]["value"] == 0
    assert actual_runs["one-way"]["author_fixture_agreement"]["pairs"]["metrics"]["f1"]["value"] == pytest.approx(2 / 3)
    assert actual_runs["cross-contract-cycle"]["author_fixture_agreement"]["pairs"]["metrics"]["f1"]["value"] == 0.5
    assert actual_runs["ambiguous-probes"]["alternative_sensitivity"]["ambiguity_acceptance"]["value"] == 1


def test_observation_masks_keep_their_mechanics_lane(tmp_path):
    worker("base", 0, tmp_path)
    masked = json.loads((tmp_path / "observation-mask.json").read_text())
    assert masked["lane"] == "injected_observation_mechanics"
    assert masked["semantic_scores"]["value"] is None
    assert masked["group_count"] == 1


def test_scheduler_retains_all_failed_attempts(tmp_path, monkeypatch):
    import seremy.evaluate_membership as module
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="worker failed"))
    report = evaluate(tmp_path, repeats=1)
    assert report["execution_status"] == "failed"
    assert report["run_success"] == {"numerator": 0, "denominator": 6, "value": 0.0, "status": "computed", "reason": None}
    assert all(r["author_fixture_agreement"]["coverage"]["unassigned"]["value"] == 1 for r in report["source_runs"])
    assert all(c["status"] == "failed" for c in report["comparisons"])


def test_invalid_corpus_still_retains_scheduled_receipts(tmp_path, monkeypatch):
    import seremy.evaluate_membership as module
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="failed"))
    def invalid(*args):
        raise ValueError("invalid source edit")
    monkeypatch.setattr(module, "fixture_sources", invalid)
    report = evaluate(tmp_path, repeats=1)
    assert report["run_success"]["denominator"] == 6
    assert all(r["failure_phase"] == "invalid_corpus_input" and r["scoring"]["value"] is None for r in report["source_runs"])


def test_frozen_metric_reference_is_byte_identical():
    from seremy.contracts import sha256_hex
    assert sha256_hex((CORPUS / "frozen-metric-contract.md").read_bytes()) == "3d83667a79f5d369b736c469e4979239d9d6e06e827128fe7442695fa0feef7e"
