import base64
import io
import json
import zipfile

import pytest

from seremy.hosted import HostedApplication, make_app
from seremy.preflight import inspect_archive, prepare, analyze_prepared
from seremy.tests.test_hosted import upload, request, finished


def archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path, content in files.items():
            output.writestr(path, content)
    return buffer.getvalue()


def test_source_inventory_warns_about_bundles_and_html_without_dropping_source():
    raw = archive({"repo/main.py": "print('test')", "repo/src/main.jsx": "const A = () => <div/>;",
                   "repo/static/app.js": "const x = 1;" * 6000, "repo/index.html": "<h1>Hi</h1>",
                   "repo/node_modules/vendor/index.js": "ignored()"})
    result = inspect_archive(raw)
    assert result["source_files"] == 3
    assert result["dense_files"][0]["path"] == "static/app.js"
    assert result["source_folders"] == [{"path": "src", "source_files": 1}, {"path": "static", "source_files": 1}]
    assert any("HTML and CSS" in warning for warning in result["warnings"])
    assert result["allowed"]


@pytest.mark.parametrize("files", [
    {"huge.py": b"x" * (1024 * 1024 + 1)},
    {f"file{i}.py": "" for i in range(1001)},
    {f"file{i}.py": b"x" * 1024 * 1024 for i in range(9)},
])
def test_extraction_limits_rejected_before_parser(files):
    with pytest.raises(ValueError, match="limit"):
        inspect_archive(archive(files))


def test_preflight_cannot_start_analysis_without_confirmation(tmp_path):
    service = HostedApplication(tmp_path)
    app = make_app(service)
    try:
        code, raw = request(app, "/api/jobs", {**upload(), "preflight": True})
        assert code == 202
        reply = json.loads(raw)
        job = reply["id"]
        state = finished(service, job)
        assert state["status"] == "ready", state
        assert state["preflight"]["source_files"] == 2
        assert not (tmp_path / job / "results").exists()
        assert request(app, "/reports/" + job + "/graph.json")[0] == 404
        assert request(app, "/api/analyze/" + job, {})[0] == 403
        assert request(app, "/api/analyze/" + job, {}, HTTP_X_ARCHDOC_GENERATION=reply["generation_token"])[0] == 202
        assert request(app, "/api/analyze/" + job, {}, HTTP_X_ARCHDOC_GENERATION=reply["generation_token"])[0] == 400
        state = finished(service, job)
        assert state["status"] == "completed", state
        assert state["coverage"]["s02"]["parsed_file_records"] == 2
        assert not (tmp_path / job / "prepared.zip").exists()
        assert json.loads(request(app, "/api/limits")[1])["analysis_seconds"] == 180
    finally:
        service.worker.shutdown()


def test_no_source_and_cancelled_check_do_not_run_parser(tmp_path):
    service = HostedApplication(tmp_path)
    try:
        raw = archive({"index.html": "hello"})
        job = service.start({"kind": "zip", "value": base64.b64encode(raw).decode(), "preflight": True})
        state = finished(service, job)
        assert state["status"] == "failed"
        assert "No supported" in state["error"]
        assert not (tmp_path / job / "prepared.zip").exists()
        job = service.start({**upload(), "preflight": True})
        assert finished(service, job)["status"] == "ready"
        service.cancel(job)
        assert service.state(job)["status"] == "cancelled"
        assert not (tmp_path / job / "prepared.zip").exists()
    finally:
        service.worker.shutdown()


def test_github_check_reuses_exact_commit_and_scope_without_second_download(tmp_path, monkeypatch):
    from seremy import preflight
    sha = "a" * 40
    raw = archive({"repo/src/main.py": "def target(): return 1\ntarget()\n", "repo/other.py": "other()"})
    (tmp_path / "source.json").write_text(json.dumps({"url": "https://github.com/example/repo", "revision": "main", "subdirectory": "src"}))
    monkeypatch.setattr(preflight, "resolve_commit", lambda *args: sha)
    calls = []
    def fetch(*args):
        calls.append(args)
        return raw
    monkeypatch.setattr(preflight, "fetch", fetch)
    checked = prepare(tmp_path)
    assert checked["preflight"]["source_files"] == 1
    assert checked["preflight"]["revision"] == sha
    monkeypatch.setattr(preflight, "fetch", lambda *args: pytest.fail("analysis downloaded a different archive"))
    result = analyze_prepared(tmp_path, tmp_path / "results")
    graph = json.loads((__import__('pathlib').Path(result["publication"]) / "graph.json").read_text())
    assert graph["contents"]["snapshot"]["declared_root"].endswith("@" + sha + "#path=src")
    assert result["source_subdirectory"] == "src"
    assert len(calls) == 1
