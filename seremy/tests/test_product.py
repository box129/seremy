"""Independent checks for the connected local product profile."""
import copy
import json
from pathlib import Path
import zipfile
import pytest
from seremy.python_adapter import parse_python
from seremy.parsing import artifact_digest
from seremy.resolver import Resolver
from seremy.architecture import framework_evidence, aggregate, shortest_path, component_cycles
from seremy.product import analyze, publish, validate_graph
from seremy.viewer import render_map
from seremy.bundle import BundleLoader
from seremy.documentation import build_document_ir, validate_document
from seremy.__main__ import extract_zip, main


def python_result(sources):
    parsed=parse_python({p:s.encode() for p,s in sources.items()})
    return Resolver(parsed,expected_s02_digest=artifact_digest(parsed)).resolve()


def test_python_renamed_import_and_shadowing():
    result=python_result({"entry.py":"from target import actual as chosen\ndef entry():\n return chosen()\n",
                          "target.py":"def actual():\n return 1\n"})
    assert len(result.edges)==1
    assert result.binding_profile=="python-ast-static-v0.1"
    assert ":actual@" in result.edges[0].target
    shadow=python_result({"entry.py":"def chosen():\n return 1\ndef entry(chosen):\n return chosen()\n"})
    assert not shadow.edges
    assert any(r.outcome=="UNSUPPORTED" for r in shadow.resolutions)


def test_python_scope_and_module_qualified_calls():
    result=python_result({"entry.py":"import target as t\ndef entry():\n return t.actual()\n",
                          "target.py":"def actual():\n return 1\n"})
    assert len(result.edges)==1
    assert result.edges[0].occurrences[0].span.start==result.edges[0].occurrences[0].span.end-len("actual")


def test_python_lambda_shadow_is_not_a_static_function_edge():
    result=python_result({"a.py":"def chosen():\n return 1\nvalue=lambda chosen:chosen()\n"})
    assert not result.edges


def test_python_default_call_owner_is_module():
    result=python_result({"a.py":"def chosen():\n return 1\ndef entry(value=chosen()):\n return value\n"})
    assert len(result.edges)==1
    assert result.edges[0].source=="file:a.py"


def test_python_unicode_crlf_offsets_and_recursion():
    text="# é 🦊\r\ndef chosen(n):\r\n return chosen(n-1)\r\n"
    result=python_result({"entry.py":text})
    assert len(result.edges)==1
    e=result.edges[0]
    assert e.source==e.target
    assert e.occurrences[0].span.start==text.encode().rindex(b"chosen")


def test_python_syntax_failure_is_explicit():
    parsed=parse_python({"a.py":b"def broken("})
    assert parsed[0].bucket=="failed"
    assert not parsed[0].declarations


def test_framework_exact_package_identity_and_monorepo():
    metadata={"ui/package.json":b'{"dependencies":{"preact":"^10"},"description":"react"}',
              "api/pyproject.toml":b'[project]\ndependencies=["fastapi>=0.100"]\n'}
    evidence=framework_evidence(metadata,[])
    assert {(f["framework"],f["package_id"]) for f in evidence["frameworks"]}=={("Preact","package:ui"),("FastAPI","package:api")}
    assert framework_evidence(dict(reversed(list(metadata.items()))),[])==evidence


def test_malformed_framework_manifest_has_diagnostic():
    evidence=framework_evidence({"package.json":b"invalid"},[])
    assert evidence["diagnostics"]
    assert not evidence["frameworks"]


def edge(source,target,kind="CALLS",sites=1):
    return {"source":source,"target":target,"kind":kind,"origin":"binder_observation",
            "occurrences":[{"candidate_id":str(i)} for i in range(sites)]}


def test_aggregation_preserves_edge_and_occurrence_counts():
    result=aggregate([edge("a","b",sites=2),edge("c","b"),edge("missing","b")],
                     {"membership":{"a":"A","b":"B","c":"A"},"version":"v1"})
    assert result["edges"][0]["distinct_edge_count"]==2
    assert result["edges"][0]["site_count"]==3
    assert len(result["unassigned_edge_ids"])==1


def test_paths_exclude_history_and_preserve_witness():
    edges=[edge("a","b"),edge("b","c"),edge("a","z","COCHANGE")]
    result=shortest_path(edges,"a","c")
    assert result["depth"]==2
    assert len(result["witness"])==2
    assert shortest_path(edges,"a","z")["status"]=="no_path"
    assert shortest_path(edges,"a","a")["depth"]==0
    assert shortest_path(edges,"a","c",max_visited=1)["status"]=="truncated"


def test_cycle_membership():
    assert component_cycles([edge("a","b"),edge("b","a"),edge("c","d")])==[["a","b"]]


@pytest.fixture
def mixed_repo(tmp_path):
    files={"app.py":"from helper import chosen\ndef entry():\n return chosen()\n",
           "helper.py":"def chosen():\n return 1\n",
           "main.ts":"import {target as chosen} from './target'; export function entry(){return chosen()}",
           "target.ts":"export function target(){return 1}",
           "package.json":'{"dependencies":{"preact":"^10"}}',
           "pyproject.toml":'[project]\ndependencies=["fastapi>=0.100"]'}
    for p,text in files.items():
        (tmp_path/p).write_bytes(text.encode())
    return tmp_path


