"""Tests for seremy.documentation (T6: S08 templated document slice)."""

import shutil
from pathlib import Path

import pytest

from seremy.bundle import BundleLoader
from seremy.documentation import (
    build_document_ir,
    document_digest,
    render_markdown,
    validate_document,
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the TypeScript adapter"
)


@pytest.fixture(scope="module")
def loader(tmp_path_factory):
    # Reuse the verified chain builder from the bundle test module.
    from seremy.tests.test_bundle import _real_bundle

    document = _real_bundle()
    path = tmp_path_factory.mktemp("doc") / "graph-bundle.json"
    BundleLoader(document).write(path)
    return BundleLoader.from_file(path)


@pytest.fixture(scope="module")
def ir(loader):
    return build_document_ir(loader)


# --- Claim generation and rendering -------------------------------------------


def test_document_contains_milestone_relationship(ir):
    rel_claims = [c for c in ir["claims"] if c["kind"] == "relationship"]
    assert len(rel_claims) == 1
    claim = rel_claims[0]
    assert claim["subject"]["kind"] == "CALLS"
    assert claim["subject"]["target"].endswith("isPlainObject@132")
    # One citation per occurrence, at the real call-site bytes.
    assert claim["citations"][0]["span"] == [185, 198]


def test_declaration_claims_cover_slice_entities(ir):
    declarations = [c for c in ir["claims"] if c["kind"] == "declaration"]
    names = {
        c["subject"]["entity_id"].rsplit("@", 1)[0].split(":")[-1]
        for c in declarations
    }
    assert names == {"isAction", "isPlainObject"}


def test_markdown_cites_exact_bytes_and_binds_bundle(loader, ir):
    text = render_markdown(ir)
    assert "[116, 124)" in text          # isAction declaration span
    assert "[132, 145)" in text          # isPlainObject declaration span
    assert "[185, 198)" in text          # the call occurrence
    assert loader.meta["content_digest"] in text
    assert loader.meta["bundle_digest"] in text
    assert "pending validation" in text.lower()
    assert "not accepted output" in text.lower()


def test_sampling_policy_is_explicit(ir):
    text = render_markdown(ir)
    assert "none defined beyond the slice universe" in text
    assert ir["label"]["slice_scope"] == "2 complete, 0 partial, 0 failed, 15 unprocessed of 17 source files"


def test_document_is_deterministic(loader, ir):
    again = build_document_ir(loader)
    assert again == ir
    assert document_digest(again) == document_digest(ir)


# --- Post-generation validation ------------------------------------------------


def test_generated_document_passes_post_validation(loader, ir):
    assert validate_document(ir, loader) == []


def test_tampered_span_fails_validation(loader, ir):
    import copy

    broken = copy.deepcopy(ir)
    broken["claims"][0]["citations"][0]["span"] = [0, 100000]
    errors = validate_document(broken, loader)
    assert errors and "does not validate" in errors[0]


def test_foreign_blob_fails_validation(loader, ir):
    import copy

    broken = copy.deepcopy(ir)
    for claim in broken["claims"]:
        if claim["kind"] == "relationship":
            claim["citations"][0]["blob_sha256"] = "0" * 64
    errors = validate_document(broken, loader)
    assert errors and any("does not validate" in e for e in errors)


def test_claim_without_stored_edge_fails_validation(loader, ir):
    import copy

    broken = copy.deepcopy(ir)
    rel = next(c for c in broken["claims"] if c["kind"] == "relationship")
    rel["subject"]["target"] = "ent:src/utils/isAction.ts#function_declaration:isAction@116"
    rel["subject"]["source"] = "ent:src/utils/isAction.ts#function_declaration:isAction@116"
    errors = validate_document(broken, loader)
    assert errors and any("no stored edge" in e for e in errors)


def test_absent_subject_entity_fails_validation(loader, ir):
    import copy

    broken = copy.deepcopy(ir)
    decl = next(c for c in broken["claims"] if c["kind"] == "declaration")
    decl["subject"]["entity_id"] = "ent:src/utils/isAction.ts#function_declaration:ghost@116"
    errors = validate_document(broken, loader)
    assert errors and any("absent from the bundle" in e for e in errors)
