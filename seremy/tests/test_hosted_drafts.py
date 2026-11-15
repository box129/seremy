import json
import sqlite3
import threading
import time

import pytest

from seremy.hosted import HostedApplication, make_app
from seremy.hosted_drafts import OpenAIProvider, DraftUnavailable
from seremy.tests.test_hosted import upload, finished, request
from seremy.map_bridge import MapBridge


class Provider:
    enabled = True
    model = "test-provider"
    daily_limit = 10

    def __init__(self):
        self.calls = 0
        self.release = threading.Event()
        self.release.set()
        self.invalid = False
        self.failed = False

    def generate(self, context):
        self.calls += 1
        assert self.release.wait(10)
        if self.failed:
            raise DraftUnavailable("Test provider timed out.")
        ref = "invalid-claim" if self.invalid else context["claims"][0]["claim_id"]
        return [{"text": "This file defines a function and calls it.", "kind": "explanation", "claim_ids": [ref]}], {
            "provider": "test", "model": self.model, "prompt_version": "test", "settings": {}}


@pytest.fixture
def service(tmp_path):
    provider = Provider()
    app = HostedApplication(tmp_path, draft_provider=provider)
    job = app.start(upload())
    state = finished(app, job)
    assert state["status"] == "completed", state
    loader, _ = MapBridge(tmp_path / job / "results").publication(state["version"])
    data = {"request_id": "12345678-1234-1234-1234-123456789abc", "digest": loader.meta["content_digest"],
            "scope": {"kind": "file", "value": "main.py"}, "question": "What does this do?"}
    yield app, provider, job, state["generation_token"], data
    provider.release.set()
    app.worker.shutdown()
    app.drafts.worker.shutdown()


def result(app, job, token, data):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = app.drafts.read(job, data["request_id"], token)
        if state["status"] not in {"queued", "running"}:
            return state
        time.sleep(.01)
    pytest.fail("Draft did not complete")


def test_browser_routes_delivery_and_idempotency(service):
    app, provider, job, token, data = service
    web = make_app(app)
    headers = {"HTTP_X_SEREMY_GENERATION": token}
    assert b"generation_token" not in request(web, "/api/jobs/" + job)[1]
    assert request(web, "/api/documentation/" + job, data)[0] == 403
    assert request(web, "/api/documentation/" + job, data, **headers, HTTP_ORIGIN="https://foreign.test")[0] == 403
    assert request(web, "/api/documentation/" + job, data, **headers)[0] == 202
    done = result(app, job, token, data)
    assert done["status"] == "completed", done
    draft = done["draft"]
    assert draft["generation"]["basis"] == "server_observed"
    assert not draft["accepted"] and draft["status"] == "review_required"
    assert "map.html#seremy-source=" in draft["markdown"]
    assert request(web, "/api/documentation/" + job + "/" + data["request_id"], **headers)[0] == 200
    assert request(web, "/api/documentation/" + job, data, **headers)[0] == 202
    assert provider.calls == 1
    assert request(web, "/api/documentation/" + job, {**data, "question": "different"}, **headers)[0] == 400


def test_reject_stale_scope_expired_and_foreign_capability(service):
    app, provider, job, token, data = service
    other = app.start(upload())
    assert finished(app, other)["status"] == "completed"
    with pytest.raises(PermissionError):
        app.drafts.start(other, data, token)
    for changed in ({"digest": "0" * 64}, {"scope": {"kind": "file", "value": "../state.json"}}):
        with pytest.raises(ValueError):
            app.drafts.start(job, {**data, **changed}, token)
    assert provider.calls == 0
    app.update(job, expires_at=0)
    assert request(make_app(app), "/api/documentation/" + job, data, HTTP_X_SEREMY_GENERATION=token)[0] == 404


@pytest.mark.parametrize("failure", ["invalid", "failed"])
def test_failed_provider_never_publishes_success(service, failure):
    app, provider, job, token, data = service
    setattr(provider, failure, True)
    app.drafts.start(job, data, token)
    done = result(app, job, token, data)
    assert done["status"] == "failed" and "draft" not in done
    assert provider.calls == 1


def test_duplicate_inflight_reserves_once_and_allowance_survives_restart(service):
    app, provider, job, token, data = service
    provider.release.clear()
    provider.daily_limit = 1
    app.drafts.start(job, data, token)
    app.drafts.start(job, data, token)
    with pytest.raises(DraftUnavailable, match="allowance"):
        app.drafts.start(job, {**data, "request_id": "other-request-12345678"}, token)
    provider.release.set()
    assert result(app, job, token, data)["status"] == "completed"
    restarted = HostedApplication(app.directory, draft_provider=provider)
    try:
        assert restarted.drafts.read(job, data["request_id"], token)["status"] == "completed"
        with pytest.raises(DraftUnavailable, match="allowance"):
            restarted.drafts.start(job, {**data, "request_id": "third-request-12345678"}, token)
    finally:
        restarted.worker.shutdown()
        restarted.drafts.worker.shutdown()


def test_disabled_provider_and_interrupted_job(service):
    app, provider, job, token, data = service
    provider.enabled = False
    assert request(make_app(app), "/api/documentation/" + job, data, HTTP_X_SEREMY_GENERATION=token)[0] == 503
    assert provider.calls == 0
    with sqlite3.connect(app.drafts.database) as db:
        db.execute("INSERT INTO drafts VALUES (?,?,?,?)", (job, data["request_id"], "payload", '{"status":"running"}'))
    restarted = HostedApplication(app.directory, draft_provider=provider)
    try:
        assert "restarted" in restarted.drafts.read(job, data["request_id"], token)["error"]
    finally:
        restarted.worker.shutdown()
        restarted.drafts.worker.shutdown()


def test_provider_contract_and_error_redaction(monkeypatch):
    from seremy import hosted_drafts
    monkeypatch.setenv("SEREMY_AI_API_KEY", "private-secret")
    monkeypatch.setenv("SEREMY_AI_MODEL", "operator-selected-model")
    monkeypatch.setenv("SEREMY_AI_DAILY_REQUEST_LIMIT", "3")
    provider = OpenAIProvider()
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            return json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": '{"statements":[]}'}}]}).encode()
    class Transport:
        def open(self, req, timeout):
            body = json.loads(req.data)
            assert req.full_url == "https://api.openai.com/v1/chat/completions"
            assert body["store"] is False and body["max_completion_tokens"] == 2048
            assert body["reasoning_effort"] == "low"
            assert body["response_format"]["json_schema"]["strict"] is True
            assert timeout == 60
            return Response()
    monkeypatch.setattr(hosted_drafts, "build_opener", lambda *args: Transport())
    assert provider.generate({"claims": []})[0] == []
    monkeypatch.setattr(Response, "read", lambda *args: b"private-secret invalid response")
    with pytest.raises(DraftUnavailable) as error:
        provider.generate({})
    assert "private-secret" not in str(error.value)


def test_purpose_is_validated_and_bound_to_retry_identity(service):
    app, provider, job, token, data = service
    with pytest.raises(ValueError, match="overview"):
        app.drafts.start(job, {**data, "purpose": "unknown"}, token)
    app.drafts.start(job, {**data, "purpose": "walkthrough"}, token)
    done = result(app, job, token, data)
    assert done["draft"]["documentation_purpose"] == "walkthrough"
    assert done["draft"]["title"].startswith("How it works")
    with pytest.raises(ValueError, match="identity"):
        app.drafts.start(job, {**data, "purpose": "overview"}, token)
    assert provider.calls == 1
