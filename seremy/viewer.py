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
                "from":{"file":occurrence["file_id"],"start":occurrence["span"][0],"end":occurrence["span"][1]},
                "to":{"file":target["file_id"],"start":target["name_span"][0],"end":target["name_span"][1]},
                "origin":edge["origin"],"method":occurrence["evidence"]["method"]})
    fixture={"bundle":loader.meta,"files":sources,"hashes":{p:sha256_hex(t.encode()) for p,t in sources.items()},
             "edges":edges,"entities":list(entities.values()),"coverage":loader.contents["coverage"],
             "repository":loader.contents["snapshot"]["repository_id"]}
    template=(Path(__file__).parent/"map/product-template.html").read_text(encoding="utf8")
    return template.replace("FIXTURE_JSON",json.dumps(fixture,ensure_ascii=False).replace("<",r"\u003c"))

