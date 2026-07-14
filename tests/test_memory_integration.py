"""Integration: the agent learns from each action and feeds it back."""

from god_agent.agent import GodAgent
from god_agent.config import Config
from god_agent.llm.base import LLMProvider, LLMRequest, LLMResponse
from god_agent.reasoning.generator import CodeGenerator


class CapturingProvider(LLMProvider):
    """Records the prompts it receives and returns scripted code."""

    name = "capturing"

    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts: list[str] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.prompts.append(request.user_text())
        text = self._responses.pop(0) if self._responses else "no more"
        return LLMResponse(text=text, model="capturing", provider=self.name, usage={})


def _agent_with(project, responses):
    agent = GodAgent(Config.load(project))
    agent.llm.provider = CapturingProvider(responses)
    agent.reasoning.generator = CodeGenerator(agent.llm, agent.reasoning.critic)
    return agent


def test_safe_apply_records_episode(project):
    agent = GodAgent(Config.load(project))
    agent.reasoning.safe_apply(
        "add a helper", "src/h.py", "def h():\n    return 1\n",
        verify_command="python -c \"print('1 passed')\"",
    )
    episodes = agent.memory.episodic.all()
    assert len(episodes) == 1
    assert episodes[0].accepted
    assert episodes[0].verified


def test_rejected_secret_is_remembered(project):
    agent = GodAgent(Config.load(project))
    agent.reasoning.safe_apply(
        "store key", "src/k.py", 'KEY = "AKIA1234567890ABCDEF"\n',
    )
    episodes = agent.memory.episodic.all()
    assert len(episodes) == 1
    assert not episodes[0].accepted
    assert any(r.startswith("secret:") for r in episodes[0].critique_rules)


def test_learned_guidance_is_injected_into_generation(project):
    agent = _agent_with(project, ["```python\ndef ok():\n    return 1\n```"])
    # Seed memory: conventions + a past secret mistake.
    agent.memory.learn_conventions(force=True)
    from god_agent.memory.episodic import Episode
    agent.memory.record_episode(Episode(
        task="add api key", critique_rules=["secret:aws-access-key"], accepted=False))

    agent.reasoning.generate_and_apply(
        "add api key loader", "src/loader.py",
        verify_command="python -c \"print('1 passed')\"",
    )
    prompt = agent.llm.provider.prompts[0]
    # The conventions + the learned secret lesson must appear in the prompt.
    assert "conventions" in prompt.lower()
    assert "environment" in prompt.lower()
