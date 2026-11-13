"""Portable source viewer backed by the same graph as documentation."""
from pathlib import Path
import json
from seremy.bundle import BundleLoader
from seremy.contracts import sha256_hex


def render_map(bundle):
    loader=BundleLoader(bundle)
    sources=loader.contents["source_texts"]
    entities={e["entity_id"]:e for e in loader.contents["s03"]["artifact"]["entities"]}
    edges=[]
    for edge in loader.edges():
        target=entities.get(edge["target"])
        if target is None:
            continue
        for occurrence in edge["occurrences"]:
            edges.append({"id":occurrence["candidate_id"],"kind":edge["kind"],
                "relation_id":json.dumps([edge["source"],edge["target"],edge["kind"]],separators=(",",":")),
                "from":{"file":occurrence["file_id"],"start":occurrence["span"][0],"end":occurrence["span"][1]},
                "to":{"file":target["file_id"],"start":target["name_span"][0],"end":target["name_span"][1]},
                "origin":edge["origin"],"method":occurrence["evidence"]["method"]})
    bound_ids={edge["id"] for edge in edges}
    fixture={"bundle":loader.meta,"files":sources,"hashes":{p:sha256_hex(t.encode()) for p,t in sources.items()},
             "edges":edges,"entities":list(entities.values()),"coverage":loader.contents["coverage"],
             "outcomes":[record for record in loader.contents["s03"]["artifact"]["resolutions"]
                         if record["candidate_id"] not in bound_ids],
             "analysis":{"profile":loader.contents["profile"],
                         "parsing_profile":loader.contents["s02"]["artifact"]["profile"],
                         "binding_profile":loader.contents["s03"]["artifact"].get("binding_profile"),
                         "scope":loader.contents.get("scope",{}),
                         "exclusions":loader.contents["inventory"]["exclusions"],
                         "parse_files":[{key:record.get(key) for key in ("file_id","bucket","reason","diagnostics")}
                                        for record in loader.contents["s02"]["artifact"]["files"]]},
             "repository":loader.contents["snapshot"]["repository_id"]}
    assets=Path(__file__).parent/"map"
    template=(assets/"product-template.html").read_text(encoding="utf8")
    template=template.replace("SCENE_RECORDS_JS",(assets/"scene-records.js").read_text(encoding="utf8"))
    template=template.replace("SCENE_MODEL_JS",(assets/"scene-model.js").read_text(encoding="utf8"))
    runtime=Path(__file__).parent/"tools/node_modules/pixi.js/dist/pixi.min.js"
    script=runtime.read_text(encoding="utf8") if runtime.exists() else ""
    template=template.replace("PIXI_RUNTIME_JS",script.replace("</script",r"<\/script"))
    template=template.replace("PIXI_SURFACE_JS",(assets/"pixi-surface.js").read_text(encoding="utf8"))
    return template.replace("FIXTURE_JSON",json.dumps(fixture,ensure_ascii=False).replace("<",r"\u003c"))

