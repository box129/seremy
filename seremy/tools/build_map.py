"""Generate the real-bundle map page (seremy/map/map.html).

Reads the graph bundle produced by the S01–S03 chain, loads it through
the same BundleLoader consumers must use, and injects the following into
the map page fixture:

- the bundle's content digest, bundle digest and inventory manifest digest
- the parsed slice files' exact source text plus their recorded blob hashes
- entities (declaration spans) as syntax regions
- direct edges with occurrence spans as follow targets, carrying origin
  and binding-method provenance

The page then verifies the embedded source against the bundle blobs with
WebCrypto at load time and shows a STALE badge (with navigation disabled)
on any mismatch — the map binds exact upstream digests, it never trusts
its own embedding.

Usage:
    python seremy/tools/build_map.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # seremy/
BUNDLE_PATH = ROOT / "artifacts" / "graph-bundle-slice.json"
FIXTURE_SRC = ROOT / "fixtures" / "redux-slice"
TEMPLATE = ROOT / "map" / "template.html"
OUTPUT = ROOT / "map" / "map.html"

sys.path.insert(0, str(ROOT.parent))
from seremy.bundle import BundleLoader  # noqa: E402


def main() -> int:
    document = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    loader = BundleLoader(document)  # full validation, including digests
    contents = loader.contents
    meta = loader.meta
    snapshot = contents["snapshot"]
    s03 = contents["s03"]["artifact"]

    entities = {e["entity_id"]: e for e in s03["entities"]}
    files = {}
    for file_id in sorted(snapshot["source_blobs"]):
        data = (FIXTURE_SRC / file_id).read_bytes()
        files[file_id] = {"text": data.decode("utf-8")}
    blobs = {fid: rec["analysis_sha256"] for fid, rec in snapshot["source_blobs"].items()}

    regions = []
    for entity_id in loader.entity_ids():
        entity = loader.lookup_entity(entity_id)
        regions.append({"file": entity["file_id"], "start": entity["name_span"][0], "end": entity["name_span"][1]})

    edges = []
    for edge in s03["edges"]:
        for occurrence in edge["occurrences"]:
            target = entities.get(edge["target"])
            if target is None:
                continue  # file-only endpoints have no entity anchor in this slice
            edges.append(
                {
                    "id": f"{edge['kind']}:{occurrence['candidate_id']}",
                    "kind": edge["kind"],
                    "from": {
                        "file": occurrence["file_id"],
                        "start": occurrence["span"][0],
                        "end": occurrence["span"][1],
                    },
                    "to": {
                        "file": target["file_id"],
                        "start": target["name_span"][0],
                        "end": target["name_span"][1],
                    },
                    "origin": edge["origin"],
                    "method": s03.get("binding_profile", "unknown"),
                }
            )

    fixture = {
        "bundle": {
            "content_digest": meta["content_digest"],
            "bundle_digest": meta["bundle_digest"],
            "manifest_digest": contents["snapshot"]["inventory_manifest_digest"],
        },
        "blobs": blobs,
        "files": files,
        "edges": edges,
        "regions": regions,
    }

    html = TEMPLATE.read_text(encoding="utf-8")
    placeholder = '"__FIXTURE__"'
    if placeholder not in html:
        print("FATAL: fixture placeholder missing from template", file=sys.stderr)
        return 2
    html = html.replace(placeholder, json.dumps(fixture).replace("<", r"<"), 1)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUTPUT} with {len(files)} files, {len(edges)} edge(s), {len(regions)} regions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
