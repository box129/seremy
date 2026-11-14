import base64
import json
import io
from pathlib import Path
from urllib.error import HTTPError

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


def test_github_download_limit_has_specific_recovery(monkeypatch):
    class Response(io.BytesIO):
        pass
    class Opener:
        def open(self,*args,**kwargs):
            return Response(b"x"*(github_input.MAX_ARCHIVE+1))
    monkeypatch.setattr(github_input,"build_opener",lambda *args:Opener())
    with pytest.raises(github_input.InputFailure) as caught:
        github_input.fetch("https://codeload.github.com/example/repo/zip/"+"a"*40,github_input.MAX_ARCHIVE,"application/zip")
    public=github_input.public_failure(caught.value)
    assert public["code"]=="GITHUB_ARCHIVE_LIMIT"
    assert "3 MiB" in public["message"] and "local app" in public["message"]


@pytest.mark.parametrize("status,code",[(404,"GITHUB_NOT_FOUND"),(403,"GITHUB_RATE_LIMIT"),(503,"GITHUB_UNAVAILABLE")])
def test_github_http_errors_are_categorized(monkeypatch,status,code):
    class Opener:
        def open(self,*args,**kwargs):
            raise HTTPError("https://api.github.com/example",status,"upstream",{},None)
    monkeypatch.setattr(github_input,"build_opener",lambda *args:Opener())
    with pytest.raises(github_input.InputFailure) as caught:
        github_input.fetch("https://api.github.com/example",256,"application/vnd.github.sha")
    assert github_input.public_failure(caught.value)["code"]==code


@pytest.mark.parametrize("value",["../src","/src","src/../other","src\\other","src//child","src/."])
def test_source_folder_must_be_contained(value):
    with pytest.raises(ValueError):
        github_input.source_subdirectory(value)


def test_scoped_import_excludes_large_assets_and_keeps_scope_identity(tmp_path,monkeypatch):
    import zipfile
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,"w") as archive:
        archive.writestr("repo/src/entry.ts","export function entry(){return 1}")
        archive.writestr("repo/website/huge.gif",b"x"*(2*1024*1024))
        archive.writestr("repo/tsconfig.json",'{"extends":"./outside.json"}')
    calls=[]
    def fetch(url,limit,accept):
        calls.append(limit)
        return b"a"*40 if len(calls)==1 else raw.getvalue()
    monkeypatch.setattr(github_input,"fetch",fetch)
    result=github_input.import_repository("https://github.com/example/repo",None,tmp_path/"results","src")
    assert calls==[256,github_input.MAX_SCOPED_DOWNLOAD]
    graph=json.loads((Path(result["publication"])/"graph.json").read_text())
    assert set(graph["contents"]["source_texts"])=={"entry.ts"}
    assert graph["contents"]["snapshot"]["declared_root"].endswith("#path=src")
    guide=(Path(result["publication"])/"architecture.md").read_text(encoding="utf8")
    assert "not a full-repository analysis" in guide
    assert result["source_subdirectory"]=="src"
    with pytest.raises(github_input.InputFailure) as caught:
        github_input.scoped_archive(raw.getvalue(),"missing")
    assert caught.value.code=="GITHUB_FOLDER_NOT_FOUND"


def test_scoped_archive_rejects_traversal(tmp_path):
    import zipfile
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,"w") as archive:
        archive.writestr("repo/src/../escape.ts","export function bad(){}")
    with pytest.raises(ValueError,match="unsafe"):
        github_input.scoped_archive(raw.getvalue(),"src")
