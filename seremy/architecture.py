"""Package-scoped framework evidence, structural memberships and typed views."""
from collections import defaultdict, deque
from pathlib import PurePosixPath
import json
import re
import tomllib
from seremy.contracts import canonical_bytes, sha256_hex

REGISTRY = {
    "npm": {"react":"React","preact":"Preact","express":"Express","next":"Next.js",
            "vue":"Vue","svelte":"Svelte"},
    "python": {"django":"Django","fastapi":"FastAPI","flask":"Flask","sqlalchemy":"SQLAlchemy"},
}


def framework_evidence(metadata, parsed):
    packages, diagnostics, records = {}, [], {}
    unregistered=[]
    for path, raw in sorted(metadata.items()):
        parent=PurePosixPath(path).parent.as_posix()
        ecosystem="npm" if PurePosixPath(path).name=="package.json" else "python"
        other="pyproject.toml" if ecosystem=="npm" else "package.json"
        collocated=(PurePosixPath(path).parent/other).as_posix() in metadata
        package="package:"+parent+(":"+ecosystem if collocated else "")
        try:
            if PurePosixPath(path).name=="package.json":
                obj=json.loads(raw)
                dependencies={}
                for section in ["dependencies","devDependencies","peerDependencies","optionalDependencies"]:
                    for name,version in obj.get(section,{}).items():
                        dependencies.setdefault(name,[]).append({"section":section,"version_spec":str(version)})
                ecosystem="npm"
            elif PurePosixPath(path).name=="pyproject.toml":
                obj=tomllib.loads(raw.decode())
                dependencies={}
                for entry in obj.get("project",{}).get("dependencies",[]):
                    match=re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)",entry.strip())
                    if not match:
                        raise ValueError("invalid project dependency")
                    name=match[1].lower().replace("_","-")
                    dependencies.setdefault(name,[]).append({"section":"project.dependencies","version_spec":entry})
                ecosystem="python"
            else:
                continue
            packages[(parent,ecosystem)]={"package_id":package,"root":parent,"manifest":path,"ecosystem":ecosystem}
            for name, specs in sorted(dependencies.items()):
                if name in REGISTRY[ecosystem]:
                    records[(package,name)]={"framework":REGISTRY[ecosystem][name],"dependency":name,"package_id":package,
                        "ecosystem":ecosystem,
                        "declared":True,"declarations":specs,"usage":[],
                        "evidence":{"file_id":path,"blob_sha256":sha256_hex(raw)},
                        "origin":"manifest_declaration"}
                else:
                    unregistered.append({"package_id":package,"dependency":name,"status":"unregistered","manifest":path})
        except (ValueError,TypeError,AttributeError) as error:
            diagnostics.append({"file_id":path,"status":"failed","reason":str(error)})
    def owner(file, ecosystem):
        parents=[p for p in packages.values() if p["ecosystem"]==ecosystem and
                 (p["root"]=="." or file.startswith(p["root"]+"/"))]
        return max(parents,key=lambda p:len(p["root"])) if parents else None
    for parsed_file in parsed:
        ecosystem="python" if parsed_file.file_id.endswith(".py") else "npm"
        package=owner(parsed_file.file_id,ecosystem)
        for candidate in parsed_file.candidates:
            if candidate.kind!="import_specifier":
                continue
            module=candidate.attributes.get("module_path","")
            # Relative imports provide no package-framework assertion.
            if module.startswith("."):
                continue
            name=module.split(".")[0] if parsed_file.file_id.endswith(".py") else "/".join(module.split("/")[:2]) if module.startswith("@") else module.split("/")[0]
            if name not in REGISTRY[ecosystem]:
                continue
            package_id=package["package_id"] if package else "package:unassigned:"+ecosystem
            record=records.setdefault((package_id,name),{"framework":REGISTRY[ecosystem][name],"dependency":name,
                "ecosystem":ecosystem,
                "package_id":package_id,"declared":False,"declarations":[],"usage":[],"origin":"syntax_import"})
            record["usage"].append({"file_id":parsed_file.file_id,"blob_sha256":parsed_file.analysis_sha256,
                "span":[candidate.span.start,candidate.span.end],"meaning":"import_syntax"})
    return {"producer":"seremy.frameworks/0.1","profile":"exact-manifest-and-import-v0.1",
            "packages":list(packages.values()),"frameworks":list(records.values()),"diagnostics":diagnostics,
            "unregistered_dependencies":unregistered,
            "capabilities":{"manifest_declarations":"supported","import_syntax":"supported",
                            "routes_di_orm_semantics":"unsupported"}}


