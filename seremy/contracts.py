"""SEREMY shared contract records for the Milestone 1 slice.

Implements the record-level requirements of shared contract v1
(02-SHARED-CONTRACT.md) as tightened by the v1.1 cross-stage addendum,
restricted to the explicitly declared slice profile:

- Original UTF-8 sources only: the SourceBlob and AnalysisTextBlob digests
  coincide, and the position map is the declared identity map
  ``identity-utf8-v1``.  No non-UTF-8 support is inferred from this.
- Internal spans are zero-based UTF-8 byte offsets against the analysis
  text blob, end-exclusive.
- Coverage/accounting vocabulary follows contract section 4 and the
  addendum's mapping table.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Optional

# --- Declared profile identifiers (must match seremy/PROFILE.md) ----------

PROFILE_ID = "seremy-m1-profile-v0.1"
POSITION_MAP_ID = "identity-utf8-v1"
ENCODING_DECLARED = "utf-8"

ReadStatus = Literal["complete", "partial", "failed", "not_read"]
ExecutionBucket = Literal[
    "complete", "partial", "failed", "unsupported", "cancelled", "not_processed"
]

# --- Digest helpers --------------------------------------------------------


def sha256_hex(data: bytes) -> str:
    """Artifact identity is SHA-256 of stored bytes (contract section 1)."""
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(payload: object) -> bytes:
    """Canonical projection bytes: sorted keys, stable separators, UTF-8.

    Used for artifact and manifest digests so equal logical records produce
    equal digests regardless of dict insertion order.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# --- Spans and coordinates (contract section 2, v1.1 identity map) ---------


@dataclass(frozen=True)
class Span:
    """A zero-based, end-exclusive byte range against an AnalysisTextBlob."""

    start: int
    end: int  # exclusive

    def __post_init__(self) -> None:
        validate_span(self.start, self.end)


def validate_span(start: int, end: int) -> None:
    if not isinstance(start, int) or not isinstance(end, int):
        raise TypeError("span offsets must be integers")
    if start < 0 or end < 0:
        raise ValueError(f"span offsets must be non-negative: start={start}, end={end}")
    if end < start:
        raise ValueError(f"span end must not precede start: start={start}, end={end}")


def slice_bytes(data: bytes, span: Span) -> bytes:
    """Return the exact bytes addressed by ``span`` within blob bytes."""
    validate_span(span.start, span.end)
    if span.end > len(data):
        raise ValueError(
            f"span [{span.start}, {span.end}) exceeds blob length {len(data)}"
        )
    return data[span.start : span.end]


def byte_to_line_col(data: bytes, offset: int) -> tuple[int, int]:
    """Map a byte offset to zero-based (line, column_in_bytes).

    CRLF is preserved: ``\\r\\n`` counts as a single line terminator ending
    the current line, matching the no-newline-normalization profile.
    """
    if offset < 0 or offset > len(data):
        raise ValueError(f"offset {offset} outside blob of length {len(data)}")
    line = 0
    col = 0
    i = 0
    while i < offset:
        byte = data[i]
        if byte == 0x0A:  # \n
            line += 1
            col = 0
            i += 1
        elif byte == 0x0D:  # \r (\r\n handled together below)
            if i + 1 < len(data) and data[i + 1] == 0x0A:
                if i + 1 == offset:
                    # Offset sits between \r and \n: still line `line`,
                    # column continuing past \r per byte addressing.
                    col += 1
                    i += 1
                    continue
                line += 1
                col = 0
                i += 2
            else:
                line += 1
                col = 0
                i += 1
        else:
            col += 1
            i += 1
    return line, col


def byte_to_utf16_col(data: bytes, offset: int) -> tuple[int, int]:
    """Map a byte offset to zero-based (line, column_in_UTF16_code_units).

    The v1.1 contract requires decoded-text maps to line/UTF-16 positions
    for the initial binder profile.  With the identity-utf8-v1 map the
    decoded text is exactly ``data.decode('utf-8')``.
    """
    line, _ = byte_to_line_col(data, offset)
    line_start = _line_start_byte(data, line)
    decoded = data[line_start:offset].decode("utf-8")
    return line, len(decoded.encode("utf-16-le")) // 2


