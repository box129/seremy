"""Tests for seremy.staleness (T7: stale evidence rejection).

The exit check under assessment: change the call target and confirm
stale evidence is rejected.  Everything runs on a *copy* of the pinned
fixture so the recorded Redux revision stays untouched.
"""

import json
import shutil
from pathlib import Path

import pytest

from seremy.bundle import BundleLoader
from seremy.contracts import (
    AnalysisTextBlob,
    SourceBlob,
    Span,
    canonical_bytes,
    sha256_hex,
    slice_bytes,
)
from seremy.discovery import discover
from seremy.documentation import build_document_ir, validate_document
from seremy.parsing import run_adapter, build_parsed_results, artifact_digest
from seremy.resolver import Resolver
from seremy.staleness import check_staleness, citation_is_current, current_source_hashes

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the TypeScript adapter"
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "redux-slice"
ISACTION = "src/utils/isAction.ts"
ISPLAIN = "src/utils/isPlainObject.ts"
OLD_CALL_SPAN = (185, 198)  # the recorded isPlainObject callee occurrence


def _build_chain(root: Path, file_ids):
    manifest = discover(root, repository_id="local:staleness-check")
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
    results = build_parsed_results(run_adapter(root, file_ids), blobs)
    rset = Resolver(results, expected_s02_digest=artifact_digest(results)).resolve()
    from seremy.bundle import build_bundle

    return build_bundle(manifest, results, rset)


def _copy_fixture(tmp_path: Path, name: str) -> Path:
    copy_root = tmp_path / name
    shutil.copytree(FIXTURE_ROOT, copy_root)
    return copy_root


def _mutate_call_target(copy_root: Path) -> None:
    """Change the call target: isPlainObject(action) -> isThing(action)."""
    target = copy_root / ISACTION
    original = target.read_bytes()
    needle = b"isPlainObject(action) &&"
    assert original.count(needle) == 1
    mutated = original.replace(needle, b"isThing(action) &&")
    mutated += b"\nfunction isThing(action: unknown): boolean {\n  return typeof action === 'object'\n}\n"
    target.write_bytes(mutated)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("staleness")
    original_root = _copy_fixture(tmp, "original")
    document_original = _build_chain(original_root, [ISACTION, ISPLAIN])
    original_loader = BundleLoader(document_original)

    mutated_root = _copy_fixture(tmp, "mutated")
    _mutate_call_target(mutated_root)
    document_mutated = _build_chain(mutated_root, [ISACTION, ISPLAIN])
    mutated_loader = BundleLoader(document_mutated)

    return {
        "original_root": original_root,
        "original_loader": original_loader,
        "mutated_root": mutated_root,
        "mutated_loader": mutated_loader,
        "mutated_document": document_mutated,
    }


# --- Baseline currency ---------------------------------------------------------


def test_fresh_bundle_is_current_against_its_own_source(world):
    report = check_staleness(world["original_loader"], world["original_root"])
    assert report["stale"] is False
    assert report["changed_files"] == []
    assert citation_is_current(
        world["original_loader"], world["original_root"], ISACTION, OLD_CALL_SPAN
    )


# --- The exit check: changed call target ----------------------------------------


def test_changed_source_makes_old_bundle_stale(world):
    report = check_staleness(world["original_loader"], world["mutated_root"])
    assert report["stale"] is True
    assert report["changed_files"] == [ISACTION]
    assert report["missing_files"] == []


def test_changed_source_invalidates_the_old_citation(world):
    """The old citation's span no longer slices the same bytes, and the
    blob hash no longer matches the current file."""
    data = (world["mutated_root"] / ISACTION).read_bytes()
    assert slice_bytes(data, Span(*OLD_CALL_SPAN)).decode("utf-8") != "isPlainObject"
    assert citation_is_current(
        world["original_loader"], world["mutated_root"], ISACTION, OLD_CALL_SPAN
    ) is False
    assert citation_is_current(
        world["original_loader"],
        world["mutated_root"],
        ISACTION,
        OLD_CALL_SPAN,
        blob_sha256=sha256_hex((world["original_root"] / ISACTION).read_bytes()),
    ) is False


def test_rebuilt_chain_binds_the_new_source(world):
    mutated_loader = world["mutated_loader"]
    report = check_staleness(mutated_loader, world["mutated_root"])
    assert report["stale"] is False

    # Digests must differ from the original chain.
    assert (
        mutated_loader.meta["content_digest"]
        != world["original_loader"].meta["content_digest"]
    )
    # The new chain carries the mutated manifest digest.
    manifest_files = {
        r["file_id"]: r
        for r in mutated_loader.contents["inventory"]["eligible"]
    }
    assert manifest_files[ISACTION]["content_sha256"] == sha256_hex(
        (world["mutated_root"] / ISACTION).read_bytes()
    )


def test_new_bundle_binds_new_call_target_not_the_old(world):
    loader = world["mutated_loader"]
    edges = loader.edges(kind="CALLS")
    assert len(edges) == 1
    edge = edges[0]
    # The new call target: isThing, declared in the same file (appended).
    assert edge["target"].startswith("ent:src/utils/isAction.ts#function_declaration:isThing@")
    # The old isPlainObject edge is gone from the factual view.
    old_target = "ent:src/utils/isPlainObject.ts#function_declaration:isPlainObject@132"
    assert loader.edges(target=old_target) == []


def test_old_document_rejected_by_new_bundle(world):
    """The document generated on the old snapshot fails post-generation
    validation against the current bundle: stale evidence is rejected."""
    old_ir = build_document_ir(world["original_loader"])
    errors = validate_document(old_ir, world["mutated_loader"])
    assert errors, "stale document must produce citation errors"
    assert any("does not validate" in e or "absent" in e for e in errors)

    # The regenerated document on the current bundle validates cleanly.
    new_ir = build_document_ir(world["mutated_loader"])
    assert validate_document(new_ir, world["mutated_loader"]) == []
    # ...and the two documents differ (stale claims are not silently kept).
    from seremy.documentation import document_digest

    assert document_digest(old_ir) != document_digest(new_ir)


def test_mixed_chain_is_rejected_by_digest_discipline(world):
    """Old-stage artifacts cannot bind into the new chain."""
    old_s02_digest = world["original_loader"].contents["s02"]["digest"]
    data = (world["mutated_root"] / ISACTION).read_bytes()
    blob = SourceBlob(
        file_id=ISACTION,
        raw_path=None,
        content_sha256=sha256_hex(data),
        byte_count=len(data),
        read_status="complete",
    )
    blobs = {
        ISACTION: (
            AnalysisTextBlob.from_source(blob, data),
            data,
        )
    }
    results = build_parsed_results(
        run_adapter(world["mutated_root"], [ISACTION]), blobs
    )
    with pytest.raises(ValueError, match="S02 artifact digest mismatch"):
        Resolver(results, expected_s02_digest=old_s02_digest)
