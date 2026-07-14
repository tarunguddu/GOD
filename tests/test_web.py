from god_agent.agent import GodAgent
from god_agent.config import Config
from god_agent.web import WebAPI


def _api(project):
    return WebAPI(GodAgent(Config.load(project)))


def test_status_endpoint(project):
    api = _api(project)
    status, body = api.route("GET", "/api/status")
    assert status == 200
    assert body["llm_provider"] == "mock"
    assert "python" in body["stacks"]


def test_health_endpoint(project):
    api = _api(project)
    api.agent.fs.write_file("src/danger.py", "def e(x):\n    return eval(x)\n")
    status, body = api.route("GET", "/api/health")
    assert status == 200
    assert 0 <= body["score"] <= 100
    assert any(s["category"] == "security" for s in body["suggestions"])


def test_memory_endpoint(project):
    api = _api(project)
    status, body = api.route("GET", "/api/memory")
    assert status == 200
    assert "stats" in body


def test_critique_post(project):
    api = _api(project)
    status, body = api.route("POST", "/api/critique",
                             {"code": "def e(x):\n    return eval(x)\n",
                              "filename": "x.py"})
    assert status == 200
    assert body["blocking"] is True
    assert any(f["rule"] == "vuln:dynamic-exec" for f in body["findings"])


def test_unknown_route_404(project):
    api = _api(project)
    status, body = api.route("GET", "/api/nope")
    assert status == 404
    assert "error" in body


def test_no_mutating_endpoints_exposed(project):
    # The API must not expose generate/shell/sandbox over HTTP.
    api = _api(project)
    for path in ("/api/generate", "/api/shell", "/api/sandbox", "/api/apply"):
        status, _ = api.route("POST", path, {})
        assert status == 404
