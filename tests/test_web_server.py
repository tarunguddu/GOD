"""End-to-end test of the actual HTTP server (covers the request handler)."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from god_agent.agent import GodAgent
from god_agent.config import Config
from god_agent.web import WebAPI, _make_handler


@pytest.fixture
def server(project):
    agent = GodAgent(Config.load(project))
    agent.fs.write_file("src/m.py", "def ok():\n    return 1\n")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                _make_handler(WebAPI(agent), {"127.0.0.1", "localhost"}))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read()


def _post(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read())


def test_dashboard_html(server):
    status, body = _get(server + "/")
    assert status == 200
    assert b"GOD Coding Agent" in body


def test_status_json(server):
    status, body = _get(server + "/api/status")
    assert status == 200
    assert json.loads(body)["llm_provider"] == "mock"


def test_critique_post_roundtrip(server):
    status, body = _post(server + "/api/critique",
                         {"code": "def e(x):\n    return eval(x)\n", "filename": "x.py"})
    assert status == 200
    assert body["blocking"] is True


def test_post_invalid_json(server):
    req = urllib.request.Request(server + "/api/critique", data=b"{not json",
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "expected HTTP 400"
    except urllib.error.HTTPError as e:
        assert e.code == 400


def test_oversized_body_rejected(server):
    # Declare a huge Content-Length -> rejected with 413 before reading a body.
    import http.client
    from urllib.parse import urlparse
    u = urlparse(server)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
    conn.putrequest("POST", "/api/critique")
    conn.putheader("Content-Length", str(2_000_000))
    conn.putheader("Content-Type", "application/json")
    conn.endheaders()
    conn.send(b"{}")          # send a tiny body; server should 413 on the header
    resp = conn.getresponse()
    assert resp.status == 413
    conn.close()


def test_bad_host_rejected(server):
    req = urllib.request.Request(server + "/api/status", headers={"Host": "evil.example.com"})
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "expected rejection"
    except urllib.error.HTTPError as e:
        assert e.code == 421
