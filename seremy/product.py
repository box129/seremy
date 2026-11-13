"""Local eight-stage pipeline and immutable draft publication."""
from pathlib import Path
import json
import os
import tempfile
import shutil
import uuid
import base64
from types import SimpleNamespace
from seremy.contracts import AnalysisTextBlob, SourceBlob, canonical_bytes, sha256_hex
from seremy.snapshot import collect_snapshot, read_contained
from seremy.parsing import run_adapter, build_parsed_results, artifact_digest
from seremy.python_adapter import parse_python
from seremy.resolver import Resolver
from seremy.bundle import build_bundle, BundleLoader
from seremy.documentation import build_document_ir, validate_document, render_markdown
from seremy.architecture import framework_evidence, structural_views, aggregate, component_cycles
from seremy.language_profiles import SCRIPT_EXTENSIONS, SOURCE_EXTENSIONS, ECMASCRIPT_PROFILE, ECMASCRIPT_PRODUCT_PROFILE

PROFILE="seremy-local-product-v0.1"


def seal(contents):
    digest=sha256_hex(canonical_bytes(contents))
    return {"bundle":{"format":"seremy-graph-bundle-v0.1","profile":contents.get("profile",PROFILE),"producer":"seremy.pipeline/0.1",
            "content_digest":digest,"checks":{"status":"not_run","roster":[]},"acceptance_state":"pending_validation",
            "bundle_digest":sha256_hex(canonical_bytes({"content_digest":digest,"checks":{"status":"not_run","roster":[]}}))},
            "contents":contents}


