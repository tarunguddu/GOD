"""Interactive REPL — a conversational, diff-and-approve coding session.

Design goals:
  - Stdlib only; works with any configured provider (offline mock included).
  - Every file change is previewed as a colored diff and applied only on
    approval, then critiqued + verified + auto-rolled-back through the guarded
    pipeline (supervised by default).
  - GOD-tier touches: a proactive opening nudge (top health issue, unprompted),
    session change tracking, and one-step /undo.

Testability: the loop reads via an injectable ``reader`` callable (raises
EOFError to stop) and writes via an injectable ``writer`` callable, so a test
can drive a full session deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .diffview import diff_stat, render_unified_diff

_BANNER = "GOD agent - interactive session. Type /help for commands, /quit to exit."

_HELP = """commands:
  /help                 show this help
  <plain text>          ask the model (conversational)
  /edit <path> <task>   generate a change, preview the diff, approve to apply
  /critique <path>      deterministic secrets/vuln/stub review
  /plan <request>       classify + show a structured plan
  /health               proactive project-health suggestions
  /verify [command]     run tests and report an honest verdict
  /memory               learned conventions + lessons
  /changes              changes applied this session
  /undo                 roll back the last applied change
  /provider             show the active LLM provider + model
  /quit                 end the session"""


@dataclass
class Repl:
    agent: object
    reader: Callable[[], str] | None = None
    writer: Callable[[str], None] | None = None
    color: bool = True
    verify_command: str | None = None
    session_changes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.reader is None:
            self.reader = lambda: input("god> ")
        if self.writer is None:
            self.writer = print

    # ---- loop --------------------------------------------------------------
    def run(self) -> None:
        self._opening()
        while True:
            try:
                line = self.reader().strip()
            except EOFError:
                break
            if not line:
                continue
            if line in ("/quit", "/exit", "quit", "exit"):
                break
            try:
                self._dispatch(line)
            except Exception as exc:  # a command error must not kill the session
                self._w(f"error: {type(exc).__name__}: {exc}")
        self._w("session ended.")

    def _w(self, text: str = "") -> None:
        self.writer(text)

    # ---- opening (proactive nudge) ----------------------------------------
    def _opening(self) -> None:
        self._w(_BANNER)
        provider = getattr(self.agent.llm.provider, "name", "?")
        self._w(f"provider: {provider}")
        try:
            report = self.agent.proactive.analyze()
            top = report.by_severity()
            self._w(f"project health: {report.score}/100")
            if top:
                s = top[0]
                self._w(f"heads-up: [{s.severity.name}] {s.category} - "
                        f"{s.message}" + (f" ({s.location})" if s.location else ""))
        except Exception:
            pass

    # ---- dispatch ----------------------------------------------------------
    def _dispatch(self, line: str) -> None:
        if not line.startswith("/"):
            self._cmd_ask(line)
            return
        parts = line.split(maxsplit=1)
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""
        handler = {
            "/help": lambda a: self._w(_HELP),
            "/edit": self._cmd_edit,
            "/critique": self._cmd_critique,
            "/plan": self._cmd_plan,
            "/health": lambda a: self._cmd_health(),
            "/verify": self._cmd_verify,
            "/memory": lambda a: self._cmd_memory(),
            "/changes": lambda a: self._cmd_changes(),
            "/undo": lambda a: self._cmd_undo(),
            "/provider": lambda a: self._cmd_provider(),
        }.get(cmd)
        if handler is None:
            self._w(f"unknown command: {cmd} (try /help)")
            return
        handler(arg)

    # ---- commands ----------------------------------------------------------
    def _cmd_ask(self, prompt: str) -> None:
        resp = self.agent.llm.complete(prompt)
        self._w(resp.text)

    def _cmd_plan(self, request: str) -> None:
        if not request:
            self._w("usage: /plan <request>")
            return
        self._w(self.agent.reasoning.plan(request).render())

    def _cmd_critique(self, path: str) -> None:
        if not path:
            self._w("usage: /critique <path>")
            return
        if not self.agent.fs.exists(path):
            self._w(f"file not found: {path}")
            return
        critique = self.agent.reasoning.critic.review_file(
            self.agent.boundary.check(path))
        self._w(f"{path}: {critique.summary()}")
        for f in critique.by_severity():
            loc = f":{f.line}" if f.line else ""
            self._w(f"  [{f.severity.name}] {f.rule}{loc}: {f.message}")

    def _cmd_health(self) -> None:
        report = self.agent.proactive.analyze()
        self._w(report.render(top=8))

    def _cmd_verify(self, command: str) -> None:
        cmd = command or self.verify_command
        try:
            result = self.agent.verify(cmd or None)
        except ValueError as exc:
            self._w(f"error: {exc}")
            return
        self._w(result.as_claim())

    def _cmd_memory(self) -> None:
        stats = self.agent.memory.stats()
        self._w(f"episodes: {stats['episodes']} "
                f"(accepted={stats['accepted']}, rejected={stats['rejected']})")
        conv = self.agent.memory.conventions()
        if conv is not None:
            self._w(conv.render())
        for lesson in self.agent.memory.top_lessons(n=5):
            self._w(f"  {lesson.render()}")

    def _cmd_changes(self) -> None:
        if not self.session_changes:
            self._w("no changes applied this session.")
            return
        for i, path in enumerate(self.session_changes, 1):
            self._w(f"  {i}. {path}")

    def _cmd_undo(self) -> None:
        restored = self.agent.rollback_last()
        if restored is None:
            self._w("nothing to undo.")
            return
        if self.session_changes:
            self.session_changes.pop()
        self._w(f"rolled back: {restored}")

    def _cmd_provider(self) -> None:
        p = self.agent.llm.provider
        self._w(f"provider: {p.name}  model: {getattr(p, 'model', '?')}  "
                f"usage: {vars(self.agent.llm.usage)}")

    # ---- the supervised edit flow -----------------------------------------
    def _cmd_edit(self, arg: str) -> None:
        bits = arg.split(maxsplit=1)
        if len(bits) < 2:
            self._w("usage: /edit <path> <instruction>")
            return
        path, instruction = bits[0], bits[1]

        # 1. Generate (routed model + learned guidance via the reasoning engine).
        try:
            guidance = self.agent.memory.guidance_for(instruction)
        except Exception:
            guidance = ""
        context = self.agent.reasoning._gather_context(instruction)
        if guidance:
            context = guidance + ("\n\n" + context if context else "")
        try:
            route = self.agent.router.select(instruction)
            model = route.model
        except Exception:
            model = None
        result = self.agent.reasoning.generator.generate(
            instruction, path, context=context, model=model)
        if not result.code:
            self._w(f"no usable code produced (provider={result.provider}). "
                    f"Configure a real provider, or this request needs more detail.")
            return

        # 2. Critique the proposal up front.
        critique = self.agent.reasoning.critic.review(result.code, filename=path)
        if critique.blocking:
            self._w(f"proposed code was rejected by self-critique "
                    f"({critique.summary()}) — not applying:")
            for f in critique.by_severity():
                if f.severity >= 3:
                    self._w(f"  [{f.severity.name}] {f.rule}: {f.message}")
            return

        # 3. Preview the diff.
        old = self.agent.fs.read_file(path) if self.agent.fs.exists(path) else ""
        added, removed = diff_stat(old, result.code)
        self._w(f"proposed change to {path}  (+{added} / -{removed}, "
                f"{result.passes} pass(es) via {result.provider}):")
        self._w(render_unified_diff(old, result.code, path, color=self.color))

        # 4. Approve.
        self._w("apply this change? [y/N]")
        try:
            answer = self.reader().strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("y", "yes"):
            self._w("skipped.")
            return

        # 5. Apply through the guarded pipeline (checkpoint -> write -> verify).
        outcome = self.agent.reasoning.safe_apply(
            description=instruction, path=path, content=result.code,
            verify_command=self.verify_command)
        if outcome.accepted:
            self.session_changes.append(path)
        self._w(outcome.report())


def run_repl(agent, color: bool = True, verify_command: str | None = None) -> None:
    Repl(agent=agent, color=color, verify_command=verify_command).run()
