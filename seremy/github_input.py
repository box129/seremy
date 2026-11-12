"""Bounded public GitHub archive acquisition, pinned to a resolved commit."""
import argparse
import io
import json
from pathlib import Path
import re
import tempfile
from urllib.error import URLError
from urllib.parse import quote, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
import zipfile

from seremy.__main__ import extract_zip
from seremy.product import analyze, publish
from seremy.viewer import render_map

MAX_ARCHIVE = 3 * 1024 * 1024


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
            raise ValueError("Repository limit is 1,000 ZIP entries and 8 MiB extracted.")


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def fetch(url, limit, accept):
    request = Request(url, headers={"User-Agent": "SEREMY", "Accept": accept})
    try:
        with build_opener(NoRedirects()).open(request, timeout=20) as response:
            raw = response.read(limit + 1)
    except URLError as error:
        raise ValueError("GitHub import failed. Check that the repository and revision are public and try again later.") from error
    if len(raw) > limit:
        raise ValueError("GitHub response exceeds the hosted import limit.")
    return raw


def import_repository(url, revision, output):
    url, revision = github_source(url, revision)
    repository = url.removeprefix("https://github.com/")
    commit = fetch(f"https://api.github.com/repos/{repository}/commits/{quote(revision, safe='')}",
                   256, "application/vnd.github.sha").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("GitHub returned an invalid commit identifier.")
    raw = fetch(f"https://codeload.github.com/{repository}/zip/{commit}", MAX_ARCHIVE, "application/zip")
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
        bundle, ir, markdown, checks = analyze(root, use_git=False,
            snapshot_identity={"repository_id": "git:" + url, "declared_root": "git:" + url + "@" + commit})
        result = publish(output, bundle, ir, markdown, checks, render_map(bundle))
    return {"publication": str(result), "revision": commit}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--revision")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(import_repository(args.url, args.revision, args.output)))
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        print(str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