def test_connected_mixed_pipeline_and_deterministic_output(mixed_repo):
    bundle,ir,markdown,report=analyze(mixed_repo)
    c=bundle["contents"]
    assert len(c["s03"]["artifact"]["edges"])==2
    assert c["s03"]["artifact"]["binding_profile"]=="mixed-callable-static-v0.1"
    assert c["coverage"]["s02"]["parsed_file_records"]==4
    assert {f["framework"] for f in c["s04"]["artifact"]["frameworks"]}=={"Preact","FastAPI"}
    assert not report["pre_generation"]["errors"]
    assert not report["post_generation"]["errors"]
    assert "Component relationships" in markdown
    assert analyze(mixed_repo)[0]==bundle
    assert len(c["s05"]["artifact"]["views"][0]["membership"])==4


def test_changed_prose_with_valid_citation_is_rejected(mixed_repo):
    bundle,*_=analyze(mixed_repo)
    loader=BundleLoader(bundle)
    ir=build_document_ir(loader)
    ir["claims"][0]["text"]="This system sends all data to the moon."
    assert validate_document(ir,loader)


def test_tampered_aggregate_rejected(mixed_repo):
    bundle,*_=analyze(mixed_repo)
    loader=BundleLoader(bundle)
    loader.contents["s06"]["artifact"]["view"]["edges"][0]["site_count"]+=1
    assert validate_graph(loader)


def test_forbidden_boundary_blocks_publication_input(tmp_path):
    (tmp_path/"api").mkdir();(tmp_path/"store").mkdir()
    (tmp_path/"api/entry.py").write_text("from store.helper import chosen\ndef entry():\n return chosen()\n")
    (tmp_path/"store/helper.py").write_text("def chosen():\n return 1\n")
    with pytest.raises(ValueError,match="forbidden boundary"):
        analyze(tmp_path,policy={"forbidden":[{"source":"directory:api","target":"directory:store","kind":"CALLS"}]})


def test_failed_publication_retains_old_pointer(tmp_path):
    out=tmp_path/"out"
    first=publish(out,{},{},"first",{},"<html>first</html>")
    pointer=(out/"current.json").read_bytes()
    for barrier in ["before_install","before_pointer"]:
        with pytest.raises(RuntimeError,match="injected failure"):
            publish(out,{},{},"second",{},"<html>second</html>",fail_at=barrier)
        assert (out/"current.json").read_bytes()==pointer
        assert first.exists()
    second=publish(out,{},{},"second",{},"<html>second</html>")
    assert first!=second
    assert first.exists()
    assert not list(out.glob(".pending-*"))


def test_zip_traversal_and_duplicates_rejected(tmp_path):
    archive=tmp_path/"bad.zip"
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("../outside.py","print(1)")
    dest=tmp_path/"extract";dest.mkdir()
    with pytest.raises(ValueError,match="unsafe"):
        extract_zip(archive,dest)
    assert not (tmp_path/"outside.py").exists()


def test_zip_symlink_rejected(tmp_path):
    archive=tmp_path/"bad.zip"
    with zipfile.ZipFile(archive,"w") as z:
        entry=zipfile.ZipInfo("link")
        entry.external_attr=(0o120777 << 16)
        z.writestr(entry,"outside")
    with pytest.raises(ValueError,match="links"):
        extract_zip(archive,tmp_path/"extract")


def test_cli_plain_python_publishes_offline_outputs(tmp_path,capsys):
    repo=tmp_path/"repo";repo.mkdir()
    (repo/"a.py").write_text("def helper():\n return 1\ndef entry():\n return helper()\n")
    output=tmp_path/"out"
    assert main(["analyze",str(repo),"--output",str(output)])==0
    pointer=json.loads((output/"current.json").read_text())
    publication=output/pointer["path"]
    assert (publication/"map.html").exists()
    assert (publication/"architecture.md").exists()
    assert json.loads((publication/"validation.json").read_text())["post_generation"]["status"]=="pass"
    assert not pointer["acceptance"]=="accepted"


def test_product_config_snapshot_is_deterministic(mixed_repo):
    (mixed_repo/"tsconfig.json").write_text('{"compilerOptions":{"baseUrl":".","strict":true}}')
    assert analyze(mixed_repo)[0]==analyze(mixed_repo)[0]


def test_promoted_bundle_state_is_rejected(mixed_repo):
    from seremy.bundle import CorruptBundleError
    bundle,*_=analyze(mixed_repo)
    bundle["bundle"]["acceptance_state"]="accepted"
    with pytest.raises(CorruptBundleError):
        BundleLoader(bundle)


def test_changed_metadata_cannot_keep_old_framework_facts(mixed_repo):
    bundle,*_=analyze(mixed_repo)
    loader=BundleLoader(bundle)
    loader.contents["s04"]["artifact"]["frameworks"][0]["framework"]="Invented"
    assert validate_graph(loader)


def test_unknown_policy_keys_are_rejected(mixed_repo):
    with pytest.raises(ValueError,match="policy"):
        analyze(mixed_repo,policy={"forbid_everything":True})


def test_zip_cli_and_empty_repository(tmp_path):
    archive=tmp_path/"source.zip"
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("project/entry.py","def helper():\n return 1\ndef entry():\n return helper()\n")
    assert main(["analyze","--zip",str(archive),"--output",str(tmp_path/"zip-output")])==0
    empty=tmp_path/"empty";empty.mkdir()
    assert main(["analyze",str(empty),"--output",str(tmp_path/"empty-output")])==0

