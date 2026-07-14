from god_agent.agent import GodAgent
from god_agent.config import Config
from god_agent.llm.base import LLMProvider, LLMRequest, LLMResponse
from god_agent.reasoning.generator import CodeGenerator


class ScriptedProvider(LLMProvider):
    name = "scripted"

    def __init__(self, responses):
        self._responses = list(responses)

    def complete(self, request: LLMRequest) -> LLMResponse:
        text = self._responses.pop(0)
        return LLMResponse(text=text, model="scripted", provider=self.name,
                           usage={})


def _agent_with(project, responses):
    agent = GodAgent(Config.load(project))
    # swap in a scripted provider + rebuild the generator around it
    agent.llm.provider = ScriptedProvider(responses)
    agent.reasoning.generator = CodeGenerator(agent.llm, agent.reasoning.critic)
    return agent


def test_generate_and_apply_accepts_clean_verified(project):
    code = "```python\ndef double(x):\n    return x * 2\n```"
    agent = _agent_with(project, [code])
    outcome = agent.reasoning.generate_and_apply(
        "add a double function",
        "src/dbl.py",
        verify_command="python -c \"print('1 passed')\"",
    )
    assert outcome.accepted
    assert agent.fs.exists("src/dbl.py")
    assert "generated in 1 pass" in outcome.reason


def test_generate_and_apply_rejects_unfixable_secret(project):
    bad = "```python\nKEY = \"AKIA1234567890ABCDEF\"\n```"
    agent = _agent_with(project, [bad, bad])
    outcome = agent.reasoning.generate_and_apply(
        "store the api key", "src/secret.py",
        verify_command="python -c \"print('1 passed')\"",
    )
    assert not outcome.accepted
    assert not agent.fs.exists("src/secret.py")   # never written


def test_generate_and_apply_rolls_back_on_failed_verification(project):
    code = "```python\ndef ok():\n    return 1\n```"
    agent = _agent_with(project, [code])
    outcome = agent.reasoning.generate_and_apply(
        "add ok", "src/ok.py",
        verify_command="python -c \"raise SystemExit(1)\"",
    )
    assert not outcome.accepted
    assert outcome.rolled_back
    assert not agent.fs.exists("src/ok.py")


def test_generate_and_apply_handles_empty_generation(project):
    # Default max_passes=2 -> the empty-code retry will request twice.
    agent = _agent_with(project, ["sorry, no code here", "still nothing useful"])
    outcome = agent.reasoning.generate_and_apply(
        "do nothing useful", "src/none.py",
        verify_command="python -c \"print('1 passed')\"",
    )
    assert not outcome.accepted
    assert "no usable code" in outcome.reason
