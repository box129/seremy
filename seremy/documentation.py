"""Build and verify a deterministic developer guide from a bound graph.

Sections, claims, witnesses and source links are validated against the exact
snapshot before publication. Independent explanation quality remains unqualified.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from seremy.bundle import BundleLoader
from seremy.guide import guide_sections, render_guide
from seremy.contracts import PROFILE_ID, canonical_bytes, sha256_hex
from seremy.language_profiles import SOURCE_EXTENSIONS

PRODUCER_DOCUMENTATION = "seremy.documentation/0.1"
TEMPLATE_VERSION = "developer-guide-v0.2"


def build_document_ir(loader: BundleLoader) -> dict:
    """Build the DocumentIR: claims with evidence, coverage and labels."""
    contents = loader.contents
    snapshot = contents["snapshot"]
    meta = loader.meta

    def blob_for(file_id: str) -> Optional[dict]:
        return snapshot["source_blobs"].get(file_id)

    claims: List[dict] = []
    claim_number = 0

    # Declaration claims (one per stored entity).
    for entity_id in loader.entity_ids():
        entity = loader.lookup_entity(entity_id)
        if entity is None:  # pragma: no cover - index built from same store
            continue
        claim_number += 1
        blob = blob_for(entity["file_id"])
        claims.append(
            {
                "claim_id": f"claim-{claim_number:03d}",
                "kind": "declaration",
                "subject": {"entity_id": entity_id},
                "text": (
                    f"{entity['name']} is declared as a {entity['kind']} in "
                    f"`{entity['file_id']}` at bytes "
                    f"[{entity['name_span'][0]}, {entity['name_span'][1]})."
                ),
                "citations": (
                    [
                        {
                            "file_id": entity["file_id"],
                            "blob_sha256": blob["analysis_sha256"],
                            "span": list(entity["name_span"]),
                        }
                    ]
                    if blob
                    else []
                ),
                "supports": {"stage": "s03", "artifact_digest": contents["s03"]["digest"]},
            }
        )

    # Relationship claims (one per direct edge, one citation per occurrence).
    for edge in loader.edges():
        source = (loader.lookup_entity(edge["source"]) if edge["source_type"]=="entity_ref" else None) or {
            "name": edge["source"],
            "file_id": "",
            "name_span": [0, 0],
        }
        target = loader.lookup_entity(edge["target"])
        if target is None:
            continue
        claim_number += 1
        citations = []
        for occurrence in edge["occurrences"]:
            blob = blob_for(occurrence["file_id"])
            if blob:
                citations.append(
                    {
                        "file_id": occurrence["file_id"],
                        "blob_sha256": blob["analysis_sha256"],
                        "span": list(occurrence["span"]),
                        "candidate_id": occurrence["candidate_id"],
                    }
                )
        claims.append(
            {
                "claim_id": f"claim-{claim_number:03d}",
                "kind": "relationship",
                "subject": {
                    "source": edge["source"],
                    "target": edge["target"],
                    "kind": edge["kind"],
                },
                "text": (
                    f"`{source['name']}` {edge['kind']} `{target['name']}` "
                    f"({len(edge['occurrences'])} occurrence(s), statically "
                    f"bound by the S03 binding profile, origin "
                    f"{edge['origin']})."
                ),
                "citations": citations,
                "supports": {"stage": "s03", "artifact_digest": contents["s03"]["digest"]},
            }
        )

    # Coverage claim: counts before rates; sampling explicitly undefined
    # beyond the slice universe.
    coverage = contents["coverage"]
    source_ids={record["file_id"] for record in contents["inventory"]["eligible"]
                if record["file_id"].endswith(SOURCE_EXTENSIONS)}
    parsed_sources={record["file_id"]:record for record in contents["s02"]["artifact"]["files"]
                    if record["file_id"] in source_ids}
    parse_counts={bucket:sum(record["bucket"]==bucket for record in parsed_sources.values())
                  for bucket in ["complete","partial","failed"]}
    claim_number += 1
    claims.append(
        {
            "claim_id": f"claim-{claim_number:03d}",
            "kind": "coverage",
            "subject": {"scope": "slice"},
            "text": (
                f"Inventory: {coverage['inventory']['input_count']} inputs = "
                f"{coverage['inventory']['eligible_count']} eligible + "
                f"{coverage['inventory']['excluded_count']} excluded. "
                f"S02: {coverage['s02']['parsed_file_records']} parsed-file "
                f"record(s). S03: {coverage['s03']['candidate_count']} "
                f"candidate(s), {coverage['s03']['attempted_count']} attempted, "
                f"{coverage['s03']['direct_edge_count']} direct edge(s)."
            ),
            "citations": [],
            "supports": {"stage": "bundle", "content_digest": meta["content_digest"]},
        }
    )

    sections, dependencies = guide_sections(loader, claims)
    return {
        "sections": sections,
        "dependencies": dependencies,
        "profile": contents["s02"]["artifact"]["profile"],
        "producer": PRODUCER_DOCUMENTATION,
        "template_version": TEMPLATE_VERSION,
        "binds": {
            "bundle_format": meta["format"],
            "content_digest": meta["content_digest"],
            "bundle_digest": meta["bundle_digest"],
        },
        "label": {
            "state": "coverage_limited_draft",
            "not_accepted_output": True,
            "slice_scope": (
                f"{parse_counts['complete']} complete, "
                f"{parse_counts['partial']} partial, {parse_counts['failed']} failed, "
                f"{len(source_ids-parsed_sources.keys())} unprocessed of "
                f"{len(source_ids)} source files"
            ),
            "sampling_policy": (
                "none defined beyond the slice universe; counts are full "
                "enumeration of the slice only"
            ),
        },
        "claims": claims,
    }


def validate_document(ir: dict, loader: BundleLoader) -> List[str]:
    """Post-generation validation: per-claim errors, never silently dropped."""
    errors: List[str] = []
    for claim in ir.get("claims", []):
        claim_id = claim.get("claim_id", "<unidentified>")

        for citation in claim.get("citations", []):
            blob_sha = citation.get("blob_sha256", "")
            span = tuple(citation.get("span", ()))
            if not loader.validate_citation(blob_sha, span):
                errors.append(
                    f"{claim_id}: citation does not validate against the bundle "
                    f"(blob {blob_sha[:12]}, span {span})"
                )

        subject = claim.get("subject", {})
        if claim.get("kind") == "declaration":
            if loader.lookup_entity(subject.get("entity_id", "")) is None:
                errors.append(f"{claim_id}: subject entity is absent from the bundle")
        elif claim.get("kind") == "relationship":
            source = subject.get("source")
            target = subject.get("target")
            kind = subject.get("kind")
            if not loader.edges(source=source, kind=kind, target=target):
                errors.append(
                    f"{claim_id}: no stored edge matches {source} {kind} {target}"
                )

    expected = build_document_ir(loader)
    if ir.get("binds") != expected["binds"]:
        errors.append("document bindings disagree with the graph bundle")
    if ir.get("label") != expected["label"]:
        errors.append("document coverage label disagrees with parser outcomes")
    if ir.get("claims") != expected["claims"]:
        errors.append("claim text, evidence or roster disagrees with the deterministic source projection")
    for key in ("sections", "dependencies", "template_version", "producer", "profile"):
        if ir.get(key) != expected[key]:
            errors.append(f"document {key} differs from the current evidence projection")
    return errors


def render_markdown(ir: dict) -> str:
    """Deterministic template rendering of the DocumentIR."""
    meta = ir["binds"]
    label = ir["label"]
    lines: List[str] = []
    lines.append("# SEREMY developer guide")
    lines.append("")
    lines.append(
        f"> **{label['state'].replace('_', ' ').capitalize()}.** Slice scope: "
        f"{label['slice_scope']}. Graph and template check results accompany this draft in validation.json. "
        f"Independent usefulness and semantic review remain pending validation; not accepted output. "
        f"Sampling policy: {label['sampling_policy']}"
    )
    lines.append("")
    lines.append(
        f"Snapshot binding: bundle format `{meta['bundle_format']}`, "
        f"content digest `{meta['content_digest']}`, "
        f"bundle digest `{meta['bundle_digest']}`."
    )
    lines.append("")

    lines.append(render_guide(ir))
    declarations = [c for c in ir["claims"] if c["kind"] == "declaration"]
    relationships = [c for c in ir["claims"] if c["kind"] == "relationship"]
    coverage_claims = [c for c in ir["claims"] if c["kind"] == "coverage"]

    if declarations:
        lines.append("## Declarations")
        lines.append("")
        for claim in declarations:
            lines.append(f"- {claim['text']}")
        lines.append("")

    if relationships:
        lines.append("## Relationships")
        lines.append("")
        for claim in relationships:
            lines.append(f"- {claim['text']}")
            for citation in claim["citations"]:
                span = citation["span"]
                lines.append(
                    f"  - Occurrence `{citation.get('candidate_id', '')}` at "
                    f"bytes [{span[0]}, {span[1]}) of `{citation['file_id']}` "
                    f"(blob `{citation['blob_sha256'][:16]}…`)"
                )
        lines.append("")

    if coverage_claims:
        lines.append("## Coverage")
        lines.append("")
        for claim in coverage_claims:
            lines.append(f"- {claim['text']}")
        lines.append("")

    lines.append("## Citation register")
    lines.append("")
    lines.append("| claim | file | bytes | blob sha256 (first 16) |")
    lines.append("|---|---|---|---|")
    for claim in ir["claims"]:
        for citation in claim.get("citations", []):
            span = citation["span"]
            lines.append(
                f"| {claim['claim_id']} | {citation['file_id']} "
                f"| [{span[0]}, {span[1]}) | {citation['blob_sha256'][:16]} |"
            )
    lines.append("")
    return "\n".join(lines)


def document_digest(ir: dict) -> str:
    return sha256_hex(canonical_bytes(ir))
