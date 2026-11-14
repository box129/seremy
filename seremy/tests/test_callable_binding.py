"""Independent callable truth and deliberate ambiguity/dynamic boundaries."""
import json
from pathlib import Path

import pytest

from seremy.product import analyze
from seremy.resolver import CALLABLE_BINDING_PROFILE
from seremy.map_bridge import MapBridge
from seremy.product import publish
from seremy.viewer import render_map
import uuid

FIXTURE=Path(__file__).resolve().parents[1]/"fixtures/callable-slice"


def test_callable_and_namespace_truth_without_callback_execution_claim():
    bundle,ir,markdown,checks=analyze(FIXTURE,use_git=False)
    c=bundle["contents"];entities={entity["entity_id"]:entity for entity in c["s03"]["artifact"]["entities"]}
    observed=[]
    for edge in c["s03"]["artifact"]["edges"]:
        source,target=entities[edge["source"]],entities[edge["target"]]
        for site in edge["occurrences"]:
            raw=c["source_texts"][site["file_id"]].encode()
            observed.append({"source_file":source["file_id"],"source_name":source["name"],"target_file":target["file_id"],
                             "target_name":target["name"],"token":raw[slice(*site["span"])].decode(),"line":raw[:site["span"][0]].count(b"\n")+1})
            assert site["evidence"]["method"]==CALLABLE_BINDING_PROFILE
    truth=json.loads((FIXTURE/"truth.json").read_text(encoding="utf8"))
    assert sorted(observed,key=str)==sorted(truth["relationships"],key=str)
    assert not any(row["source_name"]=="App" and row["target_name"]=="onClick" for row in observed)
    assert c["s03"]["artifact"]["binding_profile"]==CALLABLE_BINDING_PROFILE
    assert {entity["name"] for entity in entities.values() if entity["kind"]=="callable_declaration"}=={"make","named","onClick"}
    assert checks["pre_generation"]["status"]==checks["post_generation"]["status"]=="pass"
    section=next(section for section in ir["sections"] if section["section_id"]=="callable-structure")
    claims=[claim for claim in ir["claims"] if claim["claim_id"] in section["claim_ids"]]
    on_click=next(claim for claim in claims if claim["subject"].get("entity_id","").startswith("ent:entry.tsx#callable_declaration:onClick@"))
    assert "Captured direct incoming call sites: 0" in on_click["text"]
    assert "does not establish that the callable is unused" in on_click["text"]
    assert "Named callable structure and callback limits" in markdown


@pytest.mark.parametrize("source,token,reason",[
    ("let chosen=()=>1; chosen()","chosen","mutable_or_dynamic_callable_target"),
    ("function entry(cb:()=>number){return cb()}","cb","mutable_or_dynamic_callable_target"),
    ("const obj={run(){return 1}}; obj.run()","run","receiver_not_immutable_namespace"),
    ("const left=()=>1,right=()=>2;const chosen=true?left:right;chosen()","chosen","callable_value_target_not_established"),
    ("function chosen(){};function other(){};chosen=other;chosen()","chosen","binding_reassigned_in_snapshot"),
    ("function chosen(){};function other(){};for(chosen of [other]){};chosen()","chosen","binding_reassigned_in_snapshot"),
    ("const chosen=()=>1;chosen?.()","chosen","optional_call_outside_profile"),
    ("const a=b;const b=a;a()","a","alias_cycle"),
    ("function chosen(){};eval('chosen=other');chosen()","chosen","dynamic_scope_in_source"),
])
def test_unsafe_or_unproven_targets_stay_explicit(tmp_path,source,token,reason):
    (tmp_path/"main.ts").write_text(source,encoding="utf8")
    bundle,*_=analyze(tmp_path,use_git=False);artifact=bundle["contents"]["s03"]["artifact"]
    record=next(record for record in artifact["resolutions"] if record["name"]==token and record["attempted"])
    assert record["outcome"]=="UNSUPPORTED" and record["reason"]==reason
    assert not artifact["edges"]


def test_type_only_namespace_and_external_namespace(tmp_path):
    (tmp_path/"helper.ts").write_text("export const run=()=>1",encoding="utf8")
    (tmp_path/"entry.ts").write_text("import type * as api from './helper'; import * as ext from 'external';api.run();ext.run()",encoding="utf8")
    bundle,*_=analyze(tmp_path,use_git=False);artifact=bundle["contents"]["s03"]["artifact"]
    records=[record for record in artifact["resolutions"] if record["attempted"]]
    assert [(record["outcome"],record["reason"]) for record in records]==[
        ("UNSUPPORTED","type_only_alias_has_no_runtime_value"),("EXTERNAL","bare_specifier")]
    assert not artifact["edges"]


