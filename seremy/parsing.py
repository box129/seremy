"""S02 syntax parsing for the Milestone 1 slice.

Wraps the TypeScript compiler adapter (seremy/tools/parse_typescript.mjs,
TypeScript version pinned in seremy/tools/package.json) and binds its
output to the S01 inventory:

- Every parsed file result references the exact SourceBlob/AnalysisTextBlob
  identities from the manifest; a manifest/content mismatch is an error.
- The adapter emits binder-native UTF-16 ranges plus normalized UTF-8 byte
  ranges under the identity-utf8-v1 position map.  This module re-derives
  the UTF-16 -> byte mapping independently (a second implementation) and
  rejects any record where the two disagree.
- Every name-bearing byte span must slice the real blob bytes to exactly
  the recorded name text.
- Records overlapping a parse-diagnostic region are dropped and counted
  (v1.1: records must not be taken from an explicitly untrusted region).
- Coverage buckets: decode failure -> failed; syntax diagnostics ->
  partial (reason syntax_diagnostics); clean parse -> complete.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from seremy.contracts import (
    POSITION_MAP_ID,
    AnalysisTextBlob,
    Span,
    canonical_bytes,
    is_grapheme_boundary,
    sha256_hex,
    slice_bytes,
)

from seremy.language_profiles import syntax_profile, parsed_profile

PRODUCER_PARSING = "seremy.parsing/0.2"
ADAPTER_SCRIPT = "parse_typescript.mjs"
EXPECTED_PRODUCER = "seremy.parse_typescript/0.1"

NAME_BEARING_CANDIDATE_KINDS = frozenset({"call", "member_call", "import_name", "import_specifier", "export_specifier", "jsx_tag"})


@dataclass(frozen=True)
class DeclarationRecord:
    kind: str
    name: str
    name_span: Span
    decl_span: Span


@dataclass(frozen=True)
class CandidateRecord:
    kind: str
    name: str
    span: Span
    attributes: dict = field(default_factory=dict)


@dataclass
class ParsedFileResult:
    """S02 handoff record for one file (ParsedFileResult in contract terms)."""

    file_id: str
    analysis_sha256: str
    source_sha256: str
    bucket: str  # complete | partial | failed
    reason: Optional[str]
    declarations: List[DeclarationRecord]
    candidates: List[CandidateRecord]
    diagnostics: List[dict]
    excluded_from_error_regions: int
    construct_coverage: dict
    utf16_length: Optional[int]

    def to_artifact_record(self) -> dict:
        return {
            "file_id": self.file_id,
            "analysis_sha256": self.analysis_sha256,
            "source_sha256": self.source_sha256,
            "bucket": self.bucket,
            "reason": self.reason,
            "declarations": [
                {
                    "kind": d.kind,
                    "name": d.name,
                    "name_span": [d.name_span.start, d.name_span.end],
                    "decl_span": [d.decl_span.start, d.decl_span.end],
                }
                for d in self.declarations
            ],
            "candidates": [
                {
                    "kind": c.kind,
                    "name": c.name,
                    "span": [c.span.start, c.span.end],
                    **c.attributes,
                }
                for c in self.candidates
            ],
            "diagnostics": self.diagnostics,
            "excluded_from_error_regions": self.excluded_from_error_regions,
            "construct_coverage": self.construct_coverage,
            "utf16_length": self.utf16_length,
        }


def utf16_index_to_byte_offset(data: bytes, index: int) -> int:
    """Independent UTF-16 -> UTF-8 byte mapping (second implementation).

    Walks decoded characters accumulating UTF-16 code units (2 for astral
    code points) and UTF-8 bytes.  Used to cross-check the adapter's map.
    """
    if index < 0:
        raise ValueError("utf16 index must be non-negative")
    text = data.decode("utf-8")
    units = 0
    byte_offset = 0
    for char in text:
        if units >= index:
            return byte_offset
        char_bytes = len(char.encode("utf-8"))
        units += 2 if ord(char) > 0xFFFF else 1
        byte_offset += char_bytes
    if units < index:
        raise ValueError(f"utf16 index {index} beyond text with {units} code units")
    return byte_offset


def run_adapter(
    root: Path,
    file_ids: List[str],
    *,
    tools_dir: Optional[Path] = None,
    language_profile: Optional[str] = None,
    node_executable: str = "node",
    module_dependencies: bool = False,
) -> dict:
    """Run the TypeScript adapter over the given files and return its JSON."""
    tools_dir = tools_dir or Path(__file__).resolve().parent / "tools"
    script = tools_dir / ADAPTER_SCRIPT
    if not script.is_file():
        raise FileNotFoundError(f"adapter script missing: {script}")
    if not (tools_dir / "node_modules" / "typescript").is_dir():
        raise FileNotFoundError(
            "TypeScript package missing; run `npm install typescript@<pinned>` in seremy/tools"
        )

    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as handle:
        json.dump({"files": list(file_ids),"moduleDependencies":module_dependencies,**({"profile":language_profile} if language_profile else {})}, handle)
        files_path = handle.name
    try:
        completed = subprocess.run(
            [node_executable, str(script), str(root), files_path],
            capture_output=True,
            check=False,
        )
    finally:
        Path(files_path).unlink(missing_ok=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "adapter failed: rc=%s stderr=%s" % (completed.returncode, completed.stderr.decode("utf-8", "replace"))
        )
    return json.loads(completed.stdout.decode("utf-8"))


def _overlaps(span: Span, diagnostic: dict) -> bool:
    start, end = diagnostic.get("byte", [0, 0])
    return span.start < end and start < span.end


def _validate_and_convert_file(
    file_payload: dict,
    blob_bytes: bytes,
    analysis: AnalysisTextBlob,
) -> ParsedFileResult:
    file_id = file_payload["file_id"]
    diagnostics = file_payload.get("parse_diagnostics", [])
    excluded_from_error_regions = 0

    declarations: List[DeclarationRecord] = []
    candidates: List[CandidateRecord] = []

    def checked_span(byte_range: list, utf16_range: list) -> Span:
        """Validate one adapter record's spans against the real blob bytes."""
        start, end = byte_range
        span = Span(start, end)
        slice_bytes(blob_bytes, span)  # raises if beyond the blob
        if not is_grapheme_boundary(blob_bytes, span.start):
            raise ValueError(f"{file_id}: span start splits a multibyte character at {span.start}")
        if not is_grapheme_boundary(blob_bytes, span.end):
            raise ValueError(f"{file_id}: span end splits a multibyte character at {span.end}")
        # Independent coordinate-map cross-check.
        derived_start = utf16_index_to_byte_offset(blob_bytes, utf16_range[0])
        derived_end = utf16_index_to_byte_offset(blob_bytes, utf16_range[1])
        if (derived_start, derived_end) != (start, end):
            raise ValueError(
                f"{file_id}: coordinate-map disagreement for utf16 {utf16_range}: "
                f"adapter={byte_range} independent=({derived_start}, {derived_end})"
            )
        return span

    for payload in file_payload.get("declarations", []):
        span = checked_span(payload["name_byte"], payload["name_utf16"])
        text = slice_bytes(blob_bytes, span).decode("utf-8")
        if text != payload["name"]:
            raise ValueError(
                f"{file_id}: declaration span slices to {text!r}, expected {payload['name']!r}"
            )
        decl_span = checked_span(payload["decl_byte"], payload["decl_utf16"])
        if any(_overlaps(decl_span, diagnostic) for diagnostic in diagnostics):
            excluded_from_error_regions += 1
            continue
        declarations.append(
            DeclarationRecord(kind=payload["kind"], name=payload["name"], name_span=span, decl_span=decl_span)
        )

    for payload in file_payload.get("candidates", []):
        span = checked_span(payload["byte"], payload["utf16"])
        if payload["kind"] in NAME_BEARING_CANDIDATE_KINDS:
            text = slice_bytes(blob_bytes, span).decode("utf-8")
            if text != payload["name"]:
                raise ValueError(
                    f"{file_id}: candidate span slices to {text!r}, expected {payload['name']!r}"
                )
        if any(_overlaps(span, diagnostic) for diagnostic in diagnostics):
            excluded_from_error_regions += 1
            continue
        attributes = {
            key: value
            for key, value in payload.items()
            if key not in ("kind", "name", "byte", "utf16")
        }
        candidates.append(CandidateRecord(kind=payload["kind"], name=payload["name"], span=span, attributes=attributes))

    decode_status = file_payload.get("decode", {}).get("status", "failed")
    if decode_status != "ok":
        bucket, reason, utf16_length = "failed", "not_utf8", None
    elif file_payload.get("analysis_failure"):
        bucket, reason, utf16_length = "failed", file_payload["analysis_failure"], file_payload["decode"].get("utf16_length")
    elif diagnostics:
        bucket, reason, utf16_length = "partial", "syntax_diagnostics", file_payload["decode"].get("utf16_length")
    else:
        bucket, reason, utf16_length = "complete", None, file_payload["decode"].get("utf16_length")

    return ParsedFileResult(
        file_id=file_id,
        analysis_sha256=analysis.analysis_sha256,
        source_sha256=analysis.source_sha256,
        bucket=bucket,
        reason=reason,
        declarations=declarations,
        candidates=candidates,
        diagnostics=diagnostics,
        excluded_from_error_regions=excluded_from_error_regions,
        construct_coverage=file_payload.get("construct_coverage", {}),
        utf16_length=utf16_length,
    )


