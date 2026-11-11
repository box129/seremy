import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from seremy.server import Application, handler_for


def test_local_server_rejects_foreign_origins_and_paths(tmp_path):
    app=Application(tmp_path/"out")
    server=ThreadingHTTPServer(("127.0.0.1",0),handler_for(app))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    connection=HTTPConnection("127.0.0.1",server.server_port)
    try:
        connection.request("GET","/")
        response=connection.getresponse()
        assert response.status==200
        assert b"Analyze repository" in response.read()
        connection.request("POST","/api/jobs",body=json.dumps({"kind":"folder","value":"."}),
                           headers={"Origin":"https://foreign.example","Content-Type":"application/json"})
        response=connection.getresponse()
        assert response.status==403;response.read()
        connection.request("GET","/reports/../../outside")
        response=connection.getresponse()
        assert response.status==404;response.read()
        connection.request("POST","/api/jobs",body=json.dumps({"kind":"invalid","value":"."}),
                           headers={"Content-Type":"application/json"})
        response=connection.getresponse()
        assert response.status==400;response.read()
    finally:
        connection.close();server.shutdown();server.server_close();app.worker.shutdown()

