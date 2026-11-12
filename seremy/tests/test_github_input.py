import base64
import json
from pathlib import Path

import pytest

from seremy import github_input
from seremy.tests.test_hosted import upload


@pytest.mark.parametrize("url", ["http://github.com/owner/repo", "https://127.0.0.1/repo/x",
    "https://github.com.example/owner/repo", "https://token@github.com/owner/repo",
    "https://github.com:443/owner/repo", "https://github.com/owner/repo?url=other",
    "https://github.com/owner/repo/tree/main", "https://github.com/../repo",
    "https://github.com/%2f/repo", "https://github.com/owner/repo#fragment"])
def test_github_source_rejects_non_repository_urls(url):
    with pytest.raises(ValueError):
        github_input.github_source(url)


def test_github_import_pins_commit_and_uses_fixed_download_hosts(tmp_path, monkeypatch):
    commit = "a" * 40
    calls = []
    raw = base64.b64decode(upload()["value"])

    def fetch(url, limit, accept):
        calls.append((url, limit, accept))
        return commit.encode() if len(calls) == 1 else raw

    monkeypatch.setattr(github_input, "fetch", fetch)
    result = github_input.import_repository("https://github.com/example/repository.git", "feature/import", tmp_path / "results")
    assert result["revision"] == commit
    assert calls[0][0] == "https://api.github.com/repos/example/repository/commits/feature%2Fimport"
    assert calls[1][0] == "https://codeload.github.com/example/repository/zip/" + commit
    bundle = json.loads((Path(result["publication"]) / "graph.json").read_text())
    assert bundle["contents"]["snapshot"]["repository_id"] == "git:https://github.com/example/repository"
    assert commit in json.dumps(bundle["contents"]["snapshot"])
    assert bundle["contents"]["coverage"]["s03"]["direct_edge_count"] == 2


def test_github_invalid_commit_response_cannot_select_download_host(tmp_path, monkeypatch):
    monkeypatch.setattr(github_input, "fetch", lambda *args: b"https://internal.example/")
    with pytest.raises(ValueError, match="invalid commit"):
        github_input.import_repository("https://github.com/example/repository", None, tmp_path)


def test_archive_cap_and_redirect_rejection():
    with pytest.raises(ValueError, match="exceeds 3 MiB"):
        github_input.validate_archive(b"0" * (github_input.MAX_ARCHIVE + 1))
    assert github_input.NoRedirects().redirect_request(None, None, 302, "", {}, "http://127.0.0.1") is None
