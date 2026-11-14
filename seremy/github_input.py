"""Bounded public GitHub archive acquisition, pinned to a resolved commit."""
import argparse
import io
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.error import URLError, HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
import zipfile

from seremy.__main__ import extract_zip
from seremy.product import analyze, publish
from seremy.viewer import render_map
from seremy.input_errors import InputFailure, public_failure

MAX_ARCHIVE = 3 * 1024 * 1024
MAX_SCOPED_DOWNLOAD = 16 * 1024 * 1024


def source_subdirectory(value):
    value="" if value is None else value
    if not isinstance(value,str) or len(value)>128 or (value and (
        "\\" in value or not re.fullmatch(r"[A-Za-z0-9_./ -]+",value) or
        any(part in {"",".",".."} for part in value.split("/")))):
        raise ValueError("Source folder must be a relative repository path such as src, without dot segments.")
    return value


def scoped_archive(raw, subdirectory):
    """Explicitly chosen repository subset; keep extraction and entry bounds."""
    subdirectory=source_subdirectory(subdirectory)
    with zipfile.ZipFile(io.BytesIO(raw)) as source:
        entries=source.infolist()
        if len(entries)>1000:
            raise InputFailure("ARCHIVE_EXTRACTION_LIMIT","Too many repository entries.")
        roots=set()
        for item in entries:
            path=PurePosixPath(item.filename)
            if path.is_absolute() or "\\" in item.filename or any(part in {".",".."} or ":" in part for part in path.parts):
                raise ValueError("unsafe repository archive path")
            if path.parts:
                roots.add(path.parts[0])
        if len(roots)!=1:
            raise ValueError("GitHub archive must have one repository root")
        prefix=next(iter(roots))+"/"+subdirectory+"/"
        selected=[item for item in entries if item.filename.startswith(prefix) and item.filename!=prefix]
        if not any(not item.is_dir() for item in selected):
            raise InputFailure("GITHUB_FOLDER_NOT_FOUND","Source folder was not found in this revision.")
        if sum(item.file_size for item in selected)>8*1024*1024 or any(item.file_size>1024*1024 for item in selected):
            raise InputFailure("ARCHIVE_EXTRACTION_LIMIT","Selected source folder exceeds extraction limits.")
        output=io.BytesIO()
        with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as target:
            for item in selected:
                # Preserve link metadata so the shared extractor can reject links.
                target.writestr(item,source.read(item))
        return output.getvalue()


def github_source(value, revision=None):
    url = urlsplit(value)
    if url.scheme != "https" or url.netloc != "github.com" or url.query or url.fragment:
        raise ValueError("Use a public https://github.com/owner/repository URL.")
    parts = url.path.strip("/").split("/")
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", part) and part not in {".", ".."} for part in parts):
        raise ValueError("Use a repository URL and enter its branch or tag separately.")
    owner, repo = parts
    repo = repo.removesuffix(".git")
    if not repo:
        raise ValueError("Repository name is required.")
    if revision is not None and (not isinstance(revision, str) or not re.fullmatch(r"[A-Za-z0-9_./-]{1,128}", revision)):
        raise ValueError("Invalid branch, tag or commit.")
    return f"https://github.com/{owner}/{repo}", revision or "HEAD"


def validate_archive(raw):
    if len(raw) > MAX_ARCHIVE:
        raise ValueError("Repository archive exceeds 3 MiB. Upload a smaller ZIP or use the local app.")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.infolist()) > 1000 or sum(item.file_size for item in archive.infolist()) > 8 * 1024 * 1024:
            raise InputFailure("ARCHIVE_EXTRACTION_LIMIT", "Repository limit is 1,000 ZIP entries and 8 MiB extracted.")


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def fetch(url, limit, accept):
    request = Request(url, headers={"User-Agent": "SEREMY", "Accept": accept})
    try:
        with build_opener(NoRedirects()).open(request, timeout=20) as response:
            raw = response.read(limit + 1)
    except HTTPError as error:
        code="GITHUB_NOT_FOUND" if error.code==404 else "GITHUB_RATE_LIMIT" if error.code in {403,429} else "GITHUB_UNAVAILABLE"
        raise InputFailure(code,"GitHub import failed.") from error
    except (URLError, TimeoutError) as error:
        raise InputFailure("GITHUB_UNAVAILABLE","GitHub could not be reached.") from error
    if len(raw) > limit:
        raise InputFailure("GITHUB_SCOPED_DOWNLOAD_LIMIT" if limit==MAX_SCOPED_DOWNLOAD else "GITHUB_ARCHIVE_LIMIT" if limit==MAX_ARCHIVE else "GITHUB_UNAVAILABLE", "GitHub response exceeds the hosted import limit.")
    return raw


def import_repository(url, revision, output, subdirectory=None):
    url, revision = github_source(url, revision)
    subdirectory=source_subdirectory(subdirectory)
    repository = url.removeprefix("https://github.com/")
    commit = fetch(f"https://api.github.com/repos/{repository}/commits/{quote(revision, safe='')}",
                   256, "application/vnd.github.sha").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("GitHub returned an invalid commit identifier.")
    raw = fetch(f"https://codeload.github.com/{repository}/zip/{commit}", MAX_SCOPED_DOWNLOAD if subdirectory else MAX_ARCHIVE, "application/zip")
    if subdirectory:
        raw=scoped_archive(raw,subdirectory)
    else:
        validate_archive(raw)
    with tempfile.TemporaryDirectory(prefix="seremy-github-") as directory:
        directory = Path(directory)
        archive = directory / "source.zip"
        archive.write_bytes(raw)
        root = directory / "source"
        root.mkdir()
        extract_zip(archive, root)
        entries = list(root.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            root = entries[0]
        if subdirectory:
            root=root.joinpath(*subdirectory.split("/"))
        bundle, ir, markdown, checks = analyze(root, use_git=False,
            snapshot_identity={"repository_id": "git:" + url, "declared_root": "git:" + url + "@" + commit+("#path="+quote(subdirectory,safe="/") if subdirectory else "")})
        result = publish(output, bundle, ir, markdown, checks, render_map(bundle))
    return {"publication": str(result), "revision": commit,"source_subdirectory":subdirectory or None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--revision")
    parser.add_argument("--source-folder")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(import_repository(args.url, args.revision, args.output,args.source_folder)))
    except (ValueError, OSError, RuntimeError, zipfile.BadZipFile) as error:
        print(json.dumps({"error":public_failure(error)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
