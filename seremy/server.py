"""Single-user local launcher. Bind only to loopback."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
import json
import threading
import tempfile
from urllib.parse import urlsplit
import uuid

from seremy.__main__ import input_root
from seremy.product import analyze, publish
from seremy.viewer import render_map


class Cancelled(Exception):
    pass


class Application:
    def __init__(self, output):
        self.output=Path(output).resolve()
        self.jobs={}
        self.lock=threading.Lock()
        self.worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix="seremy")

    def start(self, request):
        kind=request.get("kind")
        if kind not in {"folder","zip","git"}:
            raise ValueError("choose a folder, ZIP or Git URL")
        if not isinstance(request.get("value"),str) or not request["value"]:
            raise ValueError("repository input is required")
        job=uuid.uuid4().hex
        with self.lock:
            self.jobs[job]={"id":job,"status":"queued","stage":"Queued","cancel":threading.Event()}
        self.worker.submit(self.run,job,request)
        return job

    def update(self,job,**changes):
        with self.lock:
            self.jobs[job].update(changes)

    def state(self,job):
        with self.lock:
            value=self.jobs[job]
            return {key:val for key,val in value.items() if key!="cancel"}

    def cancel(self,job):
        with self.lock:
            self.jobs[job]["cancel"].set()

    def run(self,job,request):
        def progress(stage):
            if self.jobs[job]["cancel"].is_set():
                raise Cancelled()
            self.update(job,stage=stage,status="running")
        try:
            progress("Preparing repository")
            with tempfile.TemporaryDirectory(prefix="seremy-web-") as directory:
                args=SimpleNamespace(root=None,zip=None,git_url=None,revision=None)
                if request["kind"]=="folder":
                    args.root=request["value"]
                elif request["kind"]=="git":
                    args.git_url=request["value"]
                    args.revision=request.get("revision")
                else:
                    data=base64.b64decode(request["value"],validate=True)
                    if len(data)>10*1024*1024:
                        raise ValueError("ZIP upload limit is 10 MiB")
                    archive=Path(directory)/"source.zip"
                    archive.write_bytes(data);args.zip=str(archive)
                with input_root(args) as root:
                    root=Path(root).resolve()
                    if root==self.output or root.is_relative_to(self.output):
                        raise ValueError("output directory cannot contain the input repository")
                    if self.output.is_relative_to(root) and self.output!=root/".seremy-artifacts":
                        raise ValueError("use .seremy-artifacts or an output directory outside the input")
                    bundle,ir,markdown,checks=analyze(root,progress=progress,
                        snapshot_identity=args.snapshot_identity,use_git=args.use_git)
                    progress("Publishing draft")
                    publication=publish(self.output,bundle,ir,markdown,checks,render_map(bundle))
            self.update(job,status="completed",stage="Draft ready",publication=publication.name,
                        coverage=bundle["contents"]["coverage"])
        except Cancelled:
            self.update(job,status="cancelled",stage="Cancelled")
        except Exception as error:
            self.update(job,status="failed",stage="Failed",error=str(error))


def handler_for(application):
    class Handler(BaseHTTPRequestHandler):
        def send(self,status,content,content_type="application/json"):
            raw=content if isinstance(content,bytes) else json.dumps(content).encode()
            self.send_response(status)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(raw)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.end_headers();self.wfile.write(raw)

        def local_request(self):
            host=self.headers.get("Host","")
            if host not in {f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}"}:
                return False
            origin=self.headers.get("Origin")
            return origin is None or origin in {f"http://127.0.0.1:{self.server.server_port}",f"http://localhost:{self.server.server_port}"}

        def do_GET(self):
            if not self.local_request():
                self.send(403,{"error":"loopback access required"});return
            route=urlsplit(self.path).path
            try:
                if route=="/":
                    self.send(200,(Path(__file__).parent/"map/launcher.html").read_bytes(),"text/html; charset=utf-8")
                elif route.startswith("/api/jobs/"):
                    self.send(200,application.state(route.removeprefix("/api/jobs/")))
                elif route.startswith("/reports/"):
                    parts=route.split("/")
                    if len(parts)!=4 or len(parts[2])!=64 or any(c not in "0123456789abcdef" for c in parts[2]):
                        raise KeyError()
                    formats={"map.html":"text/html; charset=utf-8","architecture.md":"text/plain; charset=utf-8",
                             "graph.json":"application/json","validation.json":"application/json","manifest.json":"application/json"}
                    content_type=formats[parts[3]]
                    path=application.output/"versions"/parts[2]/parts[3]
                    self.send(200,path.read_bytes(),content_type)
                else:
                    self.send(404,{"error":"not found"})
            except (KeyError,OSError):
                self.send(404,{"error":"not found"})

        def do_POST(self):
            if not self.local_request():
                self.send(403,{"error":"loopback access required"});return
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<=16*1024*1024:
                    raise ValueError("request limit is 16 MiB")
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):
                    raise ValueError("JSON object required")
                if self.path=="/api/jobs":
                    self.send(202,{"id":application.start(data)})
                elif self.path.startswith("/api/cancel/"):
                    application.cancel(self.path.removeprefix("/api/cancel/"))
                    self.send(200,{"status":"cancellation_requested"})
                else:
                    self.send(404,{"error":"not found"})
            except (ValueError,KeyError) as error:
                self.send(400,{"error":str(error)})

        def log_message(self,format,*args):
            pass
    return Handler


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--output",default=".seremy-artifacts")
    args=parser.parse_args()
    app=Application(args.output)
    server=ThreadingHTTPServer(("127.0.0.1",args.port),handler_for(app))
    print(f"SEREMY · http://127.0.0.1:{server.server_port}",flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for job in list(app.jobs):
            app.cancel(job)
        server.server_close()
        app.worker.shutdown(wait=True,cancel_futures=True)


if __name__=="__main__":
    main()

