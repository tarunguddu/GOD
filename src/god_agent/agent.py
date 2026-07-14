"""The GOD agent — orchestration of perception, safety, tools, and verification.

This binds the modules together into one object with a deterministic spine:
  perceive -> (plan) -> act-with-checkpoint -> VERIFY -> report honestly.

The agent never reports success on a change without a parsed verification result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .context.engine import ContextEngine, ProjectContext
from .depcheck import DependencyChecker, DepVerdict
from .llm.orchestrator import LLMOrchestrator, get_provider
from .llm.router import ModelRouter
from .memory.system import MemorySystem
from .proactive import ProactiveEngine
from .reasoning.engine import ReasoningEngine
from .safety import Checkpoint, SafetySystem
from .sandbox import SandboxManager
from .tools.filesystem import FileSystemTool
from .tools.git_tool import GitTool
from .tools.shell import ShellTool
from .verify import Verifier, VerificationResult
from .workspace import WorkspaceBoundary


@dataclass
class ChangeRecord:
    description: str
    paths: list[str] = field(default_factory=list)
    checkpoint: Checkpoint | None = None
    verified: VerificationResult | None = None

    @property
    def checkpoint_id(self) -> str | None:
        return self.checkpoint.id if self.checkpoint else None


class GodAgent:
    """Top-level façade over every subsystem."""

    def __init__(self, config: Config, llm_budget_tokens: int | None = None) -> None:
        self.config = config
        self.boundary = WorkspaceBoundary(config.project_root)
        self.safety = SafetySystem(config, self.boundary)
        self.fs = FileSystemTool(self.boundary, self.safety)
        self.shell = ShellTool(self.boundary, self.safety)
        self.git = GitTool(self.boundary)
        self.context = ContextEngine(config.project_root)
        self.verifier = Verifier(self.shell)
        self.depcheck = DependencyChecker()
        self.llm = LLMOrchestrator(get_provider(config), budget_tokens=llm_budget_tokens)
        self.router = ModelRouter(config.llm_fast_model, config.llm_powerful_model)
        self.memory = MemorySystem(config.project_root)
        self.reasoning = ReasoningEngine(self)
        self.proactive = ProactiveEngine(self)
        self.sandbox = SandboxManager(self)
        self._project: ProjectContext | None = None
        self.changes: list[ChangeRecord] = []

    # ---- perception --------------------------------------------------------
    def perceive(self, refresh: bool = False) -> ProjectContext:
        if self._project is None or refresh:
            self._project = self.context.build()
        return self._project

    # ---- guarded mutation --------------------------------------------------
    def apply_change(self, description: str, paths: list[str], mutate) -> ChangeRecord:
        """Run ``mutate()`` with a safety checkpoint around it.

        ``mutate`` is a zero-arg callable that performs the actual file edits via
        ``self.fs``. A checkpoint is taken first so the change is reversible.
        """
        resolved = [str(self.boundary.check(p)) for p in paths]
        cp = self.safety.create_checkpoint(resolved, label=description)
        record = ChangeRecord(description=description, paths=paths, checkpoint=cp)
        try:
            mutate()
        except Exception:
            self.safety.rollback(cp)
            raise
        self.changes.append(record)
        return record

    def rollback_last(self) -> list[str] | None:
        if not self.changes:
            return None
        cp = self.changes[-1].checkpoint
        if cp is None:
            return None
        return self.safety.rollback(cp)

    # ---- verification ------------------------------------------------------
    def verify(self, command: str | None = None) -> VerificationResult:
        """Verify the project state. Auto-detects a test command if not given."""
        cmd = command or self.config.test_command
        if cmd is None:
            project = self.perceive()
            cmd = project.test_command
        if not cmd:
            raise ValueError(
                "No verification command available. Provide one explicitly or add "
                "a recognised project marker (pyproject.toml, package.json, ...)."
            )
        result = self.verifier.run(cmd)
        if self.changes:
            self.changes[-1].verified = result
        return result

    # ---- dependency safety -------------------------------------------------
    def vet_dependencies(self, names: list[str], ecosystem: str = "pypi") -> list[DepVerdict]:
        return self.depcheck.check_many(names, ecosystem)

    # ---- reporting ---------------------------------------------------------
    def status_summary(self) -> dict:
        project = self.perceive()
        return {
            "root": project.root,
            "stacks": project.stacks,
            "files": project.file_count,
            "graph": project.graph_stats,
            "git_branch": self.git.current_branch() if self.git.is_repo() else None,
            "changes_made": len(self.changes),
            "llm_provider": self.llm.provider.name,
            "llm_usage": vars(self.llm.usage),
        }