def analyze(root, *, policy=None, snapshot_identity=None, use_git=True, progress=lambda message:None):
    root=Path(root).resolve()
    if policy is not None:
        if not isinstance(policy,dict) or set(policy)-{"forbidden","reject_cycles"}:
            raise ValueError("unsupported policy keys")
        if type(policy.get("reject_cycles",False)) is not bool or not isinstance(policy.get("forbidden",[]),list):
            raise ValueError("invalid policy types")
        for rule in policy.get("forbidden",[]):
            if not isinstance(rule,dict) or set(rule)-{"source","target","kind"} or not rule.get("source") or not rule.get("target"):
                raise ValueError("forbidden rules require source and target, with optional kind")
    progress("S01 · snapshot")
    manifest, frozen, scope=collect_snapshot(root,snapshot_identity=snapshot_identity,use_git=use_git)
    profile=ECMASCRIPT_PRODUCT_PROFILE if manifest.profile_id==ECMASCRIPT_PROFILE else PROFILE
    ts_inputs={p:raw for p,raw in frozen.items() if p.endswith(SCRIPT_EXTENSIONS)}
    py_inputs={p:raw for p,raw in frozen.items() if p.endswith(".py")}
    metadata={p:raw for p,raw in frozen.items() if Path(p).name in {"package.json","pyproject.toml","tsconfig.json"}}
    progress("S02 · parsing")
    results=parse_python(py_inputs)
    if ts_inputs:
        blobs={}
        for p,raw in ts_inputs.items():
            source=SourceBlob(p,None,sha256_hex(raw),len(raw),"complete")
            blobs[p]=(AnalysisTextBlob.from_source(source,raw),raw)
        # The compiler consumes a private copy, never a changing working tree.
        with tempfile.TemporaryDirectory(prefix="seremy-input-") as directory:
            temp=Path(directory)
            for p,raw in {**ts_inputs,**metadata}.items():
                path=temp/p
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(raw)
            results+=build_parsed_results(run_adapter(temp,list(ts_inputs),language_profile=manifest.profile_id),blobs,language_profile=manifest.profile_id)
    results.sort(key=lambda r:r.file_id)
    progress("S03 · binding")
    if results:
        resolutions=Resolver(results,expected_s02_digest=artifact_digest(results,profile_id=manifest.profile_id),profile_id=manifest.profile_id).resolve()
    else:
        from seremy.resolver import ResolutionSet
        resolutions=ResolutionSet({},[],[],"no_source_inputs",profile_id=manifest.profile_id)
    document=build_bundle(manifest,results,resolutions)
    contents=document["contents"]
    contents["profile"]=profile
    contents["scope"]=scope
    contents["snapshot"]["metadata_blobs"]={p:sha256_hex(raw) for p,raw in sorted(metadata.items())}
    contents["metadata_bytes"]={p:base64.b64encode(raw).decode("ascii") for p,raw in sorted(metadata.items())}
    contents["source_texts"]={}
    for p,raw in {**ts_inputs,**py_inputs}.items():
        try:
            contents["source_texts"][p]=raw.decode("utf8")
        except UnicodeError:
            pass
    progress("S04 · framework evidence")
    framework=framework_evidence(metadata,results)
    progress("S05 · structural components")
    components=structural_views(contents["s03"]["artifact"]["entities"],framework,contents["source_texts"])
    progress("S06 · relationship views")
    relationships={"producer":"seremy.relationships/0.1","view":aggregate(contents["s03"]["artifact"]["edges"],components["views"][0]),
                   "path_semantics":"observed_static_graph","history":{"status":"unsupported","reason":"separate_history_profile_required"}}
    for key,value in [("s04",framework),("s05",components),("s06",relationships)]:
        contents[key]={"digest":sha256_hex(canonical_bytes(value)),"artifact":value}
    contents["policy"]=policy or {"forbidden":[],"reject_cycles":False}
    progress("S07 · graph validation")
    loader=BundleLoader(seal(contents))
    pre_errors=validate_graph(loader)
    progress("S08 · documentation")
    ir=build_document_ir(loader)
    # These sections are projections of versioned artifacts. Keep evidence IDs in the text.
    extra=architecture_sections(contents)
    ir["architecture_sections"]=extra
    ir["dependencies"]={key:contents[key]["digest"] for key in ["s02","s03","s04","s05","s06"]}
    markdown=render_markdown(ir)+"\n"+extra
    progress("S07 · generated output validation")
    post_errors=validate_document(ir,loader)
    if ir["architecture_sections"]!=architecture_sections(contents):
        post_errors.append("architecture section differs from its evidence")
    if markdown!=render_markdown(ir)+"\n"+architecture_sections(contents):
        post_errors.append("rendered document differs from checked IR")
    # Detect file/config changes or additions after capture, including resolver-relevant new files.
    current, now, current_scope=collect_snapshot(root,snapshot_identity=snapshot_identity,use_git=use_git)
    if current.manifest_digest()!=manifest.manifest_digest() or current_scope!=scope:
        pre_errors.append("repository changed during analysis")
    report={"profile":profile,"pre_generation":{"status":"pass" if not pre_errors else "fail","errors":pre_errors},
            "post_generation":{"status":"pass" if not post_errors else "fail","errors":post_errors},
            "coverage":contents["coverage"],"scope":scope,
            "production_acceptance":"not_run","browser_acceptance":"not_run","performance":"not_run"}
    if pre_errors or post_errors:
        raise ValueError(json.dumps(report))
    return loader.document,ir,markdown,report


