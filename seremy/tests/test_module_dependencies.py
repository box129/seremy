"""Independent dependency truth: imports are file relationships, not calls."""
import copy
import json
import re
import uuid

import pytest

from seremy.product import analyze, seal, validate_graph, publish
from seremy.bundle import BundleLoader
from seremy.viewer import render_map
from seremy.map_bridge import MapBridge


@pytest.fixture
def analyzed(tmp_path):
    sources={
        "index.ts":"// 🦊\nimport { run } from './core';\nimport type { State } from './types';\nexport { run } from './core';\nexport type { State } from './types';\nimport './missing';\nimport 'third-party';\n",
        "core.ts":"/** Computes the source value. */\nexport function run(){ return 1 }\n",
        "types.ts":"export interface State { value: number }\n",
    }
    for path,text in sources.items():
        (tmp_path/path).write_text(text,encoding="utf8")
    return analyze(tmp_path,use_git=False)


def test_independent_module_truth_and_source_bytes(analyzed):
    bundle,ir,markdown,validation=analyzed
    modules=bundle["contents"]["module_dependencies"]["artifact"]
    assert {(e["source_file"],e["kind"],e["target_file"]) for e in modules["edges"]}=={
        ("index.ts","IMPORTS","core.ts"),("index.ts","TYPE_IMPORTS","types.ts"),
        ("index.ts","REEXPORTS","core.ts"),("index.ts","TYPE_REEXPORTS","types.ts")}
    assert modules["coverage"]["outcome_counts"]=={"EXTERNAL":1,"MISSING":1,"RESOLVED_SINGLE":4}
    assert bundle["contents"]["s03"]["artifact"]["edges"]==[]
    for edge in modules["edges"]:
        raw=bundle["contents"]["source_texts"][edge["source_file"]].encode()
        assert raw[slice(*edge["span"])].decode() in {"'./core'","'./types'"}
    assert "Module entry points and dependencies" in markdown
    assert "Computes the source value." in markdown
    assert validation["post_generation"]["status"]=="pass"


def test_module_tampering_and_mcp_selection(analyzed):
    bundle=analyzed[0];loader=BundleLoader(bundle)
    edge=loader.contents["module_dependencies"]["artifact"]["edges"][0]
    found=MapBridge.module_occurrence(loader,"module:"+edge["candidate_id"])
    assert found==edge
    assert MapBridge.module_occurrence(loader,"module:unknown") is None
    changed=copy.deepcopy(loader.contents)
    changed["module_dependencies"]["artifact"]["edges"][0]["target_file"]="missing.ts"
    assert "module dependencies disagree with snapshot observations" in validate_graph(BundleLoader(seal(changed)))
    html=render_map(bundle)
    data=json.loads(re.search(r'<script id="fixture" type="application/json">(.*?)</script>',html,re.S)[1])
    assert {edge["kind"] for edge in data["edges"]}=={"IMPORTS","TYPE_IMPORTS","REEXPORTS","TYPE_REEXPORTS"}
    assert all(edge["kind"]!="CALLS" for edge in data["edges"])


def test_module_connection_mcp_context_and_documentation(analyzed,tmp_path):
    bundle,ir,markdown,checks=analyzed
    publication=publish(tmp_path/"publications",bundle,ir,markdown,checks,render_map(bundle))
    bridge=MapBridge(tmp_path/"publications")
    edge=bundle["contents"]["module_dependencies"]["artifact"]["edges"][0]
    request={"view_id":str(uuid.uuid4()),"publication":publication.name,"digest":bundle["bundle"]["content_digest"],
             "verified":True,"selection":{"occurrence":"module:"+edge["candidate_id"]}}
    bridge.register(request)
    context=bridge.tool({"tool":"context","view_id":request["view_id"],"digest":request["digest"]})
    assert context["connection"]["kind"]=="IMPORTS"
    assert context["connection"]["target"]["file_id"]=="core.ts"
    assert context["connection"]["semantics"]=="static_module_dependency_not_runtime_execution"
    assert context["citations"][0]["text"]=="'./core'"
    document=bridge.tool({"tool":"documentation","view_id":request["view_id"],"digest":request["digest"]})
    assert any(claim["subject"].get("file_id")=="index.ts" for claim in document["claims"])
