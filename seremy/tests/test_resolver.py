"""Tests for seremy.resolver (T4: S03 dependency resolution)."""

import shutil
from pathlib import Path

import pytest

from seremy.contracts import sha256_hex, slice_bytes
from seremy.discovery import discover
from seremy.contracts import AnalysisTextBlob, SourceBlob
from seremy.parsing import run_adapter, build_parsed_results, artifact_digest as s02_digest
from seremy.resolver import (
    AMBIGUOUS,
    EXTERNAL,
    MISSING,
    NOT_PROCESSED,
    RESOLVED_SINGLE,
    TERMINAL_STATES,
    UNSUPPORTED,
    Resolver,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "redux-slice"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the TypeScript adapter"
)


def _pipeline(root: Path, file_ids):
    blobs = {}
    for fid in file_ids:
        data = (root / fid).read_bytes()
        blob = SourceBlob(
            file_id=fid,
            raw_path=None,
            content_sha256=sha256_hex(data),
            byte_count=len(data),
            read_status="complete",
        )
        blobs[fid] = (AnalysisTextBlob.from_source(blob, data), data)
    adapter_output = run_adapter(root, file_ids)
    results = build_parsed_results(adapter_output, blobs)
    return results


# --- The real fixture slice --------------------------------------------------


@pytest.fixture(scope="module")
def fixture_set():
    file_ids = ["src/utils/isAction.ts", "src/utils/isPlainObject.ts"]
    results = _pipeline(FIXTURE_ROOT, file_ids)
    return Resolver(results, expected_s02_digest=s02_digest(results)).resolve()


def test_milestone_call_resolves_to_real_declaration(fixture_set):
    """The Milestone 1 binding: isAction CALLS isPlainObject, statically."""
    edges = [
        e
        for e in fixture_set.edges
        if e.target == "ent:src/utils/isPlainObject.ts#function_declaration:isPlainObject@132"
    ]
    assert len(edges) == 1
    edge = edges[0]
    assert edge.source == "ent:src/utils/isAction.ts#function_declaration:isAction@116"
    assert edge.kind == "CALLS"
    assert edge.origin == "binder_observation"
    assert len(edge.occurrences) == 1
    occurrence = edge.occurrences[0]
    data = (FIXTURE_ROOT / "src" / "utils" / "isAction.ts").read_bytes()
    # Fresh-source check: the occurrence span slices the real callee bytes.
    assert slice_bytes(data, occurrence.span).decode("utf-8") == "isPlainObject"
    assert occurrence.evidence.blob_sha256 == sha256_hex(data)
    assert occurrence.evidence.method == "typescript-checker-v0.2"


def test_every_candidate_has_one_terminal_record(fixture_set):
    ids = [r.candidate_id for r in fixture_set.resolutions]
    assert len(ids) == len(set(ids))
    assert all(r.outcome in TERMINAL_STATES for r in fixture_set.resolutions)


def test_member_calls_unsupported_not_guessed(fixture_set):
    """getPrototypeOf member calls must not be bound by name heuristics."""
    records = [
        r for r in fixture_set.resolutions if r.candidate_kind == "member_call"
    ]
    assert len(records) == 4
    assert all(r.outcome == UNSUPPORTED for r in records)
    assert all(r.reason == "receiver_unbound_no_type_information" for r in records)


def test_outcome_coverage_reported(fixture_set):
    counts = fixture_set.outcome_counts()
    total = sum(counts.values())
    assert total == len(fixture_set.resolutions)
    assert counts.get(RESOLVED_SINGLE, 0) >= 1
    assert counts.get(UNSUPPORTED, 0) == 4
    assert counts.get(NOT_PROCESSED, 0) == 4  # 2 specifiers + 2 import names
    assert fixture_set.attempted_count() == counts.get(RESOLVED_SINGLE, 0) + counts.get(
        UNSUPPORTED, 0
    )


# --- Synthetic state-model cases ---------------------------------------------


def _resolver_for(tree: Path, file_ids):
    results = _pipeline(tree, file_ids)
    return Resolver(results, expected_s02_digest=s02_digest(results))