def test_callable_unicode_spans_and_legacy_switch(tmp_path):
    text="\ufeff// 🦊\r\nexport const café=()=>1;\r\nexport const caller=()=>café();\r\n"
    (tmp_path/"entry.ts").write_bytes(text.encode())
    bundle,*_=analyze(tmp_path,use_git=False);artifact=bundle["contents"]["s03"]["artifact"]
    site=artifact["edges"][0]["occurrences"][0]
    assert site["span"]==[text.encode().rindex("café".encode()),text.encode().rindex("café".encode())+len("café".encode())]
    legacy,*_=analyze(tmp_path,use_git=False,callable_bindings=False)
    assert not legacy["contents"]["s03"]["artifact"]["edges"]
    assert not any(entity["kind"]=="callable_declaration" for entity in legacy["contents"]["s03"]["artifact"]["entities"])


def test_namespace_write_cannot_be_treated_as_an_immutable_target(tmp_path):
    (tmp_path/"helper.ts").write_text("export const run=()=>1",encoding="utf8")
    (tmp_path/"entry.ts").write_text("import * as api from './helper';api.run=()=>2;api.run()",encoding="utf8")
    bundle,*_=analyze(tmp_path,use_git=False)
    artifact=bundle["contents"]["s03"]["artifact"]
    call=next(record for record in artifact["resolutions"] if record["candidate_kind"]=="member_call")
    assert call["outcome"]=="UNSUPPORTED" and call["reason"]=="binding_reassigned_in_snapshot"
    assert not artifact["edges"]


def test_returned_function_and_method_bodies_have_their_own_owners(tmp_path):
    source="function helper(){};export function factory(){return function worker(){helper()}};export function object(){return {run(){helper()}}}"
    (tmp_path/"entry.ts").write_text(source,encoding="utf8")
    bundle,*_=analyze(tmp_path,use_git=False);artifact=bundle["contents"]["s03"]["artifact"]
    entities={entity["entity_id"]:entity for entity in artifact["entities"]}
    assert {(entities[edge["source"]]["name"],entities[edge["target"]]["name"]) for edge in artifact["edges"]}=={("worker","helper"),("run","helper")}
    assert {(entity["kind"],entity["name"]) for entity in artifact["entities"] if entity["name"] in {"worker","run"}}=={
        ("function_expression","worker"),("method_declaration","run")}


def test_anonymous_callback_keeps_target_evidence_without_inventing_creator_owner(tmp_path):
    (tmp_path/"entry.ts").write_text("function helper(){};export function creator(){return ()=>helper()}",encoding="utf8")
    bundle,*_=analyze(tmp_path,use_git=False);artifact=bundle["contents"]["s03"]["artifact"]
    assert len(artifact["edges"])==1
    edge=artifact["edges"][0]
    assert edge["source"]=="file:entry.ts" and edge["source_type"]=="file_ref"
    assert artifact["resolutions"][0]["outcome"]=="RESOLVED_SINGLE"
    candidate=next(candidate for row in bundle["contents"]["s02"]["artifact"]["files"] for candidate in row["candidates"] if candidate["kind"]=="call")
    assert candidate["source_owner_reason"]=="lexical_callable_owner_not_identified"


def test_long_alias_chains_are_bounded(tmp_path):
    source="const a0=()=>1;"+"".join(f"const a{i}=a{i-1};" for i in range(1,140))+"a139()"
    (tmp_path/"entry.ts").write_text(source,encoding="utf8")
    bundle,*_=analyze(tmp_path,use_git=False);artifact=bundle["contents"]["s03"]["artifact"]
    call=next(record for record in artifact["resolutions"] if record["attempted"])
    assert call["outcome"]=="UNSUPPORTED" and call["reason"]=="alias_depth_limit"
    assert not artifact["edges"]


def test_mcp_and_viewer_keep_file_owner_qualification(tmp_path):
    source=tmp_path/"source";source.mkdir()
    (source/"entry.ts").write_text("function helper(){};export const callback=()=>helper();export function creator(){return ()=>helper()}",encoding="utf8")
    bundle,ir,markdown,checks=analyze(source,use_git=False)
    edge=next(edge for edge in bundle["contents"]["s03"]["artifact"]["edges"] if edge["source_type"]=="file_ref")
    html=render_map(bundle)
    assert 'lexical_callable_owner_not_identified' in html
    output=tmp_path/"publications";publication=publish(output,bundle,ir,markdown,checks,html)
    bridge=MapBridge(output)
    request={"view_id":str(uuid.uuid4()),"publication":publication.name,"digest":bundle["bundle"]["content_digest"],
             "verified":True,"selection":{"occurrence":edge["occurrences"][0]["candidate_id"]}}
    bridge.register(request)
    context=bridge.tool({"tool":"context","view_id":request["view_id"],"digest":request["digest"]})
    assert context["connection"]["source_type"]=="file_ref"
    assert context["connection"]["source_owner_reason"]=="lexical_callable_owner_not_identified"
    section=bridge.tool({"tool":"documentation_section","view_id":request["view_id"],"digest":request["digest"],"section_id":"callable-structure","offset":0,"limit":20})
    assert any('callback argument propagation' in claim["text"] for claim in section["claims"])
