from god_agent.llm.base import LLMProvider, LLMRequest, LLMResponse
from god_agent.llm.orchestrator import LLMOrchestrator
from god_agent.reasoning.generator import CodeGenerator


class ScriptedProvider(LLMProvider):
    """Returns a queued list of responses, one per call."""

    name = "scripted"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        text = self._responses.pop(0)
        return LLMResponse(text=text, model="scripted", provider=self.name,
                           usage={"input_chars": 0, "output_chars": len(text)})


def _gen(responses, max_passes=2):
    provider = ScriptedProvider(responses)
    orch = LLMOrchestrator(provider)
    return CodeGenerator(orch, max_passes=max_passes), provider


def test_extracts_fenced_code():
    gen, _ = _gen(["Here you go:\n```python\ndef f():\n    return 1\n```\nDone."])
    result = gen.generate("make f", "f.py")
    assert "def f():" in result.code
    assert result.passes == 1
    assert result.usable


def test_clean_generation_no_extra_passes():
    gen, provider = _gen(["```python\ndef add(a, b):\n    return a + b\n```"])
    result = gen.generate("add fn", "add.py")
    assert result.usable
    assert len(provider.calls) == 1  # no fix pass needed


def test_fix_loop_repairs_blocking_code():
    bad = "```python\nKEY = \"AKIA1234567890ABCDEF\"\n```"
    good = "```python\nimport os\nKEY = os.environ['KEY']\n```"
    gen, provider = _gen([bad, good], max_passes=2)
    result = gen.generate("load key", "k.py")
    assert result.passes == 2
    assert len(provider.calls) == 2
    assert result.usable
    assert "os.environ" in result.code


def test_fix_loop_gives_up_after_max_passes():
    bad = "```python\ndef f(x):\n    return eval(x)\n```"
    gen, provider = _gen([bad, bad], max_passes=2)
    result = gen.generate("eval thing", "e.py")
    assert result.passes == 2
    assert not result.usable          # still blocking
    assert result.critique.blocking


def test_no_fence_prose_returns_empty_for_python():
    # max_passes=1 -> no retry; prose with no code fence yields empty code.
    gen, _ = _gen(["I cannot do that without more info."], max_passes=1)
    result = gen.generate("x", "x.py")
    assert result.code == ""
    assert not result.usable


def test_empty_code_triggers_retry():
    # First response is prose (no fence) -> empty -> retry; second has code.
    gen, provider = _gen(
        ["no code here", "```python\ndef f():\n    return 1\n```"], max_passes=2)
    result = gen.generate("make f", "f.py")
    assert result.passes == 2
    assert result.usable
    assert "def f" in result.code


def test_fix_prompt_includes_findings():
    bad = "```python\ndef f(x):\n    return eval(x)\n```"
    good = "```python\ndef f(x):\n    return int(x)\n```"
    gen, provider = _gen([bad, good], max_passes=2)
    gen.generate("parse", "p.py")
    # second prompt should reference the previous issue
    second_prompt = provider.calls[1].user_text()
    assert "dynamic-exec" in second_prompt or "previous attempt" in second_prompt.lower()
