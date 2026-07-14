"""Real HTTP round-trip against a local fake OpenAI-compatible server.

Proves the actual urllib transport works end-to-end (what local runners like
Ollama / LM Studio / vLLM depend on), not just the injected fake transport.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from god_agent.llm.base import LLMRequest, Message
from god_agent.llm.openai_compat import OpenAICompatibleProvider


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        # echo back the user's content as an OpenAI-shaped chat completion
        user = next((m["content"] for m in body["messages"] if m["role"] == "user"), "")
        payload = {
            "model": body["model"],
            "choices": [{"message": {"role": "assistant", "content": f"echo: {user}"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        }
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        return


@pytest.fixture
def local_server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    host, port = httpd.server_address
    yield f"http://127.0.0.1:{port}/v1"
    httpd.shutdown()
    httpd.server_close()


def test_real_http_roundtrip(local_server):
    # requires_key=False mimics a local server (Ollama/LM Studio)
    provider = OpenAICompatibleProvider(
        "local-model", local_server, requires_key=False)
    resp = provider.complete(LLMRequest(messages=[Message("user", "ping")]))
    assert resp.text == "echo: ping"
    assert resp.usage == {"input_tokens": 7, "output_tokens": 3}
