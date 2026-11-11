"""Tests for seremy.contracts (T1: contract records module)."""

from pathlib import Path

import pytest

from seremy.contracts import (
    AnalysisTextBlob,
    POSITION_MAP_ID,
    Span,
    SourceBlob,
    byte_to_line_col,
    byte_to_utf16_col,
    canonical_bytes,
    is_grapheme_boundary,
    reconcile_accounting,
    sha256_hex,
    slice_bytes,
)
from seremy.discovery import discover

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "redux-slice"


# --- Digests -----------------------------------------------------------------


def test_sha256_known_vector():
    assert sha256_hex(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_canonical_bytes_are_key_order_insensitive():
    assert canonical_bytes({"a": 1, "b": 2}) == canonical_bytes({"b": 2, "a": 1})


# --- Spans against real fixture bytes ----------------------------------------


def test_span_slices_exact_declaration_text():
    """Independent locator: find the isPlainObject declaration by text search,
    then verify the contract span machinery reproduces those exact bytes."""
    data = (FIXTURE_ROOT / "src" / "utils" / "isPlainObject.ts").read_bytes()
    needle = b"export default function isPlainObject(obj: any): obj is object {"
    start = data.index(needle)
    span = Span(start, start + len(needle))
    assert slice_bytes(data, span) == needle


def test_span_slice_recovers_call_site_from_isaction():
    data = (FIXTURE_ROOT / "src" / "utils" / "isAction.ts").read_bytes()
    needle = b"isPlainObject(action)"
    start = data.index(needle)
    assert slice_bytes(data, Span(start, start + len(needle))) == needle


def test_invalid_spans_rejected():
    with pytest.raises(ValueError):
        Span(-1, 3)
    with pytest.raises(ValueError):
        Span(5, 2)
    with pytest.raises(TypeError):
        Span(1.5, 3)  # type: ignore[arg-type]


def test_span_beyond_blob_rejected():
    with pytest.raises(ValueError):
        slice_bytes(b"abc", Span(0, 4))


# --- Blobs (v1.1 addendum) ---------------------------------------------------


def _complete_source_blob(data: bytes, file_id: str = "src/x.ts") -> SourceBlob:
    return SourceBlob(
        file_id=file_id,
        raw_path=None,
        content_sha256=sha256_hex(data),
        byte_count=len(data),
        read_status="complete",
    )


def test_analysis_blob_digests_coincide_for_original_utf8_profile():
    data = (FIXTURE_ROOT / "src" / "utils" / "isAction.ts").read_bytes()
    blob = _complete_source_blob(data)
    analysis = AnalysisTextBlob.from_source(blob, data)
    assert analysis.analysis_sha256 == analysis.source_sha256 == blob.content_sha256
    assert analysis.position_map == POSITION_MAP_ID


def test_analysis_blob_requires_complete_read():
    blob = SourceBlob(
        file_id="src/big.ts",
        raw_path=None,
        content_sha256=None,
        byte_count=2_000_000,
        read_status="partial",
    )
    with pytest.raises(ValueError, match="complete current source blob"):
        AnalysisTextBlob.from_source(blob, b"")


def test_analysis_blob_detects_hash_mismatch():
    blob = _complete_source_blob(b"real")
    with pytest.raises(ValueError, match="do not match"):
        AnalysisTextBlob.from_source(blob, b"fake")


# --- Coordinates -------------------------------------------------------------


def test_line_col_with_crlf_preserved():
    data = b"ab\r\ncd"
    assert byte_to_line_col(data, 0) == (0, 0)
    assert byte_to_line_col(data, 2) == (0, 2)      # the \r
    assert byte_to_line_col(data, 3) == (0, 3)      # between \r and \n: 3 bytes consumed (a, b, \r)
    assert byte_to_line_col(data, 4) == (1, 0)      # first byte of next line
    assert byte_to_line_col(data, 6) == (1, 2)      # end of blob


def test_line_col_rejects_out_of_range_offset():
    with pytest.raises(ValueError):
        byte_to_line_col(b"abc", 4)


def test_utf16_column_counts_code_units_not_bytes():
    data = "x\u03b1\n\u03b2y".encode("utf-8")  # x α \n β y
    assert byte_to_utf16_col(data, 0) == (0, 0)
    assert byte_to_utf16_col(data, 4) == (1, 0)   # first byte of β
    assert byte_to_utf16_col(data, 6) == (1, 1)   # after β: 1 UTF-16 unit


def test_multibyte_character_boundary_guard():
    data = "a\u03b1b".encode("utf-8")  # a(1) α(2) b(1)
    assert is_grapheme_boundary(data, 0)
    assert is_grapheme_boundary(data, 1)   # start of α
    assert not is_grapheme_boundary(data, 2)  # continuation byte
    assert is_grapheme_boundary(data, 3)


# --- Accounting --------------------------------------------------------------


def test_accounting_identity_enforced():
    reconcile_accounting(5, 2, 3)  # ok
    with pytest.raises(ValueError, match="accounting mismatch"):
        reconcile_accounting(5, 2, 2)
