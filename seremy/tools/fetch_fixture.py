"""Fetch the pinned Redux fixture slice from GitHub and record its identity.

Materializes the exact bytes of the recorded revision used by the SEREMY
spatial-map research (tree SHA 61ebf8596654cf3c4b197e426e302fcb3c2bc13e).

Writes:
  seremy/fixtures/redux-slice/<sourceFiles paths>
  seremy/fixtures/redux-slice/fixture-manifest.json

The manifest records, per file: the Git blob SHA-1 (GitHub's content
address), the SHA-256 of the stored bytes, the byte count, and the source
URL. A later verification pass re-derives the Git blob SHA-1 from local
bytes (sha1("blob <len>\\0" + bytes)) to prove the stored bytes are the
revision bytes.

Usage:
    python seremy/tools/fetch_fixture.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

TREE_SHA = "61ebf8596654cf3c4b197e426e302fcb3c2bc13e"
REPO = "reduxjs/redux"
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "fixtures" / "redux-slice"
MANIFEST_PATH = DEST / "fixture-manifest.json"

EXPECTED_FILES = [
    "src/applyMiddleware.ts",
    "src/bindActionCreators.ts",
    "src/combineReducers.ts",
    "src/compose.ts",
    "src/createStore.ts",
    "src/index.ts",
    "src/types/actions.ts",
    "src/types/middleware.ts",
    "src/types/reducers.ts",
    "src/types/store.ts",
    "src/utils/actionTypes.ts",
    "src/utils/formatProdErrorMessage.ts",
    "src/utils/isAction.ts",
    "src/utils/isPlainObject.ts",
    "src/utils/kindOf.ts",
    "src/utils/symbol-observable.ts",
    "src/utils/warning.ts",
]


def git_blob_sha1(data: bytes) -> str:
    """Compute the Git blob object ID for raw bytes."""
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "seremy-fixture-fetch/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "seremy-fixture-fetch/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main() -> int:
    tree_url = f"https://api.github.com/repos/{REPO}/git/trees/{TREE_SHA}?recursive=1"
    tree = fetch_json(tree_url)
    if tree.get("truncated"):
        print("FATAL: tree listing was truncated", file=sys.stderr)
        return 2

    blobs = {entry["path"]: entry for entry in tree.get("tree", []) if entry["type"] == "blob"}
    missing = [path for path in EXPECTED_FILES if path not in blobs]
    if missing:
        print("FATAL: expected files missing from tree: %r" % missing, file=sys.stderr)
        return 2

    DEST.mkdir(parents=True, exist_ok=True)
    records = []
    for path in EXPECTED_FILES:
        entry = blobs[path]
        blob_url = f"https://api.github.com/repos/{REPO}/git/blobs/{entry['sha']}"
        payload = fetch_json(blob_url)
        if payload.get("encoding") != "base64":
            print(f"FATAL: unexpected encoding for {path}", file=sys.stderr)
            return 2
        data = __import__("base64").b64decode(payload["content"])
        derived = git_blob_sha1(data)
        if derived != entry["sha"]:
            print(f"FATAL: blob SHA-1 mismatch for {path}: {derived} != {entry['sha']}", file=sys.stderr)
            return 2
        target = DEST / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records.append(
            {
                "path": path,
                "git_blob_sha1": derived,
                "sha256": hashlib.sha256(data).hexdigest(),
                "byte_count": len(data),
                "source_url": blob_url,
            }
        )
        print(f"fetched {path} ({len(data)} bytes, git {derived[:12]})")

    manifest = {
        "fixture": "redux-slice",
        "repo": REPO,
        "tree_sha": TREE_SHA,
        "tree_url": f"https://api.github.com/repos/{REPO}/git/trees/{TREE_SHA}",
        "files": records,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST_PATH} ({len(records)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