def test_recursive_call_is_retained_as_self_loop(tmp_path):
    (tmp_path / "rec.ts").write_bytes(
        b"export function fact(n: number): number {\n"
        b"  return n <= 1 ? 1 : n * fact(n - 1);\n"
        b"}\n"
    )
    rset = _resolver_for(tmp_path, ["rec.ts"]).resolve()
    call_records = [r for r in rset.resolutions if r.candidate_kind == "call"]
    assert len(call_records) == 1
    assert call_records[0].outcome == RESOLVED_SINGLE
    # Self-loop edges are legitimate and must not be discarded.
    assert len(rset.edges) == 1
    edge = rset.edges[0]
    assert edge.source == edge.target
    assert edge.source == "ent:rec.ts#function_declaration:fact@16"
    assert len(edge.occurrences) == 1


def test_invalid_default_import_does_not_bind_unrelated_declarations(tmp_path):
    (tmp_path / "b.ts").write_bytes(
        b"export function n(): number { return 1; }\n"
        b"export function n2(): number { return 2; }\n"
        b"export function n(): number { return 3; }\n"
    )
    (tmp_path / "a.ts").write_bytes(b"import n from './b';\nexport function go(): number {\n  return n();\n}\n")
    rset = _resolver_for(tmp_path, ["a.ts", "b.ts"]).resolve()
    go_call = [r for r in rset.resolutions if r.name == "n" and r.candidate_kind == "call"]
    assert len(go_call) == 1
    record = go_call[0]
    assert record.outcome == MISSING
    assert record.reason == "unresolved_import"
    assert not record.alternatives
    # Factual views exclude ambiguous alternatives: no edge may be emitted.
    assert rset.edges == []


def test_missing_when_no_binding_within_profile(tmp_path):
    (tmp_path / "solo.ts").write_bytes(
        b"export function go(): number {\n  return nowhere();\n}\n"
    )
    rset = _resolver_for(tmp_path, ["solo.ts"]).resolve()
    record = [r for r in rset.resolutions if r.candidate_kind == "call"][0]
    assert record.outcome == MISSING
    assert record.reason == "no_binding_within_profile"
    assert record.attempted is True
    assert rset.edges == []


def test_bare_specifier_is_external(tmp_path):
    (tmp_path / "s.ts").write_bytes(
        b"import pick from 'random-pkg';\nexport function go(): number {\n  return pick();\n}\n"
    )
    rset = _resolver_for(tmp_path, ["s.ts"]).resolve()
    record = [r for r in rset.resolutions if r.candidate_kind == "call"][0]
    assert record.outcome == EXTERNAL
    assert record.reason == "bare_specifier"
    assert record.target == "random-pkg"
    assert record.target_type == "external_ref"


def test_unresolved_relative_path_is_missing(tmp_path):
    (tmp_path / "s.ts").write_bytes(
        b"import pick from './nope';\nexport function go(): number {\n  return pick();\n}\n"
    )
    rset = _resolver_for(tmp_path, ["s.ts"]).resolve()
    record = [r for r in rset.resolutions if r.candidate_kind == "call"][0]
    assert record.outcome == MISSING
    assert record.reason == "unresolved_import"


def test_default_import_without_export_has_no_call_endpoint(tmp_path):
    (tmp_path / "empty.ts").write_bytes(b"export const config = {};\n")
    (tmp_path / "s.ts").write_bytes(
        b"import helper from './empty';\nexport function go(): number {\n  return helper();\n}\n"
    )
    rset = _resolver_for(tmp_path, ["s.ts", "empty.ts"]).resolve()
    record = [r for r in rset.resolutions if r.candidate_kind == "call"][0]
    assert record.outcome == MISSING
    assert record.reason == "unresolved_import"
    assert record.target is None
    assert not rset.edges


# --- Binding discipline -------------------------------------------------------


def test_s02_digest_mismatch_rejected():
    results = _pipeline(FIXTURE_ROOT, ["src/utils/isAction.ts"])
    with pytest.raises(ValueError, match="S02 artifact digest mismatch"):
        Resolver(results, expected_s02_digest="stale-digest")


def test_artifact_round_trip_and_digest(fixture_set):
    artifact = fixture_set.to_artifact(
        manifest_digest="pending-t5", s02_digest="pending-t5"
    )
    from seremy.resolver import artifact_digest as s03_digest

    assert len(s03_digest(artifact)) == 64
    coverage = artifact["coverage"]
    assert coverage["candidate_count"] == len(fixture_set.resolutions)
    assert coverage["attempted_count"] == fixture_set.attempted_count()
    assert sum(coverage["outcome_counts"].values()) == coverage["candidate_count"]
