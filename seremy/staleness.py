"""Staleness detection for the Milestone 1 slice.

A loaded bundle is only current while its snapshot source blobs still
describe the declared root.  This module compares the bundle's recorded
blob hashes against the current bytes on disk and reports:

- ``changed_files`` — a file exists but its bytes no longer hash to the
  recorded analysis blob.  Every citation tied to that blob is stale:
  recovery alone does not revalidate changed content (contract section 6).
- ``missing_files`` — a file present in the snapshot has vanished.
- ``citation_is_current`` — a single citation re-check: current blob hash
  matches the bundle's and the span is inside the current file.

The bundle itself stays immutable and internally consistent — staleness
is a property of the bundle *relative to the current source*, never
something repaired in place.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from seremy.bundle import BundleLoader
from seremy.contracts import sha256_hex
from seremy.language_profiles import ECMASCRIPT_PRODUCT_PROFILE, ECMASCRIPT_BINDING_PROFILE


def current_source_hashes(loader: BundleLoader, root: Path) -> dict:
    """Recompute the SHA-256 of every snapshot file from current bytes."""
    root = Path(root)
    state = {}
    for file_id, record in loader.contents["snapshot"]["source_blobs"].items():
        path = root / file_id
        if not path.is_file():
            state[file_id] = None
        else:
            state[file_id] = sha256_hex(path.read_bytes())
    return state


def check_staleness(loader: BundleLoader, root: Path) -> dict:
    """Compare the loaded bundle against the current declared root."""
    changed: List[str] = []
    missing: List[str] = []
    for file_id, current in current_source_hashes(loader, root).items():
        if current is None:
            missing.append(file_id)
        elif current != loader.contents["snapshot"]["source_blobs"][file_id]["analysis_sha256"]:
            changed.append(file_id)
    config_changed = _compiler_config_changed(loader, root)
    return {
        "stale": bool(changed or missing or config_changed),
        "config_changed": config_changed,
        "changed_files": sorted(changed),
        "missing_files": sorted(missing),
    }


def _compiler_config_changed(loader: BundleLoader, root: Path) -> bool:
    config = Path(root) / "tsconfig.json"
    config_hash = sha256_hex(config.read_bytes()) if config.is_file() else None
    if loader.contents.get("profile")==ECMASCRIPT_PRODUCT_PROFILE:
        return loader.contents["snapshot"].get("metadata_blobs",{}).get("tsconfig.json")!=config_hash
    return any(
        candidate.get("binding", {}).get("context", {}).get("config_sha256") != config_hash
        for parsed in loader.contents["s02"]["artifact"]["files"]
        for candidate in parsed["candidates"]
        if candidate.get("binding",{}).get("context",{}).get("method") in {"typescript-checker-v0.2",ECMASCRIPT_BINDING_PROFILE}
    )


def citation_is_current(
    loader: BundleLoader,
    root: Path,
    file_id: str,
    span: Tuple[int, int],
    *,
    blob_sha256: Optional[str] = None,
) -> bool:
    """Re-check one citation against the file's current bytes.

    Returns False when the blob hash changed, the file is gone, or the
    span no longer fits the current byte count.
    """
    if _compiler_config_changed(loader, root):
        return False
    path = Path(root) / file_id
    if not path.is_file():
        return False
    data = path.read_bytes()
    if blob_sha256 is not None and sha256_hex(data) != blob_sha256:
        return False
    snapshot_record = loader.contents["snapshot"]["source_blobs"].get(file_id)
    if snapshot_record is None or sha256_hex(data) != snapshot_record["analysis_sha256"]:
        return False
    start, end = span
    return 0 <= start <= end <= len(data)
