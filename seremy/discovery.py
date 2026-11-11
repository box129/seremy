"""S01 file discovery for the Milestone 1 slice.

Implements a bounded, policy-driven plain-directory walk producing the
contract handoff artifacts: InventoryManifest + EligibleFile records +
Exclusion diagnostics.  Profile policy is declared in seremy/PROFILE.md.

Accounting follows contract section 4: every enumerated input is either
excluded by a recorded rule or eligible, and each eligible unit receives
exactly one execution bucket.  Empty output is never treated as proof that
no entities exist; a bounded frontier would be reported separately (none
exists for a complete plain walk).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from seremy.contracts import (
    POSITION_MAP_ID,
    PROFILE_ID,
    S01_ACCOUNTING_UNITS,
    EligibleFileRecord,
    SourceBlob,
    canonical_bytes,
    reconcile_accounting,
    sha256_hex,
)

PRODUCER_DISCOVERY = "seremy.discovery/0.1"

DEFAULT_EXCLUDED_DIRS = frozenset({".git", "node_modules", "dist", ".seremy-artifacts"})
DEFAULT_INCLUDED_EXTENSIONS = frozenset({".ts"})
DEFAULT_MAX_FILE_BYTES = 1_048_576  # 1 MiB, per PROFILE.md


@dataclass(frozen=True)
class DiscoveryPolicy:
    included_extensions: frozenset = DEFAULT_INCLUDED_EXTENSIONS
    excluded_dirs: frozenset = DEFAULT_EXCLUDED_DIRS
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES

    def __post_init__(self) -> None:
        if self.max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")


@dataclass(frozen=True)
class ExclusionRecord:
    """An input excluded by a recorded eligibility rule (contract section 4)."""

    path: str  # repository-relative POSIX path
    reason: str  # e.g. "excluded_directory", "excluded_extension"


@dataclass
class InventoryManifest:
    """S01 handoff: snapshot identity plus the scheduled population."""

    repository_id: str
    declared_root: str
    policy: DiscoveryPolicy
    exclusions: List[ExclusionRecord] = field(default_factory=list)
    eligible: List[EligibleFileRecord] = field(default_factory=list)
    excluded_by_reason: Dict[str, int] = field(default_factory=dict)
    not_processed_by_reason: Dict[str, int] = field(default_factory=dict)
    profile_id: str = PROFILE_ID
    producer: str = PRODUCER_DISCOVERY
    accounting_units: str = S01_ACCOUNTING_UNITS

    @property
    def input_count(self) -> int:
        return len(self.exclusions) + len(self.eligible)

    @property
    def excluded_count(self) -> int:
        return len(self.exclusions)

    @property
    def eligible_count(self) -> int:
        return len(self.eligible)

    def reconcile(self) -> None:
        """Raise unless every accounting invariant holds (contract section 4)."""
        reconcile_accounting(self.input_count, self.excluded_count, self.eligible_count)
        reasons: Dict[str, int] = {}
        for exclusion in self.exclusions:
            reasons[exclusion.reason] = reasons.get(exclusion.reason, 0) + 1
        if reasons != self.excluded_by_reason:
            raise AssertionError("excluded_by_reason does not match exclusion records")
        not_processed: Dict[str, int] = {}
        for record in self.eligible:
            if record.bucket == "not_processed":
                key = record.reason or "unspecified"
                not_processed[key] = not_processed.get(key, 0) + 1
        if not_processed != self.not_processed_by_reason:
            raise AssertionError("not_processed_by_reason does not match records")

    def manifest_digest(self) -> str:
        """Deterministic digest over the canonical manifest projection.

        Raw artifacts keep their own hashes; this digest addresses the
        sorted canonical record set (contract section 1).
        """
        self.reconcile()
        payload = {
            "profile_id": self.profile_id,
            "producer": self.producer,
            "repository_id": self.repository_id,
            "declared_root": self.declared_root,
            "accounting_units": self.accounting_units,
            "position_map": POSITION_MAP_ID,
            "policy": {
                "included_extensions": sorted(self.policy.included_extensions),
                "excluded_dirs": sorted(self.policy.excluded_dirs),
                "max_file_bytes": self.policy.max_file_bytes,
            },
            "exclusions": sorted(
                ({"path": e.path, "reason": e.reason} for e in self.exclusions),
                key=lambda item: (item["path"], item["reason"]),
            ),
            "eligible": sorted(
                (
                    {
                        "file_id": r.file_id,
                        "content_sha256": r.content_sha256,
                        "byte_count": r.byte_count,
                        "bucket": r.bucket,
                        "reason": r.reason,
                    }
                    for r in self.eligible
                ),
                key=lambda item: item["file_id"],
            ),
            "excluded_by_reason": dict(sorted(self.excluded_by_reason.items())),
            "not_processed_by_reason": dict(sorted(self.not_processed_by_reason.items())),
        }
        return sha256_hex(canonical_bytes(payload))


def discover(
    root: Path,
    *,
    repository_id: str = "local:redux-slice",
    policy: Optional[DiscoveryPolicy] = None,
) -> InventoryManifest:
    """Walk a plain directory and produce the S01 inventory manifest."""
    policy = policy or DiscoveryPolicy()
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"declared root is not a directory: {root}")

    manifest = InventoryManifest(
        repository_id=repository_id,
        declared_root=root.as_posix(),
        policy=policy,
    )

    for current, dirnames, filenames in os.walk(root):
        pruned = sorted(name for name in dirnames if name in policy.excluded_dirs)
        dirnames[:] = sorted(name for name in dirnames if name not in policy.excluded_dirs)

        # A pruned directory and its contents are excluded at directory
        # granularity; its files are never enumerated as inputs.
        for name in pruned:
            rel = (Path(current) / name).relative_to(root).as_posix()
            manifest.exclusions.append(
                ExclusionRecord(path=rel, reason="excluded_directory")
            )

        for filename in sorted(filenames):
            file_path = Path(current) / filename
            rel_path = file_path.relative_to(root).as_posix()
            if file_path.suffix.lower() not in policy.included_extensions:
                manifest.exclusions.append(
                    ExclusionRecord(path=rel_path, reason="excluded_extension")
                )
                continue

            try:
                byte_count = file_path.stat().st_size
            except OSError as error:
                manifest.eligible.append(
                    EligibleFileRecord(
                        file_id=rel_path,
                        content_sha256=None,
                        byte_count=None,
                        bucket="failed",
                        reason=f"stat_error:{error.__class__.__name__}",
                    )
                )
                continue

            if byte_count > policy.max_file_bytes:
                # Eligible but never read: sample hashes cannot attest a
                # complete read (v1.1 addendum).  Not read at all maps to
                # not_processed (execution not_started) with a reason.
                manifest.eligible.append(
                    EligibleFileRecord(
                        file_id=rel_path,
                        content_sha256=None,
                        byte_count=byte_count,
                        bucket="not_processed",
                        reason="read_limit",
                    )
                )
                continue

            try:
                data = file_path.read_bytes()
            except OSError as error:
                manifest.eligible.append(
                    EligibleFileRecord(
                        file_id=rel_path,
                        content_sha256=None,
                        byte_count=None,
                        bucket="failed",
                        reason=f"read_error:{error.__class__.__name__}",
                    )
                )
                continue

            manifest.eligible.append(
                EligibleFileRecord(
                    file_id=rel_path,
                    content_sha256=sha256_hex(data),
                    byte_count=len(data),
                    bucket="complete",
                )
            )

    manifest.excluded_by_reason = _count_reasons(manifest.exclusions)
    manifest.not_processed_by_reason = _count_not_processed(manifest.eligible)
    manifest.reconcile()
    return manifest


def _count_reasons(exclusions: List[ExclusionRecord]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for record in exclusions:
        counts[record.reason] = counts.get(record.reason, 0) + 1
    return counts


def _count_not_processed(eligible: List[EligibleFileRecord]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for record in eligible:
        if record.bucket == "not_processed":
            key = record.reason or "unspecified"
            counts[key] = counts.get(key, 0) + 1
    return counts


def source_blobs_from_manifest(
    manifest: InventoryManifest, root: Path
) -> Dict[str, SourceBlob]:
    """Build SourceBlob records for every completely-read eligible file."""
    blobs: Dict[str, SourceBlob] = {}
    for record in manifest.eligible:
        if record.bucket != "complete":
            continue
        data = (root / record.file_id).read_bytes()
        blobs[record.file_id] = SourceBlob(
            file_id=record.file_id,
            raw_path=None,
            content_sha256=sha256_hex(data),
            byte_count=len(data),
            read_status="complete",
        )
    return blobs
