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


def test_walkthrough_links_call_and_target_in_same_snapshot(loader, ir):
    from urllib.parse import unquote
    from seremy.guide import source_link
    section = next(s for s in ir["sections"] if s["section_id"] == "walkthroughs")
    claim = next(c for c in ir["claims"] if c["claim_id"] == section["claim_ids"][0])
    assert "`isAction` to `isPlainObject`" in claim["text"]
    assert [c["role"] for c in claim["citations"]] == ["call_site", "target_declaration"]
    assert [c["span"] for c in claim["citations"]] == [[185, 198], [132, 145]]
    for citation in claim["citations"]:
        link = unquote(source_link(citation, ir["binds"]))
        assert loader.meta["content_digest"] in link
        assert citation["file_id"] in link


@pytest.mark.parametrize("tamper", ["irrelevant_citation", "reverse", "runtime", "section", "dependency", "snapshot"])
def test_guide_rejects_plausible_but_unsupported_changes(loader, ir, tamper):
    import copy
    broken = copy.deepcopy(ir)
    section = next(s for s in broken["sections"] if s["section_id"] == "walkthroughs")
    claim = next(c for c in broken["claims"] if c["claim_id"] == section["claim_ids"][0])
    if tamper == "irrelevant_citation":
        # A perfectly valid declaration span does not establish a call site.
        claim["citations"][0] = copy.deepcopy(claim["citations"][1])
    elif tamper == "reverse":
        claim["subject"]["source"], claim["subject"]["target"] = claim["subject"]["target"], claim["subject"]["source"]
    elif tamper == "runtime":
        claim["text"] = "isAction always executes isPlainObject at runtime and owns the business layer."
    elif tamper == "section":
        section["claim_ids"] = []
    elif tamper == "dependency":
        broken["dependencies"]["s03"] = "0" * 64
    else:
        broken["binds"]["content_digest"] = "0" * 64
    assert validate_document(broken, loader)


def test_guide_invalidates_after_membership_or_policy_change(tmp_path):
    import copy
    from seremy.product import analyze, seal
    (tmp_path / "entry.py").write_text("def helper():\n return 1\ndef entry():\n return helper()\n")
    bundle, ir, _, _ = analyze(tmp_path)
    for key in ("s05", "policy"):
        changed = copy.deepcopy(bundle["contents"])
        if key == "s05":
            changed[key]["artifact"]["views"][0]["version"] = "changed-membership"
        else:
            changed[key]["reject_cycles"] = True
        assert validate_document(ir, BundleLoader(seal(changed)))
    (tmp_path / "entry.py").write_text("def helper():\n return 2\ndef entry():\n return helper()\n")
    current, _, _, _ = analyze(tmp_path)
    assert validate_document(ir, BundleLoader(current))