def build_parsed_results(
    adapter_output: dict,
    blobs: Dict[str, Tuple[AnalysisTextBlob, bytes]],
    *, language_profile: Optional[str] = None,
) -> List[ParsedFileResult]:
    """Bind adapter output to S01 blob identities and validate every record."""
    if adapter_output.get("producer") != EXPECTED_PRODUCER:
        raise ValueError(f"unexpected adapter producer: {adapter_output.get('producer')!r}")
    if adapter_output.get("position_map") != POSITION_MAP_ID:
        raise ValueError("adapter position map does not match the declared profile")
    if adapter_output.get("profile") != (language_profile or syntax_profile(blobs)):
        raise ValueError("adapter language profile does not match the requested source universe")

    results: List[ParsedFileResult] = []
    for file_payload in adapter_output.get("files", []):
        file_id = file_payload["file_id"]
        if file_id not in blobs:
            raise ValueError(f"adapter produced a result for an out-of-band file: {file_id}")
        analysis, data = blobs[file_id]
        if file_payload.get("content_sha256") != analysis.source_sha256:
            raise ValueError(f"content hash mismatch for {file_id}")
        if file_payload.get("byte_count") != analysis.byte_count:
            raise ValueError(f"byte count mismatch for {file_id}")
        results.append(_validate_and_convert_file(file_payload, data, analysis))
    if len(results) != len(blobs) or len({r.file_id for r in results}) != len(blobs):
        raise ValueError("adapter output does not cover the exact requested file universe")
    return results


def artifact_digest(results: List[ParsedFileResult], *, profile_id: Optional[str] = None) -> str:
    payload = {
        "profile": profile_id or parsed_profile(results),
        "producer": PRODUCER_PARSING,
        "position_map": POSITION_MAP_ID,
        "files": sorted((r.to_artifact_record() for r in results), key=lambda r: r["file_id"]),
    }
    return sha256_hex(canonical_bytes(payload))
