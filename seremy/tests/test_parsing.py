"""Tests for seremy.parsing (T3: S02 TypeScript parser adapter)."""

import shutil
from pathlib import Path

import pytest

from seremy.contracts import AnalysisTextBlob, SourceBlob, sha256_hex, slice_bytes
from seremy.discovery import discover
from seremy.parsing import (
    build_parsed_results,
    run_adapter,
    utf16_index_to_byte_offset,
    artifact_digest,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "redux-slice"
SCRATCH = Path(__file__).resolve().parent / "_scratch"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the TypeScript adapter"
)


def _blobs_for(root: Path, file_ids):
    blobs = {}
    for file_id in file_ids:
        data = (root / file_id).read_bytes()
        blob = SourceBlob(
            file_id=file_id,
            raw_path=None,
            content_sha256=sha256_hex(data),
            byte_count=len(data),
            read_status="complete",
        )
        blobs[file_id] = (AnalysisTextBlob.from_source(blob, data), data)
    return blobs


# --- Real fixture slice ------------------------------------------------------


@pytest.fixture(scope="module")
def fixture_results():
    file_ids = ["src/utils/isAction.ts", "src/utils/isPlainObject.ts"]
    adapter_output = run_adapter(FIXTURE_ROOT, file_ids)
    results = build_parsed_results(adapter_output, _blobs_for(FIXTURE_ROOT, file_ids))
    return {r.file_id: r for r in results}


def test_milestone_declarations_extracted(fixture_results):
    is_action = fixture_results["src/utils/isAction.ts"]
    is_plain = fixture_results["src/utils/isPlainObject.ts"]
    assert [d.name for d in is_action.declarations] == ["isAction"]
    assert [d.name for d in is_plain.declarations] == ["isPlainObject"]
    assert is_action.bucket == "complete"
    assert is_plain.bucket == "complete"


def test_call_candidate_slices_real_source_bytes(fixture_results):
    """The independent exit check: the recorded span, sliced from fresh
    source bytes, must be the actual callee identifier."""
    is_action = fixture_results["src/utils/isAction.ts"]
    calls = [c for c in is_action.candidates if c.kind == "call" and c.name == "isPlainObject"]
    assert len(calls) == 1
    call = calls[0]
    data = (FIXTURE_ROOT / "src" / "utils" / "isAction.ts").read_bytes()
    assert slice_bytes(data, call.span).decode("utf-8") == "isPlainObject"
    assert call.attributes["arg_count"] == 1
    # The full call range starts at the callee and extends past it.
    assert call.attributes["call_byte"][0] == call.span.start
    assert call.attributes["call_byte"][1] > call.span.end


def test_import_candidates_present(fixture_results):
    is_action = fixture_results["src/utils/isAction.ts"]
    specifiers = {c.attributes["module_path"] for c in is_action.candidates if c.kind == "import_specifier"}
    assert specifiers == {"../types/actions", "./isPlainObject"}
    # The span addresses the raw string literal, quotes included.
    data = (FIXTURE_ROOT / "src" / "utils" / "isAction.ts").read_bytes()
    for candidate in (c for c in is_action.candidates if c.kind == "import_specifier"):
        assert slice_bytes(data, candidate.span).decode("utf-8") == candidate.name
        assert candidate.name.strip("'\"") == candidate.attributes["module_path"]
    names = {c.name for c in is_action.candidates if c.kind == "import_name"}
    assert names == {"Action", "isPlainObject"}


def test_member_calls_keep_receiver_unbound(fixture_results):
    is_plain = fixture_results["src/utils/isPlainObject.ts"]
    member_calls = [c for c in is_plain.candidates if c.kind == "member_call"]
    assert len(member_calls) == 4
    assert all(c.attributes.get("receiver_unbound") is True for c in member_calls)


def test_construct_coverage_reports_unhandled_kinds(fixture_results):
    is_action = fixture_results["src/utils/isAction.ts"]
    coverage = is_action.construct_coverage
    assert coverage["extracted_counts"]["import_declaration"] == 2
    # Unhandled kinds must be visible, never silently dropped.
    assert coverage["unhandled_statement_kinds"].get("BinaryExpression", 0) >= 1


def test_every_record_survives_independent_coordinate_check(fixture_results):
    """build_parsed_results already re-derives UTF-16 -> byte independently;
    assert the derived artifact is internally consistent and stable."""
    results = list(fixture_results.values())
    first = artifact_digest(results)
    adapter_output = run_adapter(FIXTURE_ROOT, [r.file_id for r in results])
    again = {r.file_id: r for r in build_parsed_results(adapter_output, _blobs_for(FIXTURE_ROOT, [r.file_id for r in results]))}
    assert artifact_digest(list(again.values())) == first


