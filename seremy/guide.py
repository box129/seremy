"""Structured developer-guide projections of immutable analysis records."""
import json
import re
from collections import defaultdict
from urllib.parse import quote


def source_link(citation, binding):
    payload = {"digest": binding["content_digest"], **citation}
    return "map.html#seremy-source=" + quote(json.dumps(payload, separators=(",", ":")), safe="")


def guide_sections(loader, claims):
    contents = loader.contents
    dependencies = {key: contents[key]["digest"] for key in ("s02", "s03", "s04", "s05", "s06") if key in contents}
    dependencies["graph"] = loader.meta["content_digest"]
    if "module_dependencies" in contents:
        dependencies["module_dependencies"]=contents["module_dependencies"]["digest"]
    sections = []

    def section(section_id, title):
        result = {"section_id": section_id, "title": title, "claim_ids": [], "dependencies": dependencies}
        sections.append(result)
        return result

    def add(section, text, subjects, witnesses, citations=()):
        claim_id = f"guide-{len(claims):04d}"
        claims.append({"claim_id": claim_id, "kind": "guide", "text": text,
                       "subject": subjects, "citations": list(citations), "witnesses": witnesses,
                       "dependencies": dependencies, "interpretation": "deterministic_projection"})
        section["claim_ids"].append(claim_id)

    overview = section("overview", "Repository overview")
    add(overview, f"This guide describes {len(loader.entity_ids())} observed declarations and "
        f"{len(loader.edges())} direct static relationships in the captured analysis. "
        "Use the call walkthroughs to inspect source evidence and the coverage section to assess analysis limits.",
        {"scope": "snapshot"}, [{"stage": "s03", "artifact_digest": contents["s03"]["digest"]}])
    declared_root=contents["snapshot"].get("declared_root","")
    if "#path=" in declared_root:
        add(overview,f"Repository input scope: `{declared_root}`. Only the selected source folder was captured. "
            "Configuration and dependencies outside that folder were not acquired; this is not a full-repository analysis.",
            {"scope":"source_subdirectory"},[{"stage":"snapshot","declared_root":declared_root}])

    modules=contents.get("module_dependencies",{}).get("artifact",{})
    module_edges=modules.get("edges",[])
    if modules:
        entry=section("entry-points", "Module entry points and dependencies")
        by_file=defaultdict(list)
        for edge in module_edges:
            by_file[edge["source_file"]].append(edge)
        if not by_file:
            add(entry,"No in-snapshot module dependencies were resolved. This does not establish that the repository has no dependencies.",
                {"scope":"snapshot"},[{"stage":"module_dependencies","artifact_digest":contents["module_dependencies"]["digest"]}])
        for file,edges in sorted(by_file.items(),key=lambda item:(not item[0].endswith(("index.ts","index.js","index.tsx","index.jsx")),-len(item[1]),item[0])):
            targets=", ".join(f"`{e['target_file']}` ({e['kind']})" for e in edges)
            citations=[{"file_id":file,"span":e["span"],"blob_sha256":e["blob_sha256"],"role":"module_dependency","candidate_id":"module:"+e["candidate_id"]} for e in edges]
            add(entry,f"`{file}` connects to {targets}. Follow these module boundaries before drilling into individual calls. "
                "Imports and re-exports describe static dependencies, not execution order.",{"file_id":file},
                [{"stage":"module_dependencies","edge_ids":[e["edge_id"] for e in edges]}],citations)

    descriptions=section("source-descriptions","Source descriptions")
    for file,text in sorted(contents.get("source_texts",{}).items()):
        # Quote the repository's own leading JSDoc as source evidence, never as accepted purpose inference.
        match=re.search(r"/\*\*([\s\S]*?)\*/",text)
        if not match:
            continue
        description=" ".join(re.sub(r"^\s*\* ?","",line).strip() for line in match[1].splitlines()).strip()
        description=description.split("@param",1)[0].strip()
        if not description:
            continue
        start=len(text[:match.start()].encode());end=len(text[:match.end()].encode())
        citation={"file_id":file,"span":[start,end],"blob_sha256":contents["snapshot"]["source_blobs"][file]["analysis_sha256"],"role":"source_comment"}
        # Keep raw source syntax as quoted text; the renderer never interprets HTML.
        add(descriptions,f"Source comment in `{file}` (author-provided, not independently verified):\n\n> "+description[:1200].replace("\n"," "),
            {"file_id":file},[{"stage":"snapshot","file_id":file}], [citation])
    if not descriptions["claim_ids"]:
        add(descriptions,"No JSDoc source descriptions were available in this snapshot. Architectural responsibilities still need an evidence-backed author or agent draft.",
            {"scope":"snapshot"},[{"stage":"snapshot"}])

    flows=section("static-flows","Static call paths to explore")
    entities={e["entity_id"]:e for e in contents["s03"]["artifact"]["entities"]}
    outgoing=defaultdict(list)
    for edge in loader.edges():
        outgoing[edge["source"]].append(edge)
    paths=[]
    for first in loader.edges():
        for second in outgoing[first["target"]]:
            if second["target"] in {first["source"],first["target"]}:
                continue
            paths.append((first,second))
    for first,second in paths[:8]:
        names=[entities.get(key,{"name":key})["name"] for key in [first["source"],first["target"],second["target"]]]
        citations=[]
        for edge in (first,second):
            site=edge["occurrences"][0]
            citations.append({"file_id":site["file_id"],"span":site["span"],"blob_sha256":site["evidence"]["blob_sha256"],"role":"call_site"})
        add(flows," → ".join(f"`{name}`" for name in names)+". These two observed static calls provide a reading path; they do not prove that this sequence executes at runtime.",
            {"scope":"static_path"},[{"stage":"s03","edges":[[e["source"],e["target"],e["kind"]] for e in (first,second)]}],citations)
    if not paths:
        add(flows,"No two-edge direct-call paths were observed. Use individual call evidence and module dependencies to navigate this scope.",
            {"scope":"snapshot"},[{"stage":"s03","artifact_digest":contents["s03"]["digest"]}])

    walkthroughs = section("walkthroughs", "Call walkthroughs")
    for edge in loader.edges():
        source = loader.lookup_entity(edge["source"]) if edge["source_type"] == "entity_ref" else None
        target = loader.lookup_entity(edge["target"])
        if not target:
            continue
        citations = []
        for site in edge["occurrences"]:
            citations.append({"file_id": site["file_id"], "span": site["span"],
                              "blob_sha256": contents["snapshot"]["source_blobs"][site["file_id"]]["analysis_sha256"],
                              "role": "call_site", "candidate_id": site["candidate_id"]})
        citations.append({"file_id": target["file_id"], "span": target["name_span"],
                          "blob_sha256": contents["snapshot"]["source_blobs"][target["file_id"]]["analysis_sha256"],
                          "role": "target_declaration"})
        caller = source["name"] if source else edge["source"]
        add(walkthroughs, f"The analyzer connects `{caller}` to `{target['name']}` because "
            f"the binding profile resolves {len(edge['occurrences'])} call site(s) to the declaration in "
            f"`{target['file_id']}`. Open a call site, then the target declaration to follow the evidence. "
            "This records a static call relationship. Runtime execution and business purpose require additional evidence.",
            {"source": edge["source"], "target": edge["target"], "kind": edge["kind"]},
            [{"stage": "s03", "artifact_digest": contents["s03"]["digest"],
              "candidate_ids": [site["candidate_id"] for site in edge["occurrences"]]}], citations)

    framework = section("frameworks", "Framework evidence")
    if "s04" in contents:
        artifact = contents["s04"]["artifact"]
        if not artifact["frameworks"]:
            add(framework, "No registered framework declarations or import syntax were found within the observed scope.",
                {"scope": "snapshot"}, [{"stage": "s04", "artifact_digest": contents["s04"]["digest"]}])
        for index, record in enumerate(artifact["frameworks"]):
            add(framework, f"{record['framework']} in `{record['package_id']}`. Declared dependency "
                f"{record['declared']}, import occurrences {len(record['usage'])}. Framework runtime semantics remain outside this profile.",
                {"package_id": record["package_id"]},
                [{"stage": "s04", "artifact_digest": contents["s04"]["digest"], "record_index": index,
                  "manifest": record.get("evidence"), "imports": record["usage"]}], record["usage"])
        for diagnostic in artifact["diagnostics"]:
            add(framework, f"Manifest analysis failed for `{diagnostic['file_id']}`. {diagnostic['reason']}.",
                {"file_id": diagnostic["file_id"]}, [{"stage": "s04", "diagnostic": diagnostic}])
        add(framework, f"Unregistered dependencies {len(artifact['unregistered_dependencies'])}.",
            {"scope": "snapshot"}, [{"stage": "s04", "artifact_digest": contents["s04"]["digest"]}])

    groups = section("groups", "Structural components")
    for view in contents.get("s05", {}).get("artifact", {}).get("views", []):
        for group in view["groups"]:
            count = sum(owner == group for owner in view["membership"].values())
            add(groups, f"`{group}` contains {count} observed declarations under the `{view['target']}` view.",
                {"group_id": group}, [{"stage": "s05", "membership_version": view["version"], "target": view["target"]}])

    experiment = contents.get("s05", {}).get("artifact", {}).get("experimental_membership")
    if experiment:
        membership = experiment["artifact"]
        experimental = section("experimental-membership", "Experimental membership views")
        add(experimental, f"Membership adapter `{membership['producer']}` has origin `{membership['origin']}` and "
            f"execution `{membership['execution']}`. Quality assessment remains not_run. "
            "The declared universe contains observed declarations; upstream parse and resolution limits remain applicable.",
            {"scope": "membership"}, [{"stage": "s05", "artifact_digest": contents["s05"]["digest"]}])
        for view in [*membership["views"], *membership["role_views"]]:
            count = view["coverage"]
            add(experimental, f"View `{view['view_id']}` targets `{view['target']}` at cut `{view['cut_id']}`. "
                f"Assigned {count['assigned']} of {count['eligible']} observed declarations. "
                f"Unassigned {count['unassigned']}, including {count['disputed']} disputed. "
                f"Membership map `{view['membership_map_version']}`. Interpretation `{view['rationale']}`.",
                {"view_id": view["view_id"]}, [{"stage": "s05", "view_version": view["version"], "origin": view["origin"]}])
            if view["mode"] == "primary_partition":
                add(experimental, f"View `{view['view_id']}` retains {len(view['relationships']['unassigned_edge_ids'])} "
                    "distinct source edges with unassigned endpoints. Aggregates retain source edge IDs and occurrence counts.",
                    {"view_id": view["view_id"]}, [{"stage": "s06", "view_version": view["version"]}])

    relationships = section("component-relations", "Component relationships")
    for edge in contents.get("s06", {}).get("artifact", {}).get("view", {}).get("edges", []):
        add(relationships, f"`{edge['source']}` → `{edge['target']}` · {edge['kind']} · "
            f"{edge['distinct_edge_count']} distinct relationships · {edge['site_count']} source sites.",
            {"source": edge["source"], "target": edge["target"]}, [{"stage": "s06", "edge_ids": edge["edge_ids"]}])

    limits = section("limits", "Capability and coverage")
    add(limits, "Directory and package membership describe structural views. Semantic ownership, architectural layers, "
        "runtime behavior and route/DI/ORM semantics require additional profiles. Resolution outcomes "
        + json.dumps(contents["coverage"]["s03"].get("outcome_counts", {}), sort_keys=True) + ".",
        {"scope": "snapshot"}, [{"stage": "bundle", "content_digest": loader.meta["content_digest"]}])
    candidates = {f"cand:{f['file_id']}#{c['kind']}:{c['name']}@{c['span'][0]}": c
                  for f in contents["s02"]["artifact"]["files"] for c in f.get("candidates", [])}
    for result in contents["s03"]["artifact"].get("resolutions", []):
        candidate = candidates.get(result["candidate_id"], {})
        if candidate.get("kind") != "jsx_tag":
            continue
        add(limits, f"JSX tag `{candidate.get('name', '')}` has outcome {result['outcome']}. "
            "JSX runtime semantics are outside this profile. The tag supplies no accepted runtime call relationship.",
            {"candidate_id": result["candidate_id"]}, [{"stage": "s03", "resolution": result}])
    return sections, dependencies


def render_guide(ir):
    claims = {claim["claim_id"]: claim for claim in ir["claims"]}
    lines = []
    for section in ir.get("sections", []):
        lines.extend([f"## {section['title']}", ""])
        for claim_id in section["claim_ids"]:
            claim = claims[claim_id]
            lines.extend([claim["text"], ""])
            for citation in claim["citations"]:
                role = citation.get("role", "source").replace("_", " ")
                label = f"{role} · {citation['file_id']} · bytes {citation['span']}"
                lines.extend([f"[{label}]({source_link(citation, ir['binds'])})", ""])
    return "\n".join(lines)