def _line_start_byte(data: bytes, line: int) -> int:
    """Byte offset at which zero-based ``line`` begins."""
    if line == 0:
        return 0
    seen = 0
    i = 0
    n = len(data)
    while i < n and seen < line:
        byte = data[i]
        if byte == 0x0D and i + 1 < n and data[i + 1] == 0x0A:
            seen += 1
            i += 2
            continue
        if byte in (0x0A, 0x0D):
            seen += 1
            i += 1
            continue
        i += 1
    if seen < line:
        raise ValueError(f"line {line} does not exist in blob of {n} bytes")
    return i


def is_grapheme_boundary(data: bytes, offset: int) -> bool:
    """Conservative check that ``offset`` is a UTF-8 character boundary.

    Continuation bytes (0b10xxxxxx) never start a character.  This guards
    span construction against splitting multibyte characters; full
    grapheme-cluster rules are out of scope for the identity map.
    """
    if offset <= 0 or offset >= len(data):
        return True
    return (data[offset] & 0xC0) != 0x80


# --- Source and analysis blobs (v1.1 addendum) ------------------------------


@dataclass(frozen=True)
class SourceBlob:
    """Raw source bytes with their identity and read boundary."""

    file_id: str  # normalized repository-relative POSIX path
    raw_path: Optional[str]  # original path when decoding is lossy; else None
    content_sha256: str
    byte_count: int
    read_status: ReadStatus
    encoding_declared: str = ENCODING_DECLARED

    def __post_init__(self) -> None:
        if "\\" in self.file_id:
            raise ValueError(f"file_id must use POSIX separators: {self.file_id!r}")
        if self.read_status == "complete" and self.byte_count < 0:
            raise ValueError("complete read needs a byte count")


@dataclass(frozen=True)
class AnalysisTextBlob:
    """Decoded analysis text bound to its SourceBlob.

    Under the original-UTF-8-only profile the analysis digest equals the
    source digest and both identities are preserved on citation.
    """

    analysis_sha256: str
    source_sha256: str
    byte_count: int
    position_map: str = POSITION_MAP_ID

    @staticmethod
    def from_source(blob: SourceBlob, data: bytes) -> "AnalysisTextBlob":
        if blob.read_status != "complete":
            raise ValueError(
                "a complete current source blob is required; an eligible "
                "unreadable/partial file cannot supply one"
            )
        digest = sha256_hex(data)
        if digest != blob.content_sha256:
            raise ValueError("source bytes do not match SourceBlob content hash")
        return AnalysisTextBlob(
            analysis_sha256=digest,
            source_sha256=blob.content_sha256,
            byte_count=len(data),
        )


# --- Evidence and claims (contract section 3) -------------------------------

Origin = Literal[
    "syntax_candidate",
    "binder_observation",
    "framework_rule",
    "history_observation",
    "authored_contract",
    "model_hypothesis",
    "derived",
]


@dataclass(frozen=True)
class EvidenceRef:
    """Source evidence binding an exact blob and span (contract section 3)."""

    blob_sha256: str
    span: Span
    producer: str
    method: str
    method_version: str

    def __post_init__(self) -> None:
        if not self.producer or not self.method or not self.method_version:
            raise ValueError("evidence requires producer, method and version")


# --- Inventory accounting (contract section 4) ------------------------------

S01_ACCOUNTING_UNITS = "files"


def reconcile_accounting(
    input_count: int,
    excluded_count: int,
    eligible_count: int,
) -> None:
    """Enforce input_count = excluded_count + eligible_count.

    Every enumerated input is either excluded by a recorded eligibility
    rule or eligible.  Zero denominators are N/A upstream; this check only
    guards arithmetic integrity.
    """
    if input_count != excluded_count + eligible_count:
        raise ValueError(
            "accounting mismatch: "
            f"input_count={input_count} != excluded_count={excluded_count} "
            f"+ eligible_count={eligible_count}"
        )


@dataclass(frozen=True)
class EligibleFileRecord:
    """A scheduled S01 unit with its execution bucket and reason."""

    file_id: str
    content_sha256: Optional[str]
    byte_count: Optional[int]
    bucket: ExecutionBucket
    reason: Optional[str] = None

    def __post_init__(self) -> None:
        buckets_with_content = ("complete", "partial")
        if self.bucket in buckets_with_content:
            if self.content_sha256 is None or self.byte_count is None:
                raise ValueError(
                    f"{self.bucket} unit requires content hash and byte count"
                )
        if self.bucket == "not_processed" and not self.reason:
            raise ValueError("not_processed requires a reason")