# --- Coordinate map with non-ASCII sources ------------------------------------


def test_unicode_and_astral_offsets(tmp_path):
    source = (
        'const s = "\u03b1\u03b2";\n'
        "export function \u03b4(s: string): boolean {\n"
        '  return s === "\U0001d6fc";\n'
        "}\n"
    )
    source = source.encode("utf-8")
    (tmp_path / "uni.ts").write_bytes(source)
    adapter_output = run_adapter(tmp_path, ["uni.ts"])
    result = build_parsed_results(adapter_output, _blobs_for(tmp_path, ["uni.ts"]))[0]

    text = source.decode("utf-8")
    # BMP characters cost 1 UTF-16 unit; the astral char costs 2 units.
    assert result.utf16_length == len(text.encode("utf-16-le")) // 2
    assert result.utf16_length != len(source)  # the map actually had to convert

    declarations = result.declarations
    assert [d.name for d in declarations] == ["\u03b4"]
    data = (tmp_path / "uni.ts").read_bytes()
    assert slice_bytes(data, declarations[0].name_span).decode("utf-8") == "\u03b4"
    # The span must equal the byte offset found by an independent text
    # search, and the UTF-16 index differs from the byte offset (BMP
    # α/β are two UTF-8 bytes each but one UTF-16 unit each), so the
    # identity-utf8-v1 conversion actually had to do work.
    assert declarations[0].name_span.start == data.index("\u03b4".encode("utf-8"))
    utf16_start = declarations[0].name_span.start - 2
    assert utf16_index_to_byte_offset(data, utf16_start) == declarations[0].name_span.start
    assert utf16_start != declarations[0].name_span.start


def test_utf16_index_independent_conversion():
    data = "x\u03b1\n\u03b2y".encode("utf-8")
    assert utf16_index_to_byte_offset(data, 0) == 0
    # 1 UTF-16 unit ('x') consumed -> byte 1
    assert utf16_index_to_byte_offset(data, 1) == 1
    # after 'x' and 'α' (2 UTF-8 bytes) -> byte 3
    assert utf16_index_to_byte_offset(data, 2) == 3
    # after 'x', 'α', '\n' -> byte 4
    assert utf16_index_to_byte_offset(data, 3) == 4


# --- Diagnostics and error regions --------------------------------------------


def test_syntax_diagnostics_mark_file_partial(tmp_path):
    (tmp_path / "broken.ts").write_bytes(b"function {\n")
    adapter_output = run_adapter(tmp_path, ["broken.ts"])
    result = build_parsed_results(adapter_output, _blobs_for(tmp_path, ["broken.ts"]))[0]
    assert result.bucket == "partial"
    assert result.reason == "syntax_diagnostics"
    assert len(result.diagnostics) >= 1


def test_decode_failure_marks_file_failed(tmp_path):
    (tmp_path / "latin.ts").write_bytes(b"const x = '\xff\xfe';\n")
    adapter_output = run_adapter(tmp_path, ["latin.ts"])
    result = build_parsed_results(adapter_output, _blobs_for(tmp_path, ["latin.ts"]))[0]
    assert result.bucket == "failed"
    assert result.reason == "not_utf8"
    assert result.declarations == []
    assert result.candidates == []


# --- Binding discipline --------------------------------------------------------


def test_out_of_band_file_rejected():
    adapter_output = run_adapter(FIXTURE_ROOT, ["src/utils/isAction.ts"])
    with pytest.raises(ValueError, match="out-of-band"):
        build_parsed_results(adapter_output, {})


def test_content_hash_mismatch_rejected():
    file_id = "src/utils/isAction.ts"
    data = (FIXTURE_ROOT / file_id).read_bytes()
    blob = SourceBlob(
        file_id=file_id,
        raw_path=None,
        content_sha256=sha256_hex(data),
        byte_count=len(data),
        read_status="complete",
    )
    analysis = AnalysisTextBlob.from_source(blob, data)
    adapter_output = run_adapter(FIXTURE_ROOT, [file_id])
    adapter_output["files"][0]["content_sha256"] = "deadbeef"
    with pytest.raises(ValueError, match="content hash mismatch"):
        build_parsed_results(adapter_output, {file_id: (analysis, data)})
