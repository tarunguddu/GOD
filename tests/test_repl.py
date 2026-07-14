"""Drive full REPL sessions deterministically via injected reader/writer."""
from god_agent.agent import GodAgent
from god_agent.config import Config
from god_agent.llm.base import LLMProvider, LLMResponse
from god_agent.reasoning.generator import CodeGenerator
from god_agent.ui.repl import Repl


class ScriptedProvider(LLMProvider):
    name = "scripted"

    def __init__(self, responses):
        self._responses = list(responses)
        self.model = "scripted-1"

    def complete(self, request):
        text = self._responses.pop(0) if self._responses else "(no more)"
        return LLMResponse(text=text, model=self.model, provider=self.name, usage={})


def _session(project, inputs, responses=None):
    agent = GodAgent(Config.load(project))
    if responses is not None:
        agent.llm.provider = ScriptedProvider(responses)
        agent.reasoning.generator = CodeGenerator(agent.llm, agent.reasoning.critic)
    out: list[str] = []
    it = iter(inputs)

    def reader():
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    repl = Repl(agent=agent, reader=reader, writer=out.append, color=False,
                verify_command="python -c \"print('1 passed')\"")
    repl.run()
    return agent, "\n".join(out)


def test_opening_shows_provider_and_health(project):
    _, out = _session(project, ["/quit"])
    assert "interactive session" in out
    assert "provider:" in out
    assert "project health:" in out


def test_help_command(project):
    _, out = _session(project, ["/help", "/quit"])
    assert "/edit" in out and "/undo" in out


def test_plan_command(project):
    _, out = _session(project, ["/plan add an export feature", "/quit"])
    assert "Plan" in out and "verify" in out.lower()


def test_critique_command_flags_eval(project):
    agent_proj = project
    (agent_proj / "src" / "danger.py").write_text(
        "def e(x):\n    return eval(x)\n", encoding="utf-8")
    _, out = _session(project, ["/critique src/danger.py", "/quit"])
    assert "vuln:dynamic-exec" in out


def test_unknown_command(project):
    _, out = _session(project, ["/frobnicate", "/quit"])
    assert "unknown command" in out


def test_edit_preview_and_apply(project):
    code = "```python\ndef double(x):\n    return x * 2\n```"
    inputs = ["/edit src/dbl.py make a double function", "y", "/quit"]
    agent, out = _session(project, inputs, responses=[code])
    assert "proposed change to src/dbl.py" in out
    assert "+def double" in out          # diff preview
    assert "ACCEPTED" in out
    assert agent.fs.exists("src/dbl.py")


def test_edit_skipped_when_not_approved(project):
    code = "```python\ndef f():\n    return 1\n```"
    inputs = ["/edit src/f.py make f", "n", "/quit"]
    agent, out = _session(project, inputs, responses=[code])
    assert "skipped." in out
    assert not agent.fs.exists("src/f.py")


def test_edit_rejects_blocking_code_without_prompting(project):
    bad = "```python\nKEY = \"AKIA1234567890ABCDEF\"\n```"
    inputs = ["/edit src/leak.py store key", "/quit"]
    agent, out = _session(project, inputs, responses=[bad, bad])
    assert "rejected by self-critique" in out
    assert not agent.fs.exists("src/leak.py")


def test_undo_rolls_back_last_edit(project):
    code = "```python\ndef g():\n    return 7\n```"
    inputs = ["/edit src/g.py make g", "y", "/undo", "/quit"]
    agent, out = _session(project, inputs, responses=[code])
    assert "rolled back" in out
    assert not agent.fs.exists("src/g.py")


def test_changes_tracking(project):
    code = "```python\ndef h():\n    return 1\n```"
    inputs = ["/edit src/h.py make h", "y", "/changes", "/quit"]
    agent, out = _session(project, inputs, responses=[code])
    assert "src/h.py" in out.split("changes")[-1] or "1. src/h.py" in out


def test_command_error_does_not_kill_session(project):
    _, out = _session(project, ["/critique does_not_exist.py", "/help", "/quit"])
    assert "file not found" in out
    assert "/edit" in out          # session continued to /help
