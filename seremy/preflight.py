"""Bounded hosted repository inspection, before any syntax/compiler work."""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from seremy.github_input import (fetch, resolve_commit, scoped_archive, validate_archive,
                                 MAX_ARCHIVE, MAX_SCOPED_DOWNLOAD)
from seremy.input_errors import public_failure
from seremy.language_profiles import SOURCE_EXTENSIONS
from seremy.snapshot import EXCLUDED


def limits(timeout=180):
    return {"archive_bytes": MAX_ARCHIVE, "scoped_download_bytes": MAX_SCOPED_DOWNLOAD,
            "extracted_bytes": 8 * 1024 * 1024, "entry_count": 1000,
            "file_bytes": 1024 * 1024, "analysis_seconds": timeout,
            "source_extensions": sorted(SOURCE_EXTENSIONS)}


def inspect_archive(raw, subdirectory=""):
    """Read bounded source bytes for warnings; never import or execute code."""
    validate_archive(raw, compressed_limit=MAX_SCOPED_DOWNLOAD if subdirectory else MAX_ARCHIVE)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        files = [item for item in entries if not item.is_dir()]
        # Match the analyzer's single top-level directory unwrapping.
        roots = {PurePosixPath(item.filename).parts[0] for item in entries if item.filename}
        unwrap = len(roots) == 1 and all("/" in item.filename.rstrip("/") for item in files)
        supported = Counter()
        other = Counter()
        source_bytes = 0
        folders = Counter()
        dense = []
        warnings = []
        for item in files:
            parts = PurePosixPath(item.filename).parts
            relative = parts[1:] if unwrap else parts
            if subdirectory:
                relative = relative[len(PurePosixPath(subdirectory).parts):]
            path = PurePosixPath(*relative)
            if set(relative) & EXCLUDED:
                continue
            if path.suffix not in SOURCE_EXTENSIONS:
                other[path.suffix or "(no extension)"] += 1
                continue
            supported[path.suffix] += 1
            source_bytes += item.file_size
            if len(relative) > 1:
                folders[relative[0]] += 1
            if item.file_size >= 64 * 1024 and path.suffix in {".js", ".jsx", ".ts", ".tsx"}:
                raw_source = archive.read(item)
                longest = max((len(line) for line in raw_source.splitlines()), default=0)
                if item.file_size >= 256 * 1024 or longest >= 2000 or path.name.endswith(".min.js"):
                    dense.append({"path": path.as_posix(), "bytes": item.file_size,
                                  "longest_line_bytes": longest})
        if dense:
            warnings.append("Large or dense JavaScript/TypeScript files may be compiled bundles. They can slow analysis and crowd the map. Consider a source folder; files are not silently excluded.")
        if other.get(".html") or other.get(".css"):
            warnings.append("HTML and CSS are not analyzed for architecture. React JSX/TSX syntax is supported, but does not prove runtime component relationships.")
        if subdirectory:
            warnings.append("Only the selected folder will be analyzed. Configuration and dependencies outside it are not included.")
        if sum(supported.values()) == 0:
            warnings.append("No supported source files were found. Choose a folder or ZIP containing Python, JavaScript, TypeScript, JSX or TSX.")
        return {"archive_bytes": len(raw), "entry_count": len(entries),
                "file_count": len(files), "extracted_bytes": sum(i.file_size for i in files),
                "source_files": sum(supported.values()), "source_bytes": source_bytes,
                "supported": dict(sorted(supported.items())), "other_files": dict(sorted(other.items())),
                "dense_files": dense[:10], "dense_file_count": len(dense),
                "source_folders": [{"path": "/".join(filter(None, [subdirectory, name])), "source_files": count}
                                   for name, count in folders.most_common(8)],
                "warnings": warnings, "allowed": bool(supported),
                "runtime_note": "Passing these checks does not guarantee completion within the analysis time limit."}


def prepare(folder):
    folder = Path(folder)
    source_path = folder / "source.json"
    source = json.loads(source_path.read_text(encoding="utf8")) if source_path.exists() else None
    if source:
        repository = source["url"].removeprefix("https://github.com/")
        commit = resolve_commit(repository, source["revision"])
        subdirectory = source.get("subdirectory", "")
        raw = fetch(f"https://codeload.github.com/{repository}/zip/{commit}",
                    MAX_SCOPED_DOWNLOAD if subdirectory else MAX_ARCHIVE, "application/zip")
        download_bytes = len(raw)
        if subdirectory:
            raw = scoped_archive(raw, subdirectory)
        identity = {"repository_id": "git:" + source["url"],
                    "declared_root": "git:" + source["url"] + "@" + commit}
        if subdirectory:
            from urllib.parse import quote
            identity["declared_root"] += "#path=" + quote(subdirectory, safe="/")
    else:
        raw = (folder / "input.zip").read_bytes()
        download_bytes, subdirectory, commit = len(raw), "", None
        digest = hashlib.sha256(raw).hexdigest()
        identity = {"repository_id": "zip:sha256:" + digest, "declared_root": "archive:/" + digest}
    summary = inspect_archive(raw, subdirectory)
    summary.update(download_bytes=download_bytes, revision=commit, source_subdirectory=subdirectory or None)
    (folder / "prepared.zip").write_bytes(raw)
    (folder / "prepared.json").write_text(json.dumps({"snapshot_identity": identity,
        "source_subdirectory": subdirectory, "revision": commit}), encoding="utf8")
    return {"preflight": summary}


def analyze_prepared(folder, output):
    from seremy.__main__ import extract_zip
    from seremy.product import analyze, publish
    from seremy.viewer import render_map
    from seremy.progress import report_progress
    folder = Path(folder)
    metadata = json.loads((folder / "prepared.json").read_text(encoding="utf8"))
    with tempfile.TemporaryDirectory(prefix="archdoc-checked-") as temporary:
        root = Path(temporary)
        extract_zip(folder / "prepared.zip", root)
        entries = list(root.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            root = entries[0]
        if metadata["source_subdirectory"]:
            root = root.joinpath(*metadata["source_subdirectory"].split("/"))
        bundle, ir, markdown, checks = analyze(root, use_git=False, progress=report_progress,
                                             snapshot_identity=metadata["snapshot_identity"])
        report_progress("Publishing draft")
        publication = publish(output, bundle, ir, markdown, checks, render_map(bundle))
        return {"publication": str(publication), "revision": metadata["revision"],
                "source_subdirectory": metadata["source_subdirectory"] or None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-folder", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    try:
        result = analyze_prepared(args.job_folder, args.output) if args.analyze else prepare(args.job_folder)
        print(json.dumps(result))
    except (ValueError, OSError, RuntimeError, zipfile.BadZipFile) as error:
        print(json.dumps({"error": public_failure(error)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