def validate_graph(loader):
    c=loader.contents;errors=[]
    entities={e["entity_id"]:e for e in c["s03"]["artifact"]["entities"]}
    source=c["source_texts"]
    for key in ["s04","s05","s06"]:
        if sha256_hex(canonical_bytes(c[key]["artifact"]))!=c[key]["digest"]:
            errors.append(key+" digest mismatch")
    metadata={p:base64.b64decode(encoded,validate=True) for p,encoded in c["metadata_bytes"].items()}
    if {p:sha256_hex(raw) for p,raw in metadata.items()}!=c["snapshot"]["metadata_blobs"]:
        errors.append("metadata blob mismatch")
    parsed=[]
    for record in c["s02"]["artifact"]["files"]:
        candidates=[SimpleNamespace(kind=x["kind"],attributes=x,span=SimpleNamespace(start=x["span"][0],end=x["span"][1]))
                    for x in record["candidates"]]
        parsed.append(SimpleNamespace(file_id=record["file_id"],analysis_sha256=record["analysis_sha256"],candidates=candidates))
    if framework_evidence(metadata,parsed)!=c["s04"]["artifact"]:
        errors.append("framework evidence does not match manifest and import inputs")
    resolutions={r["candidate_id"]:r for r in c["s03"]["artifact"]["resolutions"]}
    expected_candidates={f"cand:{r['file_id']}#{x['kind']}:{x['name']}@{x['span'][0]}"
                         for r in c["s02"]["artifact"]["files"] for x in r["candidates"]}
    if set(resolutions)!=expected_candidates or len(resolutions)!=len(c["s03"]["artifact"]["resolutions"]):
        errors.append("candidate conservation mismatch")
    source_ids={r["file_id"] for r in c["inventory"]["eligible"] if r["file_id"].endswith(SOURCE_EXTENSIONS)}
    parsed_files=c["s02"]["artifact"]["files"]
    parse_counts={bucket:sum(r["bucket"]==bucket for r in parsed_files)
                  for bucket in ["complete","partial","failed"]}
    parse_counts.update(parsed_file_records=len(parsed_files),source_file_count=len(source_ids),
                        not_processed=len(source_ids-{r["file_id"] for r in parsed_files}))
    if any(c["coverage"]["s02"].get(key)!=count for key,count in parse_counts.items()):
        errors.append("parsing coverage disagrees with file outcomes")
    seen_occurrences=set()
    for path,text in source.items():
        if sha256_hex(text.encode())!=c["snapshot"]["source_blobs"][path]["analysis_sha256"]:
            errors.append(path+" source bytes mismatch")
    for entity in entities.values():
        raw=source.get(entity["file_id"],"").encode()
        start,end=entity["name_span"]
        if raw[start:end].decode("utf8",errors="replace")!=entity["name"]:
            errors.append(entity["entity_id"]+" declaration span mismatch")
    for edge in loader.edges():
        target=entities.get(edge["target"])
        if not target or edge["origin"]!="binder_observation":
            errors.append("invalid factual edge target or origin")
        if edge["source_type"]=="entity_ref" and edge["source"] not in entities:
            errors.append("dangling edge source")
        if edge["source_type"]=="file_ref" and edge["source"] not in {"file:"+p for p in source}:
            errors.append("dangling file source")
        for occurrence in edge["occurrences"]:
            record=resolutions.get(occurrence["candidate_id"])
            if not record or record["outcome"]!="RESOLVED_SINGLE" or record["target"]!=edge["target"] or record["candidate_span"]!=occurrence["span"]:
                errors.append("edge occurrence does not match its resolution")
            seen_occurrences.add(occurrence["candidate_id"])
            ev=occurrence["evidence"]
            blob=c["snapshot"]["source_blobs"].get(occurrence["file_id"],{})
            if ev["blob_sha256"]!=blob.get("analysis_sha256") or not loader.validate_citation(ev["blob_sha256"],tuple(occurrence["span"])):
                errors.append("occurrence evidence mismatch")
    if seen_occurrences!={r["candidate_id"] for r in resolutions.values()
                          if r["outcome"]=="RESOLVED_SINGLE" and r["target_type"]=="entity_ref"}:
        errors.append("resolved entity occurrences are missing from the graph")
    view=c["s05"]["artifact"]["views"][0]
    if set(view["membership"])!=set(entities):
        errors.append("structural membership universe mismatch")
    actual_components=structural_views(list(entities.values()),c["s04"]["artifact"],source)
    if actual_components!=c["s05"]["artifact"]:
        errors.append("component membership does not match source paths and package manifests")
    expected=aggregate(loader.edges(),view)
    if expected!=c["s06"]["artifact"]["view"]:
        errors.append("aggregate view lost contributing edges")
    for edge in expected["edges"]:
        for rule in c["policy"].get("forbidden",[]):
            if all(rule.get(k) in (None,edge[k]) for k in ["source","target","kind"]):
                errors.append("forbidden boundary: "+edge["source"]+" → "+edge["target"])
    cross=[e for e in expected["edges"] if e["source"]!=e["target"]]
    if c["policy"].get("reject_cycles") and component_cycles(cross):
        errors.append("cross-component cycle")
    return errors


