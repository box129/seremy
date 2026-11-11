"""Tests for seremy.bundle (T5: versioned graph bundle + loader)."""

import copy
import shutil
from pathlib import Path

import pytest

from seremy.contracts import AnalysisTextBlob, SourceBlob, canonical_bytes, sha256_hex
from seremy.discovery import discover
from seremy.parsing import run_adapter, build_parsed_results, artifact_digest
from seremy.resolver import Resolver
from seremy.bundle import (
    BUNDLE_FORMAT,
    BundleLoader,
    CorruptBundleError,
    StaleBundleError,
    _digest_artifact,
    build_bundle,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "redux-slice"
FILE_IDS = ["src/utils/isAction.ts", "src/utils/isPlainObject.ts"]

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the TypeScript adapter"
)


def _real_bundle():
    manifest = discover(FIXTURE_ROOT, repository_id="local:redux-slice")
    blobs = {}
    for fid in FILE_IDS:
        data = (FIXTURE_ROOT / fid).read_bytes()
        blob = SourceBlob(
            file_id=fid,
            raw_path=None,
            content_sha256=sha256_hex(data),
            byte_count=len(data),
            read_status="complete",
        )
        blobs[fid] = (AnalysisTextBlob.from_source(blob, data), data)
    results = build_parsed_results(run_adapter(FIXTURE_ROOT, FILE_IDS), blobs)
    rset = Resolver(results, expected_s02_digest=artifact_digest(results)).resolve()
    return build_bundle(manifest, results, rset)


@pytest.fixture(scope="module")
def bundle_document():
    return _real_bundle()


MILESTONE_TARGET = "ent:src/utils/isPlainObject.ts#function_declaration:isPlainObject@132"


# --- Determinism and round trip -----------------------------------------------


def test_bundle_build_is_deterministic():
    assert _real_bundle() == _real_bundle()


def test_write_and_reload_round_trip(bundle_document, tmp_path):
    path = tmp_path / "graph-bundle.json"
    loader = BundleLoader(bundle_document)
    loader.write(path)
    reloaded = BundleLoader.from_file(path)
    assert reloaded.meta == loader.meta
    assert reloaded.meta["content_digest"] == bundle_document["bundle"]["content_digest"]
    assert reloaded.meta["format"] == BUNDLE_FORMAT


def test_acceptance_is_honestly_pending(bundle_document):
    loader = BundleLoader(bundle_document)
    assert loader.acceptance_state == "pending_validation"
    assert bundle_document["bundle"]["checks"]["status"] == "not_run"


# --- Loader rejection of stale and corrupt input -------------------------------


def _tampered(document, mutator, resign: str = "none"):
    """resign levels:
    - "none": leave digests -> outermost content-digest check fires first
    - "meta": re-sign content+bundle digests -> embedded-record digest check fires
    - "full": also re-sign embedded artifact digests -> only the cross-binding
      layer can catch the mutation (a stale chain with consistent local digests)
    """
    clone = copy.deepcopy(document)
    mutator(clone)
    if resign in ("meta", "full"):
        meta, contents = clone["bundle"], clone["contents"]
        if resign == "full":
            for stage in ("s02", "s03"):
                record = contents[stage]
                record["digest"] = _digest_artifact(record["artifact"])
        meta["content_digest"] = sha256_hex(canonical_bytes(contents))
        meta["bundle_digest"] = sha256_hex(
            canonical_bytes(
                {"content_digest": meta["content_digest"], "checks": meta["checks"]}
            )
        )
    return clone


def test_content_digest_mismatch_rejected(bundle_document):
    def touch(clone):
        clone["contents"]["coverage"]["s03"]["candidate_count"] = 999

    with pytest.raises(StaleBundleError, match="content digest mismatch"):
        BundleLoader(_tampered(bundle_document, touch))


def test_embedded_artifact_digest_mismatch_rejected(bundle_document):
    def corrupt_s02(clone):
        clone["contents"]["s02"]["artifact"]["files"][0]["bucket"] = "failed"

    with pytest.raises(CorruptBundleError, match="s02 artifact digest mismatch"):
        BundleLoader(_tampered(bundle_document, corrupt_s02, resign="meta"))


def test_stale_s03_binding_rejected(bundle_document):
    def retarget(clone):
        # S03 now claims a different S02 digest than the one in the bundle.
        clone["contents"]["s03"]["artifact"]["binds"]["s02_artifact_digest"] = "0" * 64

    with pytest.raises(StaleBundleError, match="different S02 digest"):
        BundleLoader(_tampered(bundle_document, retarget, resign="full"))


def test_stale_s02_inventory_binding_rejected(bundle_document):
    def rebind(clone):
        clone["contents"]["snapshot"]["inventory_manifest_digest"] = "1" * 64

    with pytest.raises(StaleBundleError):
        BundleLoader(_tampered(bundle_document, rebind))


def test_bundle_digest_mismatch_rejected(bundle_document):
    def touch(clone):
        clone["bundle"]["checks"] = {"status": "passed", "roster": ["made_up_check"]}

    with pytest.raises(StaleBundleError, match="bundle digest mismatch"):
        BundleLoader(_tampered(bundle_document, touch))


# --- Consumer API --------------------------------------------------------------


def test_entity_lookup_distinguishes_missing_from_failed(bundle_document):
    loader = BundleLoader(bundle_document)
    present = "ent:src/utils/isAction.ts#function_declaration:isAction@116"
    assert loader.lookup_entity(present)["name"] == "isAction"
    # Well-formed but absent -> None (missing), not an error (failed).
    absent = "ent:src/utils/isAction.ts#function_declaration:nope@116"
    assert loader.lookup_entity(absent) is None
    # Malformed -> an explicit lookup failure.
    with pytest.raises(CorruptBundleError, match="malformed entity ID"):
        loader.lookup_entity("not-an-entity-id")


def test_milestone_edge_query(bundle_document):
    loader = BundleLoader(bundle_document)
    edges = loader.edges(
        source="ent:src/utils/isAction.ts#function_declaration:isAction@116",
        kind="CALLS",
        target=MILESTONE_TARGET,
    )
    assert len(edges) == 1
    assert edges[0]["origin"] == "binder_observation"


def test_occurrence_lookup(bundle_document):
    loader = BundleLoader(bundle_document)
    found = loader.occurrence(
        "cand:src/utils/isAction.ts#call:isPlainObject@185"
    )
    assert found is not None
    assert found["occurrence"]["span"] == [185, 198]


def test_citation_validation(bundle_document):
    loader = BundleLoader(bundle_document)
    is_action = loader._files["src/utils/isAction.ts"]
    assert loader.validate_citation(is_action["analysis_sha256"], (185, 198)) is True
    assert loader.validate_citation(is_action["analysis_sha256"], (300, 400)) is False
    assert loader.validate_citation("0" * 64, (0, 1)) is False  # unknown blob
    assert loader.validate_citation(is_action["analysis_sha256"], (5, 2)) is False


def test_embedded_artifact_digest_helper_excludes_self_report():
    artifact = {"a": 1, "artifact_digest": "whatever"}
    assert _digest_artifact(artifact) == _digest_artifact({"a": 1})
