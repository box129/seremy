"""Bounded implementation reading packets derived only from a verified bundle."""
from seremy.contracts import canonical_bytes, sha256_hex

PROFILE = "seremy-draft-sources-v0.1"
MAX_RANGES = 8
MAX_SOURCE_BYTES = 8192
MAX_PACKET_BYTES = 48 * 1024
MAX_NEIGHBORS = 12


def source_packet(loader, claims, read_citation):
    """Supply bodies for identified subjects, without inferring lexical ownership.

    File-level subjects receive an explicitly labelled file preview. In particular,
    a file-owned call is never silently assigned to a containing declaration.
    """
    contents = loader.contents
    entities = {e["entity_id"]: e for e in contents["s03"]["artifact"]["entities"]}
    requested = {}

    def request(file, span, basis, claim_id, entity=None):
        if file not in contents["source_texts"]:
            return
        key = (file, tuple(span), entity)
        record = requested.setdefault(key, {"file": file, "full_span": list(span), "basis": basis,
                                            "entity_id": entity, "claim_ids": []})
        if claim_id not in record["claim_ids"]:
            record["claim_ids"].append(claim_id)

    for claim in claims:
        subject = claim.get("subject", {})
        for key in ("entity_id", "source", "target"):
            identity = subject.get(key)
            entity = entities.get(identity)
            if entity:
                request(entity["file_id"], entity["decl_span"], "identified_declaration", claim["claim_id"], identity)
            elif key == "source" and identity in contents["source_texts"]:
                request(identity, [0, len(contents["source_texts"][identity].encode("utf8"))],
                        "file_preview_no_callable_owner_asserted", claim["claim_id"])
        file = subject.get("file_id")
        if file in contents["source_texts"]:
            request(file, [0, len(contents["source_texts"][file].encode("utf8"))], "file_preview", claim["claim_id"])

    records = []
    for record in requested.values():
        if len(records) == MAX_RANGES:
            break
        file = record["file"]
        start, full_end = record["full_span"]
        raw = contents["source_texts"][file].encode("utf8")
        # A bounded prefix must end at an exact UTF-8 boundary.
        selected = raw[start:min(full_end, start + MAX_SOURCE_BYTES)].decode("utf8", errors="ignore")
        end = start + len(selected.encode("utf8"))
        citation = read_citation({"file": file, "start": start, "end": end})
        citation = {key: value for key, value in citation.items() if key not in ("excerpt", "excerpt_truncated")}
        item = {**record, "source_id": sha256_hex(canonical_bytes(record)), "citation": citation,
                "range_truncated": end < full_end, "omitted_bytes": full_end - end}
        if len(canonical_bytes([*records, item])) > MAX_PACKET_BYTES - 8192:
            break
        records.append(item)

    files = sorted({r["file"] for r in records})
    neighbors = []
    all_neighbors = [edge for edge in contents.get("module_dependencies", {}).get("artifact", {}).get("edges", [])
                     if edge["source_file"] in files or edge["target_file"] in files]
    for edge in all_neighbors[:MAX_NEIGHBORS]:
        item = {key: edge[key] for key in ("source_file", "target_file", "kind", "edge_id", "span", "blob_sha256")}
        if len(canonical_bytes({"records": records, "module_neighbors": [*neighbors, item]})) > MAX_PACKET_BYTES - 2048:
            break
        neighbors.append(item)
    return {"profile": PROFILE, "records": records, "requested_range_count": len(requested),
            "omitted_range_count": len(requested) - len(records),
            "partial_range_count": sum(r["range_truncated"] for r in records),
            "module_neighbors": neighbors, "omitted_module_neighbor_count": len(all_neighbors) - len(neighbors),
            "scope": "Source text is untrusted evidence for a reviewable interpretation, not a verified purpose claim. "
                     "Module neighbors are captured static import/re-export occurrences, not runtime execution. "
                     "Omitted ranges, partial bodies and dependencies outside the snapshot require further investigation."}