def architecture_sections(contents):
    framework=contents["s04"]["artifact"]
    view=contents["s05"]["artifact"]["views"][0]
    graph=contents["s06"]["artifact"]["view"]
    lines=["## Framework evidence",""]
    if not framework["frameworks"]:
        lines.append("No registered framework declarations or import syntax were found within the observed scope.")
    for f in framework["frameworks"]:
        lines.append(f"- {f['framework']} in {f['package_id']}. Declared dependency {f['declared']}, import occurrences {len(f['usage'])}.")
        if "evidence" in f:
            lines.append(f"  Evidence {f['evidence']['file_id']} · SHA-256 {f['evidence']['blob_sha256']}.")
        for site in f["usage"]:
            lines.append(f"  Import {site['file_id']} bytes {site['span']} · SHA-256 {site['blob_sha256']}.")
    for diagnostic in framework["diagnostics"]:
        lines.append(f"- Manifest analysis failed for {diagnostic['file_id']}. {diagnostic['reason']}.")
    lines.append(f"Unregistered dependencies {len(framework['unregistered_dependencies'])}. These receive no framework classification.")
    lines+=["","## Structural components",""]
    for group in view["groups"]:
        count=sum(owner==group for owner in view["membership"].values())
        lines.append(f"- {group} contains {count} observed declarations. Membership {view['version']}.")
    lines+=["","## Component relationships",""]
    for e in graph["edges"]:
        lines.append(f"- {e['source']} → {e['target']} · {e['kind']} · {e['distinct_edge_count']} distinct relationships · {e['site_count']} source sites.")
        lines.append("  Backing edge IDs "+", ".join(e["edge_ids"])+".")
    lines+=["","## Capability and coverage","",
            "Directory membership is structural. Semantic components, architectural layers, history analysis, runtime behavior and route/DI/ORM semantics await their own profiles.",
            "The graph reflects the declared static-analysis profiles. Unresolved and unsupported candidates remain in the graph bundle.",
            "Resolution outcomes "+json.dumps(contents["coverage"]["s03"]["outcome_counts"],sort_keys=True)+".",
            "This output is a draft. Product-wide acceptance, large-map performance and independent semantic evaluation remain unrun.",
            "", "Scope "+json.dumps(contents["scope"],sort_keys=True),""]
    return "\n".join(lines)


def publish(output, bundle, ir, markdown, report, map_html, *, fail_at=None):
    """Immutable content directory plus a single atomic pointer to the draft."""
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    artifacts={"graph.json":canonical_bytes(bundle),"document-ir.json":canonical_bytes(ir),
               "architecture.md":markdown.encode(),"validation.json":canonical_bytes(report),"map.html":map_html.encode()}
    hashes={name:sha256_hex(raw) for name,raw in artifacts.items()}
    digest=sha256_hex(canonical_bytes(hashes))
    staging=output/(".pending-"+uuid.uuid4().hex)
    staging.mkdir()
    try:
        for name,raw in artifacts.items():
            with (staging/name).open("wb") as f:
                f.write(raw);f.flush();os.fsync(f.fileno())
        manifest={"content_digest":digest,"files":hashes,"acceptance":"draft","profile":bundle.get("bundle",{}).get("profile",PROFILE)}
        manifest_bytes=canonical_bytes(manifest)
        with (staging/"manifest.json").open("wb") as handle:
            handle.write(manifest_bytes);handle.flush();os.fsync(handle.fileno())
        for name,expected in hashes.items():
            if sha256_hex((staging/name).read_bytes())!=expected:
                raise ValueError("publication verification failed")
        if fail_at=="before_install":
            raise RuntimeError("injected failure before install")
        versions=output/"versions"
        versions.mkdir(exist_ok=True)
        destination=versions/digest
        def verify_existing():
            if (destination/"manifest.json").read_bytes()!=manifest_bytes:
                raise ValueError("existing immutable publication manifest is corrupt")
            for name,expected in hashes.items():
                if sha256_hex((destination/name).read_bytes())!=expected:
                    raise ValueError("existing immutable publication is corrupt")
        if destination.exists():
            # A repeated content ID must match the bytes already on disk.
            verify_existing()
        else:
            try:
                os.replace(staging,destination)
            except OSError:
                if not destination.is_dir():
                    raise
                verify_existing()
        if fail_at=="before_pointer":
            raise RuntimeError("injected failure before pointer")
        pointer=output/(".pointer-"+uuid.uuid4().hex)
        try:
            pointer.write_bytes(canonical_bytes({"content_digest":digest,"path":"versions/"+digest,"acceptance":"draft"}))
            os.replace(pointer,output/"current.json")
        finally:
            pointer.unlink(missing_ok=True)
        return destination
    finally:
        if staging.exists():
            if not staging.resolve().is_relative_to(output):
                raise ValueError("staging cleanup escaped the publication directory")
            shutil.rmtree(staging)

