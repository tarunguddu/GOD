from god_agent.agent import GodAgent
from god_agent.config import Config
from god_agent.llm.base import LLMProvider, LLMRequest, LLMResponse
from god_agent.loop import (
    AutonomousLoop,
    LoopLimits,
    quality_sweep_workflow,
    sequential_codegen_workflow,
)
from god_agent.reasoning.generator import CodeGenerator


class ScriptedProvider(LLMProvider):
    name = "scripted"

    def __init__(self, responses):
        self._responses = list(responses)

    def complete(self, request: LLMRequest) -> LLMResponse:
        text = self._responses.pop(0) if self._responses else "no more"
        return LLMResponse(text=text, model="scripted", provider=self.name, usage={})


def test_quality_sweep_completes_on_clean_project(project):
    agent = GodAgent(Config.load(project))
    # write a clean, passing-by-construction source file
    agent.fs.write_file("src/clean.py", "def ok():\n    return 1\n")
    loop = AutonomousLoop(agent, LoopLimits(max_runs=4, completion_threshold=2))
    workflow = quality_sweep_workflow(
        agent, verify_command="python -c \"print('1 passed')\"")
    report = loop.run("keep it clean", workflow)
    assert report.completed
    assert report.runs == 2


def test_quality_sweep_does_not_complete_when_verify_fails(project):
    agent = GodAgent(Config.load(project))
    agent.fs.write_file("src/clean.py", "def ok():\n    return 1\n")
    loop = AutonomousLoop(agent, LoopLimits(max_runs=3, completion_threshold=2))
    workflow = quality_sweep_workflow(
        agent, verify_command="python -c \"raise SystemExit(1)\"")
    report = loop.run("task", workflow)
    assert not report.completed
    assert report.runs >= 1


def test_sequential_codegen_advances_through_steps(project):
    agent = GodAgent(Config.load(project))
    agent.llm.provider = ScriptedProvider([
        "```python\ndef a():\n    return 1\n```",
        "```python\ndef b():\n    return 2\n```",
    ])
    agent.reasoning.generator = CodeGenerator(agent.llm, agent.reasoning.critic)

    steps = [("make a", "src/a.py"), ("make b", "src/b.py")]
    loop = AutonomousLoop(agent, LoopLimits(max_runs=6, completion_threshold=2))
    workflow = sequential_codegen_workflow(
        agent, steps, verify_command="python -c \"print('1 passed')\"")
    report = loop.run("build a then b", workflow)
    assert report.completed
    assert agent.fs.exists("src/a.py")
    assert agent.fs.exists("src/b.py")
