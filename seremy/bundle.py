"""Graph bundle for the Milestone 1 slice.

Serializes the S01+S02+S03 chain into one versioned artifact bundle and
provides the loader both consumers (map, document) must use.

Identity follows the v1.1 addendum's three non-circular identities:

1. ``content_digest`` — canonical digest over the exact contents (snapshot
   identity, inventory records, S02 artifact, S03 artifact and coverage).
2. ``bundle_digest`` — binds the content digest and the check roster.  In
   this slice the roster is empty and honestly labelled ``not_run``; S07
   checks arrive with T6/T7.
3. Acceptance receipts are NOT produced here; the bundle is labelled
   ``pending_validation`` and must never be presented as accepted output.

The loader re-derives every digest from stored bytes:

- content digest mismatch -> stale or tampered bundle
- stored-artifact digest mismatch -> corrupted embedded artifact
- cross-binding mismatch (S02's bound manifest digest, S03's bound S02
  digest) -> stale chain, the mechanism T7's staleness check exploits.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from seremy.contracts import PROFILE_ID, canonical_bytes, sha256_hex
from seremy.discovery import InventoryManifest
from seremy.parsing import PRODUCER_PARSING, ParsedFileResult, artifact_digest as s02_results_digest
from seremy.resolver import ResolutionSet, artifact_digest as s03_set_digest
from seremy.language_profiles import SOURCE_EXTENSIONS, ECMASCRIPT_PROFILE, parsed_profile

PRODUCER_BUNDLE = "seremy.bundle/0.1"
BUNDLE_FORMAT = "seremy-graph-bundle-v0.1"


def _digest_artifact(artifact: dict) -> str:
    """Digest an embedded artifact, excluding its self-reporting digest key."""
    stripped = {key: value for key, value in artifact.items() if key != "artifact_digest"}
    return sha256_hex(canonical_bytes(stripped))


def build_bundle(
    manifest: InventoryManifest,
    results: List[ParsedFileResult],
    resolution_set: ResolutionSet,
    *,
    repository_id: Optional[str] = None,
) -> dict:
    """Assemble the immutable bundle document (not yet written anywhere)."""
    manifest_digest = manifest.manifest_digest()
    manifest.reconcile()

    profile_id=ECMASCRIPT_PROFILE if manifest.profile_id==ECMASCRIPT_PROFILE else parsed_profile(results)
    s02_artifact = {
        "profile": profile_id,
        "producer": PRODUCER_PARSING,
        "position_map": "identity-utf8-v1",
        "files": sorted(
            (r.to_artifact_record() for r in results), key=lambda r: r["file_id"]
        ),
    }
    s02_digest = _digest_artifact(s02_artifact)
    # Cross-check: the embedded S02 digest must equal the digest computed
    # from the in-memory results (the value S03 bound).
    if s02_digest != s02_results_digest(results,profile_id=profile_id):
        raise AssertionError("embedded S02 projection disagrees with S02 digest")

    s03_artifact = resolution_set.to_artifact(
        manifest_digest=manifest_digest, s02_digest=s02_digest
    )
    s03_digest = _digest_artifact(s03_artifact)
    if s03_digest != s03_set_digest(s03_artifact):
        raise AssertionError("embedded S03 projection disagrees with S03 digest")

    # Source blobs bind the parsed files back to inventory identity: the
    # S02 result must reference exactly the manifest's content hash, and
    # the byte count comes from the manifest record (read boundary).
    manifest_files = {r.file_id: r for r in manifest.eligible}
    source_blobs = {}
    for result in results:
        record = manifest_files.get(result.file_id)
        if record is None:
            raise ValueError(f"S02 result references a file outside the manifest: {result.file_id}")
        if record.content_sha256 != result.source_sha256:
            raise ValueError(
                f"S02 result does not bind the inventory blob for {result.file_id}"
            )
        source_blobs[result.file_id] = {
            "analysis_sha256": result.analysis_sha256,
            "source_sha256": result.source_sha256,
            "byte_count": record.byte_count,
        }

    contents = {
        "format": BUNDLE_FORMAT,
        "profile": profile_id,
        "snapshot": {
            "repository_id": repository_id or manifest.repository_id,
            "declared_root": manifest.declared_root,
            "inventory_manifest_digest": manifest_digest,
            "position_map": "identity-utf8-v1",
            "source_blobs": dict(sorted(source_blobs.items())),
        },
        "inventory": {
            "manifest_digest": manifest_digest,
            "input_count": manifest.input_count,
            "excluded_count": manifest.excluded_count,
            "eligible_count": manifest.eligible_count,
            "eligible": sorted(
                (
                    {
                        "file_id": r.file_id,
                        "content_sha256": r.content_sha256,
                        "byte_count": r.byte_count,
                        "bucket": r.bucket,
                        "reason": r.reason,
                    }
                    for r in manifest.eligible
                ),
                key=lambda item: item["file_id"],
            ),
            "exclusions": sorted(
                ({"path": e.path, "reason": e.reason} for e in manifest.exclusions),
                key=lambda item: (item["path"], item["reason"]),
            ),
        },
        "s02": {"digest": s02_digest, "artifact": s02_artifact},
        "s03": {"digest": s03_digest, "artifact": s03_artifact},
        "coverage": {
            "units": "per-stage declared units (files; parsed-file records; candidate IDs)",
            "inventory": {
                "input_count": manifest.input_count,
                "excluded_count": manifest.excluded_count,
                "eligible_count": manifest.eligible_count,
            },
            "s02": {
                "parsed_file_records": len(results),
                "source_file_count": sum(r.file_id.endswith(SOURCE_EXTENSIONS) for r in manifest.eligible),
                "not_processed": sum(r.file_id.endswith(SOURCE_EXTENSIONS) and
                                     r.file_id not in {p.file_id for p in results} for r in manifest.eligible),
                "complete": sum(1 for r in results if r.bucket == "complete"),
                "partial": sum(1 for r in results if r.bucket == "partial"),
                "failed": sum(1 for r in results if r.bucket == "failed"),
            },
            "s03": {
                "candidate_count": len(resolution_set.resolutions),
                "attempted_count": resolution_set.attempted_count(),
                "outcome_counts": dict(sorted(resolution_set.outcome_counts().items())),
                "direct_edge_count": len(resolution_set.edges),
            },
        },
    }

    content_digest = sha256_hex(canonical_bytes(contents))
    checks = {"status": "not_run", "roster": []}
    bundle_digest = sha256_hex(canonical_bytes({"content_digest": content_digest, "checks": checks}))

    return {
        "bundle": {
            "format": BUNDLE_FORMAT,
            "profile": profile_id,
            "producer": PRODUCER_BUNDLE,
            "content_digest": content_digest,
            "checks": checks,
            "acceptance_state": "pending_validation",
            "bundle_digest": bundle_digest,
        },
        "contents": contents,
    }


def _byte_count_from(results: List[ParsedFileResult], file_id: str) -> int:
    for result in results:
        if result.file_id == file_id:
            return result.analysis_length if hasattr(result, "analysis_length") else 0
    raise KeyError(file_id)


class BundleError(Exception):
    """Base for bundle loading failures with distinct reasons."""


class StaleBundleError(BundleError):
    pass


class CorruptBundleError(BundleError):
    pass


class BundleLoader:
    """The single loader both consumers must use."""

    def __init__(self, document: dict):
        self.document = document
        self._validate()

    @staticmethod
    def from_file(path: Path) -> "BundleLoader":
        return BundleLoader(json.loads(Path(path).read_text(encoding="utf-8")))

    def write(self, path: Path) -> None:
        Path(path).write_text(
            json.dumps(self.document, indent=2) + "\n", encoding="utf-8"
        )

    # -- validation -----------------------------------------------------------

    def _validate(self) -> None:
        meta = self.document.get("bundle")
        contents = self.document.get("contents")
        if not isinstance(meta, dict) or not isinstance(contents, dict):
            raise CorruptBundleError("missing bundle metadata or contents")
        if meta.get("format") != BUNDLE_FORMAT:
            raise CorruptBundleError(f"unknown bundle format: {meta.get('format')!r}")
        if meta.get("acceptance_state") != "pending_validation":
            raise CorruptBundleError("this bundle profile requires a detached acceptance process")

        # 1. Content digest over the exact stored contents.
        computed = sha256_hex(canonical_bytes(contents))
        if computed != meta.get("content_digest"):
            raise StaleBundleError(
                f"content digest mismatch: stored {meta.get('content_digest')} != computed {computed}"
            )

        # 2. Embedded artifact digests.
        for stage in ("s02", "s03"):
            record = contents.get(stage)
            if not isinstance(record, dict) or "digest" not in record or "artifact" not in record:
                raise CorruptBundleError(f"missing {stage} record")
            if _digest_artifact(record["artifact"]) != record["digest"]:
                raise CorruptBundleError(f"{stage} artifact digest mismatch")

        # 3. Cross-bindings: stale chain detection.
        snapshot = contents["snapshot"]
        inventory = contents["inventory"]
        if inventory.get("manifest_digest") != snapshot.get("inventory_manifest_digest"):
            raise StaleBundleError("inventory digest disagrees with snapshot identity")
        if contents["s02"]["artifact"].get("binds", {}).get("inventory_manifest_digest") not in (
            None,
            snapshot["inventory_manifest_digest"],
        ):
            raise StaleBundleError("S02 artifact binds a different inventory manifest")
        s02_digest = contents["s02"]["digest"]
        s03_binds = contents["s03"]["artifact"].get("binds", {})
        if s03_binds.get("s02_artifact_digest") != s02_digest:
            raise StaleBundleError("S03 artifact binds a different S02 digest")
        if s03_binds.get("inventory_manifest_digest") != snapshot["inventory_manifest_digest"]:
            raise StaleBundleError("S03 artifact binds a different inventory manifest")

        # 4. Bundle digest binds content digest and check roster.
        expected_bundle = sha256_hex(
            canonical_bytes(
                {"content_digest": meta["content_digest"], "checks": meta["checks"]}
            )
        )
        if expected_bundle != meta.get("bundle_digest"):
            raise StaleBundleError("bundle digest mismatch")

        self.contents = contents
        self.meta = meta
        self._entities = {
            e["entity_id"]: e for e in contents["s03"]["artifact"]["entities"]
        }
        self._edges = contents["s03"]["artifact"]["edges"]
        self._files = snapshot["source_blobs"]
        self._blob_to_file = {
            record["analysis_sha256"]: file_id
            for file_id, record in self._files.items()
        }
        self._inventory_files = {
            r["file_id"]: r for r in inventory["eligible"]
        }

    # -- consumer API -----------------------------------------------------------

    @property
    def acceptance_state(self) -> str:
        return self.meta["acceptance_state"]

    def entity_ids(self) -> List[str]:
        return sorted(self._entities)

    def file_ids(self) -> List[str]:
        return sorted(self._inventory_files)

    def lookup_entity(self, entity_id: str) -> Optional[dict]:
        """Well-formed but absent ID -> None; malformed -> CorruptBundleError.

        A missing relationship and a failed lookup stay distinguishable.
        """
        if not entity_id.startswith("ent:"):
            raise CorruptBundleError(f"malformed entity ID: {entity_id!r}")
        return self._entities.get(entity_id)

    def lookup_file(self, file_id: str) -> Optional[dict]:
        if not file_id or ".." in file_id:
            raise CorruptBundleError(f"malformed file ID: {file_id!r}")
        return self._inventory_files.get(file_id)

    def edges(
        self,
        *,
        source: Optional[str] = None,
        kind: Optional[str] = None,
        target: Optional[str] = None,
    ) -> List[dict]:
        return [
            edge
            for edge in self._edges
            if (source is None or edge["source"] == source)
            and (kind is None or edge["kind"] == kind)
            and (target is None or edge["target"] == target)
        ]

    def occurrence(self, candidate_id: str) -> Optional[dict]:
        for edge in self._edges:
            for occ in edge["occurrences"]:
                if occ["candidate_id"] == candidate_id:
                    return {"edge": edge, "occurrence": occ}
        return None

    def validate_citation(self, blob_sha256: str, span: Tuple[int, int]) -> bool:
        """A citation is valid only if the blob belongs to this snapshot and
        the span is inside it.  Changed blobs invalidate old citations."""
        file_id = self._blob_to_file.get(blob_sha256)
        if file_id is None:
            return False
        start, end = span
        return 0 <= start <= end <= self._files[file_id]["byte_count"]