def structural_views(entities, frameworks, files=()):
    packages=frameworks["packages"]
    directory, deployable = {}, {}
    for entity in entities:
        path=entity["file_id"]
        directory[entity["entity_id"]]="directory:"+PurePosixPath(path).parent.as_posix()
        ecosystem="python" if path.endswith(".py") else "npm"
        owners=[p for p in packages if p["ecosystem"]==ecosystem and
                (p["root"]=="." or path.startswith(p["root"]+"/"))]
        if owners:
            deployable[entity["entity_id"]]=max(owners,key=lambda p:len(p["root"]))["package_id"]
    def view(kind, membership):
        groups=set(membership.values())
        if kind=="structural_directory":
            groups.update("directory:"+PurePosixPath(path).parent.as_posix() for path in files)
        return {"target":kind,"membership":dict(sorted(membership.items())),
                "groups":sorted(groups),
                "unassigned":sorted(e["entity_id"] for e in entities if e["entity_id"] not in membership),
                "version":sha256_hex(canonical_bytes(membership))}
    return {"producer":"seremy.components/0.1","views":[view("structural_directory",directory),
            view("deployable_package",deployable)],
            "semantic_component":{"status":"unsupported","reason":"algorithm_not_qualified"},
            "architectural_layer":{"status":"unsupported","reason":"authored_mapping_required"}}


def typed_edges(edges):
    return [dict(edge,edge_id=sha256_hex(canonical_bytes(edge))) for edge in edges]


def aggregate(edges, view):
    mapping=view["membership"]
    grouped={}
    unassigned=[]
    for edge in typed_edges(edges):
        source,target=mapping.get(edge["source"]),mapping.get(edge["target"])
        if source is None and view.get("target")=="structural_directory" and edge.get("source_type")=="file_ref":
            source="directory:"+PurePosixPath(edge["source"].removeprefix("file:")).parent.as_posix()
        if source is None or target is None:
            unassigned.append(edge["edge_id"])
            continue
        key=(source,target,edge["kind"],edge["origin"])
        record=grouped.setdefault(key,{"source":source,"target":target,"kind":edge["kind"],
            "origin":edge["origin"],"edge_ids":[],"site_count":0})
        record["edge_ids"].append(edge["edge_id"])
        record["site_count"]+=len(edge["occurrences"])
    return {"membership_version":view["version"],"edges":[dict(grouped[k],distinct_edge_count=len(grouped[k]["edge_ids"])) for k in sorted(grouped)],
            "unassigned_edge_ids":sorted(unassigned)}


def shortest_path(edges, source, target, *, kinds=("CALLS",), max_visited=10000):
    if max_visited<1:
        raise ValueError("max_visited must be positive")
    adjacency=defaultdict(list)
    for e in typed_edges(edges):
        if e["kind"] in kinds and e["origin"]=="binder_observation":
            adjacency[e["source"]].append(e)
    pending=deque([(source,[])])
    seen={source}
    while pending:
        current,path=pending.popleft()
        if current==target:
            return {"status":"observed_static_path","depth":len(path),"witness":path}
        for edge in sorted(adjacency[current],key=lambda e:e["edge_id"]):
            if edge["target"] in seen:
                continue
            if len(seen)>=max_visited:
                return {"status":"truncated","depth":None,"witness":[]}
            seen.add(edge["target"])
            pending.append((edge["target"],path+[edge["edge_id"]]))
    return {"status":"no_path","depth":None,"witness":[]}


def component_cycles(edges):
    """Iterative reachability finds cycle membership without recursion limits."""
    adjacent=defaultdict(set)
    for edge in edges:
        adjacent[edge["source"]].add(edge["target"])
    remaining=set(adjacent)|{t for targets in adjacent.values() for t in targets}
    cycles=[]
    # SCCs are the intersection of forward and reverse reachability.
    reverse=defaultdict(set)
    for source,targets in adjacent.items():
        for target in targets:
            reverse[target].add(source)
    def reach(node, graph):
        seen={node};todo=[node]
        while todo:
            for nxt in graph[todo.pop()]-seen:
                seen.add(nxt);todo.append(nxt)
        return seen
    while remaining:
        node=min(remaining)
        group=reach(node,adjacent)&reach(node,reverse)
        remaining-=group
        if len(group)>1 or node in adjacent[node]:
            cycles.append(sorted(group))
    return sorted(cycles)

