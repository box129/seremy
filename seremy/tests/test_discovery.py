"""Tests for seremy.discovery (T2: S01 mini-discovery)."""

import hashlib
import json
from pathlib import Path

import pytest

from seremy.contracts import sha256_hex
from seremy.discovery import DiscoveryPolicy, discover

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "redux-slice"
FIXTURE_MANIFEST = FIXTURE_ROOT / "fixture-manifest.json"


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


# --- The real fixture slice --------------------------------------------------


def test_fixture_slice_inventory_and_provenance():
    manifest = discover(FIXTURE_ROOT, repository_id="local:redux-slice")

    # 17 .ts files eligible; fixture provenance and license retained as exclusions.
    assert manifest.eligible_count == 17
    assert all(record.bucket == "complete" for record in manifest.eligible)
    assert manifest.excluded_count == 2  # fixture manifest and bundled Redux license
    assert {(e.path,e.reason) for e in manifest.exclusions} == {
        ("fixture-manifest.json","excluded_extension"), ("LICENSE.md","excluded_extension")}
    manifest.reconcile()  # input = excluded + eligible

    by_id = {record.file_id: record for record in manifest.eligible}
    assert "src/utils/isAction.ts" in by_id
    assert "src/utils/isPlainObject.ts" in by_id

    recorded = {f["path"]: f for f in json.loads(FIXTURE_MANIFEST.read_text())["files"]}
    for file_id, record in by_id.items():
        expected = recorded[file_id]
        assert record.content_sha256 == expected["sha256"]
        assert record.byte_count == expected["byte_count"]

    # Fresh-source integrity: re-derive the Git blob SHA-1 from local bytes
    # and match the recorded revision identity (T0 exit check re-checked).
    for file_id in ("src/utils/isAction.ts", "src/utils/isPlainObject.ts"):
        data = (FIXTURE_ROOT / file_id).read_bytes()
        assert _git_blob_sha1(data) == recorded[file_id]["git_blob_sha1"]


def test_manifest_digest_is_reproducible():
    first = discover(FIXTURE_ROOT).manifest_digest()
    second = discover(FIXTURE_ROOT).manifest_digest()
    assert first == second
    # Content sensitivity is covered by test_manifest_digest_changes_when_content_changes.


def test_discovery_on_synthetic_tree():
    # Synthetic tree in tmp_path: exercises exclusions, pruned subtrees,
    # read limits and accounting without touching the pinned fixture.
    tree = tmp_path_factory("seremy-discovery-synthetic")
    (tree / "pkg").mkdir(parents=True)
    (tree / "pkg" / "a.ts").write_bytes(b"export const a = 1;\n")
    (tree / "pkg" / "notes.md").write_bytes(b"# notes")
    (tree / "pkg" / "node_modules").mkdir()
    (tree / "pkg" / "node_modules" / "dep.ts").write_bytes(b"export const dep = 2;")
    (tree / "pkg" / "big.ts").write_bytes(b"x" * 26)

    policy = DiscoveryPolicy(max_file_bytes=25)
    manifest = discover(tree, repository_id="local:synthetic", policy=policy)

    eligible_ids = {record.file_id: record for record in manifest.eligible}
    # node_modules contents are never enumerated; the pruned directory is
    # excluded at directory granularity.
    assert set(eligible_ids) == {"pkg/a.ts", "pkg/big.ts"}
    assert eligible_ids["pkg/a.ts"].bucket == "complete"
    assert eligible_ids["pkg/a.ts"].content_sha256 == sha256_hex(b"export const a = 1;\n")
    assert eligible_ids["pkg/big.ts"].bucket == "not_processed"
    assert eligible_ids["pkg/big.ts"].reason == "read_limit"
    assert eligible_ids["pkg/big.ts"].content_sha256 is None  # sample hash cannot attest

    excluded = {(e.path, e.reason) for e in manifest.exclusions}
    assert excluded == {
        ("pkg/node_modules", "excluded_directory"),
        ("pkg/notes.md", "excluded_extension"),
    }
    assert manifest.input_count == manifest.excluded_count + manifest.eligible_count
    assert manifest.input_count == 4
    manifest.reconcile()

    digest = manifest.manifest_digest()
    assert len(digest) == 64


def test_manifest_digest_changes_when_content_changes():
    tree = tmp_path_factory("seremy-discovery-digest")
    (tree / "a.ts").write_bytes(b"export const a = 1;\n")
    before = discover(tree).manifest_digest()
    (tree / "a.ts").write_bytes(b"export const a = 2;\n")
    after = discover(tree).manifest_digest()
    assert before != after


def test_empty_directory_yields_accounted_zero_population():
    tree = tmp_path_factory("seremy-discovery-empty")
    manifest = discover(tree)
    assert manifest.input_count == 0
    manifest.reconcile()  # empty output is accounted, not treated as proof of absence


def tmp_path_factory(name: str) -> Path:
    """Deterministic per-test scratch directory."""
    import tempfile

    base = Path(tempfile.gettempdir()) / "seremy-test-trees"
    tree = base / name
    if tree.exists():
        import shutil

        shutil.rmtree(tree)
    tree.mkdir(parents=True)
    return tree
