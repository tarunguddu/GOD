"""Web interface — a read-only dashboard + JSON API over the agent.

Built on the standard library only (``http.server``), so it adds no dependency.

SECURITY POSTURE (important):
  - Binds to 127.0.0.1 by default — never exposed on a public interface.
  - There is NO authentication. Do not bind this to 0.0.0.0 or expose it on a
    network without putting an authenticating reverse proxy in front of it.
  - Only safe, read-only/compute endpoints are exposed: status, project health,
    memory, code graph, and critique-of-posted-text. Mutating, shell, sandbox,
    and generation capabilities are deliberately NOT reachable over HTTP.

The request routing is a pure function (:meth:`WebAPI.route`) so it can be unit
tested without opening a socket.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_MAX_BODY_BYTES = 1_000_000          # reject larger POST bodies (DoS guard)
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


_DASHBOARD = """<!doctype html>
<html><head><meta charset="utf-8"><title>GOD Agent</title>
<style>
 body{font-family:system-ui,sans-serif;margin:2rem;background:#0f1115;color:#e6e6e6}
 h1{font-weight:600} .card{background:#181b22;border:1px solid #262b36;border-radius:8px;
 padding:1rem 1.25rem;margin:1rem 0} pre{white-space:pre-wrap;word-break:break-word}
 .score{font-size:2rem;font-weight:700} .warn{color:#ffb454}
 button{background:#2b6cb0;color:#fff;border:0;padding:.5rem 1rem;border-radius:6px;cursor:pointer}
</style></head><body>
<h1>GOD Coding Agent</h1>
<p class="warn">Local dashboard — no authentication. Do not expose on a network.</p>
<div class="card"><h3>Status</h3><pre id="status">loading…</pre></div>
<div class="card"><h3>Health <span id="score" class="score"></span></h3><pre id="health">loading…</pre></div>
<div class="card"><h3>Memory</h3><pre id="memory">loading…</pre></div>
<script>
async function j(u){const r=await fetch(u);return r.json()}
(async()=>{
  document.getElementById('status').textContent=JSON.stringify(await j('/api/status'),null,2);
  const h=await j('/api/health');
  document.getElementById('score').textContent=h.score+'/100';
  document.getElementById('health').textContent=(h.suggestions||[]).map(s=>`[${s.severity}] ${s.category}: ${s.message} (${s.location})`).join('\\n')||'no issues';
  document.getElementById('memory').textContent=JSON.stringify(await j('/api/memory'),null,2);
})();
</script></body></html>"""


class WebAPI:
    def __init__(self, agent) -> None:  # agent: GodAgent
        self.agent = agent

    def route(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        """Pure request router. Returns (status_code, json_body)."""
        method = method.upper()
        if method == "GET" and path == "/api/status":
            return 200, self.agent.status_summary()
        if method == "GET" and path == "/api/health":
            report = self.agent.proactive.analyze()
            return 200, {
                "score": report.score,
                "scanned_files": report.scanned_files,
                "suggestions": [
                    {**asdict(s), "severity": s.severity.name}
                    for s in report.by_severity()
                ],
            }
        if method == "GET" and path == "/api/memory":
            return 200, {
                "stats": self.agent.memory.stats(),
                "conventions": (self.agent.memory.conventions().__dict__
                                if self.agent.memory.conventions() else None),
                "lessons": [l.render() for l in self.agent.memory.top_lessons()],
            }
        if method == "GET" and path == "/api/graph":
            self.agent.perceive()
            return 200, {"stats": self.agent.context.graph.stats()}
        if method == "POST" and path == "/api/critique":
            code = (body or {}).get("code", "")
            filename = (body or {}).get("filename", "<posted>")
            critique = self.agent.reasoning.critique_code(code, filename)
            return 200, {
                "summary": critique.summary(),
                "blocking": critique.blocking,
                "findings": [
                    {"severity": f.severity.name, "rule": f.rule,
                     "message": f.message, "line": f.line}
                    for f in critique.by_severity()
                ],
            }
        return 404, {"error": "not found", "path": path}


def _make_handler(api: WebAPI, allowed_hosts: set[str]):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload, content_type="application/json"):
            data = (payload if isinstance(payload, bytes)
                    else json.dumps(payload).encode("utf-8"))
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self) -> bool:
            # Reject mismatched Host headers — defeats DNS-rebinding attempts to
            # reach this unauthenticated localhost API from a browser.
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip().lower()
            return host in allowed_hosts or not host

        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                self._send(421, {"error": "host not allowed"})
                return
            if self.path in ("/", "/index.html"):
                self._send(200, _DASHBOARD.encode("utf-8"), "text/html; charset=utf-8")
                return
            status, payload = api.route("GET", self.path)
            self._send(status, payload)

        def do_POST(self):  # noqa: N802
            if not self._host_ok():
                self._send(421, {"error": "host not allowed"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self._send(400, {"error": "invalid content-length"})
                return
            if length > _MAX_BODY_BYTES:
                self._send(413, {"error": "request body too large"})
                return
            raw = self.rfile.read(length) if length > 0 else b""
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid json"})
                return
            status, payload = api.route("POST", self.path, body)
            self._send(status, payload)

        def log_message(self, *args):  # silence default logging
            return

    return Handler


def serve(agent, host: str = "127.0.0.1", port: int = 8787) -> None:
    """Run the dashboard/API server (blocking). Localhost-only by default."""
    api = WebAPI(agent)
    allowed = set(_LOCAL_HOSTS) | {host.lower()}
    server = ThreadingHTTPServer((host, port), _make_handler(api, allowed))
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"WARNING: binding to {host} exposes an UNAUTHENTICATED API. "
              f"Put an authenticating proxy in front of it or use 127.0.0.1.")
    print(f"GOD dashboard on http://{host}:{port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
