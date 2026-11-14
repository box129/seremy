import base64
import io
import json
import threading
import time
import zipfile

import pytest

from seremy.hosted import HostedApplication, make_app


def upload():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("repo/main.py", "def target(): return 1\n\ntarget()\n")
        output.writestr("repo/main.ts", "export function target() { return 1; }\ntarget();\n")
    return {"kind": "zip", "value": base64.b64encode(archive.getvalue()).decode()}


def request(app, path, data=None, **headers):
    raw = json.dumps(data).encode() if data is not None else b""
    environ = {"REQUEST_METHOD": "POST" if data is not None else "GET", "PATH_INFO": path,
               "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(raw)),
               "HTTP_HOST": "example.test", "wsgi.input": io.BytesIO(raw), **headers}
    statuses = []
    body = b"".join(app(environ, lambda status, response_headers: statuses.append(status)))
    return int(statuses[0].split()[0]), body


def finished(app, job):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        state = app.state(job)
        if state["status"] not in {"queued", "running"}:
            return state
        time.sleep(.05)
    pytest.fail("hosted analysis did not finish")


def test_hosted_upload_uses_both_adapters_and_private_results(tmp_path):
    service = HostedApplication(tmp_path)
    app = make_app(service)
    try:
        assert request(app, "/api/jobs", upload(), HTTP_ORIGIN="https://foreign.test")[0] == 403
        assert request(app, "/api/jobs", {"kind": "folder", "value": "."})[0] == 400
        assert request(app, "/api/jobs", {"kind": "zip", "value": "!!"})[0] == 400
        code, raw = request(app, "/api/jobs", upload())
        assert code == 202
        job = json.loads(raw)["id"]
        state = finished(service, job)
        assert state["status"] == "completed", state
        assert state["coverage"]["s03"]["direct_edge_count"] == 2
        assert not (tmp_path / job / "input.zip").exists()
        assert request(app, f"/reports/{job}/map.html")[0] == 200
        assert request(app, f"/reports/{state['version']}/map.html")[0] == 404
        assert request(app, f"/reports/{job}/state.json")[0] == 404
        assert request(app, "/api/jobs/" + "0" * 64)[0] == 404
        service.update(job, expires_at=0)
        assert request(app, f"/reports/{job}/map.html")[0] == 404
        assert not (tmp_path / job).exists()
    finally:
        service.worker.shutdown()


def test_hosted_restart_reports_interrupted_jobs(tmp_path):
    job = "a" * 64
    (tmp_path / job).mkdir()
    (tmp_path / job / "state.json").write_text(json.dumps({"id": job, "status": "running", "expires_at": time.time() + 3600}))
    service = HostedApplication(tmp_path)
    try:
        assert service.state(job)["status"] == "failed"
        assert "restarted" in service.state(job)["error"]
    finally:
        service.worker.shutdown()


def test_hosted_timeout_terminates_analysis(tmp_path):
    service = HostedApplication(tmp_path, timeout=0)
    try:
        state = finished(service, service.start(upload()))
        assert state["status"] == "failed"
        assert "time limit" in state["error"]
    finally:
        service.worker.shutdown()


def test_hosted_queued_cancel_and_capacity(tmp_path):
    service = HostedApplication(tmp_path)
    release = threading.Event()
    service.worker.submit(release.wait)
    try:
        first, second = service.start(upload()), service.start(upload())
        assert request(make_app(service), "/api/jobs", upload())[0] == 429
        service.cancel(first)
        service.cancel(second)
        release.set()
        assert finished(service, first)["status"] == "cancelled"
        assert finished(service, second)["status"] == "cancelled"
    finally:
        release.set()
        service.worker.shutdown()


def test_hosted_preserves_known_failure_and_redacts_subprocess_output(tmp_path,monkeypatch):
    from seremy import hosted
    class FailedProcess:
        returncode=1
        def communicate(self,timeout=None):
            return json.dumps({"error":{"code":"GITHUB_ARCHIVE_LIMIT","message":"untrusted subprocess details"}}),"private traceback"
        def poll(self):
            return self.returncode
    monkeypatch.setattr(hosted.subprocess,"Popen",lambda *args,**kwargs:FailedProcess())
    service=HostedApplication(tmp_path)
    try:
        state=finished(service,service.start(upload()))
        assert state["status"]=="failed" and state["error_code"]=="GITHUB_ARCHIVE_LIMIT"
        assert "3 MiB" in state["error"]
        assert "private" not in json.dumps(state) and "untrusted" not in json.dumps(state)
    finally:
        service.worker.shutdown()
