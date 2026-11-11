"""Bounded ZIP analysis for a single hosted instance with temporary results."""
import base64
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import zipfile

ID = re.compile(r"[0-9a-f]{64}\Z")
MAX_UPLOAD = 3 * 1024 * 1024
RESULT_TTL = 3600
FORMATS = {"map.html": "text/html; charset=utf-8", "architecture.md": "text/plain; charset=utf-8",
           "graph.json": "application/json", "validation.json": "application/json", "manifest.json": "application/json"}


class Busy(ValueError):
    pass


class HostedApplication:
    def __init__(self, directory, *, timeout=180):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.lock = threading.RLock()
        self.jobs = {}
        self.cancelled = set()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hosted-analysis")
        for path in self.directory.glob("*/state.json"):
            if not ID.fullmatch(path.parent.name):
                continue
            state = json.loads(path.read_text(encoding="utf8"))
            self.jobs[path.parent.name] = state
            if state["status"] in {"queued", "running"}:
                self.update(path.parent.name, status="failed", error="The service restarted. Upload the ZIP again.")
        self.cleanup()

    def update(self, job, **changes):
        with self.lock:
            self.jobs[job].update(changes)
            path = self.directory / job / "state.json"
            temporary = path.with_suffix(".pending")
            temporary.write_text(json.dumps(self.jobs[job]), encoding="utf8")
            os.replace(temporary, path)

    def cleanup(self):
        with self.lock:
            for job, state in list(self.jobs.items()):
                if state["expires_at"] > time.time() or state["status"] in {"queued", "running"}:
                    continue
                target = (self.directory / job).resolve()
                if target.parent != self.directory or not ID.fullmatch(job):
                    raise ValueError("invalid result directory")
                shutil.rmtree(target)
                del self.jobs[job]
                self.cancelled.discard(job)

    def start(self, request):
        if request.get("kind") != "zip" or not isinstance(request.get("value"), str):
            raise ValueError("Upload a repository ZIP file.")
        if len(request["value"]) > 4 * ((MAX_UPLOAD + 2) // 3):
            raise ValueError("Choose a ZIP file up to 3 MiB.")
        raw = base64.b64decode(request["value"], validate=True)
        if len(raw) > MAX_UPLOAD:
            raise ValueError("Choose a ZIP file up to 3 MiB.")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if len(archive.infolist()) > 1000 or sum(item.file_size for item in archive.infolist()) > 8 * 1024 * 1024:
                raise ValueError("Repository limit is 1,000 ZIP entries and 8 MiB extracted.")
        with self.lock:
            self.cleanup()
            if sum(state["status"] in {"queued", "running"} for state in self.jobs.values()) >= 2 or len(self.jobs) >= 16:
                raise Busy("The analysis service is busy. Please try again later.")
            job = secrets.token_hex(32)
            folder = self.directory / job
            folder.mkdir()
            (folder / "input.zip").write_bytes(raw)
            self.jobs[job] = {"id": job, "status": "queued", "stage": "Queued", "expires_at": time.time() + RESULT_TTL}
            self.update(job)
            self.worker.submit(self.run, job)
            return job

    def state(self, job):
        with self.lock:
            self.cleanup()
            return dict(self.jobs[job])

    def cancel(self, job):
        with self.lock:
            self.state(job)
            if self.jobs[job]["status"] in {"queued", "running"}:
                self.cancelled.add(job)

    @staticmethod
    def stop(process):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.communicate()

    def run(self, job):
        folder = self.directory / job
        process = None
        outcome = {}
        try:
            if job in self.cancelled:
                outcome = {"status": "cancelled", "stage": "Cancelled"}
                return
            self.update(job, status="running", stage="Analyzing repository")
            environment = dict(os.environ, NODE_OPTIONS="--max-old-space-size=192", PYTHONDONTWRITEBYTECODE="1")
            process = subprocess.Popen([sys.executable, "-B", "-m", "seremy", "analyze", "--zip", str(folder / "input.zip"),
                                        "--output", str(folder / "results")],
                                       cwd=Path(__file__).resolve().parent.parent, env=environment,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       start_new_session=os.name != "nt")
            deadline = time.monotonic() + self.timeout
            while True:
                if job in self.cancelled:
                    self.stop(process)
                    outcome = {"status": "cancelled", "stage": "Cancelled"}
                    return
                if time.monotonic() >= deadline:
                    self.stop(process)
                    raise ValueError("Analysis reached its time limit. Try a smaller repository.")
                try:
                    stdout, stderr = process.communicate(timeout=.25)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode:
                raise ValueError("Analysis failed. Check the ZIP contents and try a smaller repository.")
            publication = Path(json.loads(stdout)["publication"])
            coverage = json.loads((publication / "graph.json").read_text(encoding="utf8"))["contents"]["coverage"]
            if job in self.cancelled:
                outcome = {"status": "cancelled", "stage": "Cancelled"}
                return
            outcome = {"status": "completed", "stage": "Draft ready", "publication": job,
                       "version": publication.name, "coverage": coverage}
        except Exception as error:
            if process is not None and process.poll() is None:
                self.stop(process)
            outcome = {"status": "failed", "stage": "Analysis failed", "error": str(error)}
        finally:
            (folder / "input.zip").unlink(missing_ok=True)
            self.update(job, **outcome)

    def report(self, job, name):
        state = self.state(job)
        if state["status"] != "completed" or name not in FORMATS:
            raise KeyError()
        return (self.directory / job / "results/versions" / state["version"] / name).read_bytes(), FORMATS[name]


def make_app(application):
    def app(environ, start_response):
        status, content_type, body = 200, "application/json", {}
        path, method = environ.get("PATH_INFO", "/"), environ["REQUEST_METHOD"]
        try:
            if method == "GET" and path == "/healthz":
                body = {"status": "ok"}
            elif method == "GET" and path == "/":
                content_type = "text/html; charset=utf-8"
                body = (Path(__file__).parent / "map/launcher.html").read_text(encoding="utf8").replace(
                    "<script>", "<script>window.SEREMY_HOSTED=true;", 1).encode()
            elif method == "GET" and path.startswith("/api/jobs/") and ID.fullmatch(path.split("/")[-1]):
                body = application.state(path.split("/")[-1])
            elif method == "GET" and path.startswith("/reports/"):
                parts = path.split("/")
                if len(parts) != 4 or not ID.fullmatch(parts[2]):
                    raise KeyError()
                body, content_type = application.report(parts[2], parts[3])
            elif method == "POST":
                origin = environ.get("HTTP_ORIGIN")
                if origin and urlsplit(origin).netloc != environ.get("HTTP_HOST"):
                    raise PermissionError()
                if environ.get("CONTENT_TYPE", "").split(";")[0] != "application/json":
                    raise ValueError("JSON input required.")
                length = int(environ.get("CONTENT_LENGTH") or 0)
                if not 0 < length <= 4 * 1024 * 1024 + 4096:
                    raise ValueError("Request exceeds the upload limit.")
                request = json.loads(environ["wsgi.input"].read(length))
                if not isinstance(request, dict):
                    raise ValueError("JSON object required.")
                if path == "/api/jobs":
                    body, status = {"id": application.start(request)}, 202
                elif path.startswith("/api/cancel/") and ID.fullmatch(path.split("/")[-1]):
                    application.cancel(path.split("/")[-1])
                    body = {"status": "cancellation_requested"}
                else:
                    raise KeyError()
            else:
                raise KeyError()
        except Busy as error:
            status, body = 429, {"error": str(error)}
        except (ValueError, zipfile.BadZipFile) as error:
            status, body = 400, {"error": str(error)}
        except PermissionError:
            status, body = 403, {"error": "Same-origin access required."}
        except (KeyError, FileNotFoundError):
            status, body = 404, {"error": "Result unavailable or expired. Upload the ZIP again."}
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        headers = [("Content-Type", content_type), ("Content-Length", str(len(raw))),
                   ("Cache-Control", "no-store"), ("Referrer-Policy", "no-referrer"),
                   ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "SAMEORIGIN")]
        start_response(f"{status} {HTTPStatus(status).phrase}", headers)
        return [raw]
    return app


def create_app():
    return make_app(HostedApplication(os.environ.get("SEREMY_DATA", "/tmp/seremy-hosted")))
