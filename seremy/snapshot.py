"""Bounded snapshot acquisition with explicit Git and plain-folder scope."""
import os
from pathlib import Path
import subprocess
from seremy.discovery import InventoryManifest, DiscoveryPolicy, ExclusionRecord
from seremy.contracts import EligibleFileRecord, sha256_hex
from seremy.git_input import run_git
from seremy.language_profiles import SOURCE_EXTENSIONS, LEGACY_SOURCE_EXTENSIONS, has_ecmascript, syntax_profile

MAX_FILES=5000
MAX_TOTAL_BYTES=64*1024*1024
MAX_FILE_BYTES=1024*1024
EXCLUDED={".git","node_modules","dist",".seremy-artifacts","__pycache__",".venv","venv"}


def read_contained(root, relative, limit=MAX_FILE_BYTES):
    root=Path(root).resolve()
    path=root/relative
    current=root
    for part in Path(relative).parts:
        if part in ("..",""):
            raise ValueError("invalid relative input path")
        current=current/part
        if current.is_symlink() or current.is_junction():
            raise ValueError("link_skipped")
    if not path.resolve().is_relative_to(root):
        raise ValueError("outside_root")
    with path.open("rb") as handle:
        before=os.fstat(handle.fileno())
        data=handle.read(limit+1)
        after=os.fstat(handle.fileno())
    if len(data)>limit:
        raise ValueError("read_limit")
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError("changed_during_read")
    if not path.resolve().is_relative_to(root):
        raise ValueError("outside_root")
    return data


def collect_snapshot(root, *, snapshot_identity=None, use_git=True):
    root=Path(root).resolve()
    if not root.is_dir():
        raise ValueError("repository folder does not exist")
    identity=snapshot_identity or {}
    diagnostics=[]
    candidates=[]
    try:
        git=run_git(["-C",str(root),"rev-parse","--is-inside-work-tree"],capture_output=True,timeout=10) if use_git else None
    except FileNotFoundError:
        git=None
    if git is not None and git.returncode==0 and git.stdout.strip()==b"true":
        listing=run_git(["-C",str(root),"ls-files","--cached","--others","--exclude-standard","-z","--","."],
                               capture_output=True,timeout=15,check=True)
        if len(listing.stdout)>8*1024*1024:
            raise ValueError("Git inventory exceeds 8 MiB")
        candidates=sorted(set(os.fsdecode(p).replace("\\","/") for p in listing.stdout.split(b"\0") if p))
        mode="git_tracked_and_nonignored"
    else:
        mode="plain_explicit_exclusions"
        visited=0
        def onerror(error):
            diagnostics.append({"status":"partial","reason":"walk_error","path":str(error.filename)})
        for current,dirs,files in os.walk(root,onerror=onerror):
            visited+=1
            if visited>MAX_FILES:
                diagnostics.append({"status":"partial","reason":"directory_limit"})
                break
            for name in list(dirs):
                p=Path(current)/name
                if name in EXCLUDED or p.is_symlink() or p.is_junction():
                    dirs.remove(name)
                    diagnostics.append({"status":"excluded","reason":"pruned_subtree","path":p.relative_to(root).as_posix()})
            dirs.sort()
            for name in sorted(files):
                candidates.append((Path(current)/name).relative_to(root).as_posix())
            if len(candidates)>MAX_FILES:
                diagnostics.append({"status":"partial","reason":"file_limit"})
                break
    selected=[path for path in candidates if not set(Path(path).parts)&EXCLUDED]
    extensions=SOURCE_EXTENSIONS if has_ecmascript(selected) else LEGACY_SOURCE_EXTENSIONS
    policy=DiscoveryPolicy(included_extensions=frozenset((*extensions,".json",".toml")),excluded_dirs=frozenset(EXCLUDED))
    manifest=InventoryManifest(identity.get("repository_id", "local:"+root.name),
                               identity.get("declared_root", root.as_posix()),policy,profile_id=syntax_profile(selected))
    contents={}
    total=0
    for index,relative in enumerate(candidates):
        path=Path(relative)
        if path.suffix not in policy.included_extensions or set(path.parts)&EXCLUDED:
            manifest.exclusions.append(ExclusionRecord(relative,"excluded_by_product_profile"))
            continue
        try:
            if index>=MAX_FILES:
                raise ValueError("file_limit")
            raw=read_contained(root,relative)
            if total+len(raw)>MAX_TOTAL_BYTES:
                raise ValueError("total_read_limit")
            total+=len(raw)
            contents[relative]=raw
            manifest.eligible.append(EligibleFileRecord(relative,sha256_hex(raw),len(raw),"complete"))
        except (OSError,ValueError) as error:
            reason=str(error) if isinstance(error,ValueError) else type(error).__name__
            manifest.eligible.append(EligibleFileRecord(relative,None,None,"not_processed",reason))
    if len(candidates)>MAX_FILES:
        diagnostics.append({"status":"partial","reason":"file_limit","unprocessed_enumerated":len(candidates)-MAX_FILES})
    manifest.excluded_by_reason={}
    for e in manifest.exclusions:
        manifest.excluded_by_reason[e.reason]=manifest.excluded_by_reason.get(e.reason,0)+1
    for e in manifest.eligible:
        if e.bucket=="not_processed":
            manifest.not_processed_by_reason[e.reason]=manifest.not_processed_by_reason.get(e.reason,0)+1
    manifest.reconcile()
    return manifest,contents,{"mode":mode,"diagnostics":diagnostics,"limits":{"files":MAX_FILES,"file_bytes":MAX_FILE_BYTES,"total_bytes":MAX_TOTAL_BYTES},
                             "plain_ignore_policy":"explicit_directory_exclusions"}

