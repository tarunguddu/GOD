"""Command-line interface for the GOD agent.

Subcommands:
  status      Show project perception summary (stacks, graph stats, git).
  tree        Print the project tree.
  search      Token-overlap relevance search across the project.
  graph       Show code-graph stats / complexity hotspots.
  verify      Run and parse the project's test command, report an honest verdict.
  depcheck    Vet one or more dependency names for hallucination / typosquatting.
  audit       Show the tail of the audit log.
  ask         Send a prompt to the configured LLM provider.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .agent import GodAgent
from .config import Config


def _build_agent(args: argparse.Namespace) -> GodAgent:
    overrides: dict[str, object] = {}
    if getattr(args, "provider", None):
        overrides["llm_provider"] = args.provider
    config = Config.load(args.root, **overrides)
    return GodAgent(config)


def cmd_status(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    summary = agent.status_summary()
    print(f"GOD agent v{__version__}")
    print(f"root:    {summary['root']}")
    print(f"stacks:  {', '.join(summary['stacks']) or 'unknown'}")
    print(f"files:   {summary['files']}")
    print(f"graph:   {summary['graph']}")
    print(f"git:     {summary['git_branch'] or 'not a repo'}")
    print(f"llm:     {summary['llm_provider']}")
    return 0


def cmd_tree(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    print(agent.fs.tree(".", depth=args.depth))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    agent.perceive()
    hits = agent.context.search(args.query, top_k=args.top)
    if not hits:
        print("No matches.")
        return 0
    for hit in hits:
        print(f"{hit.score:>7.3f}  {hit.path}")
        if hit.preview:
            print(f"         {hit.preview}")
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    agent.perceive()
    print("stats:", agent.context.graph.stats())
    print("\ncomplexity hotspots:")
    for node in agent.context.graph.hotspots(top=args.top):
        print(f"  {node.complexity:>3}  {node.file}::{node.qualified_name}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    try:
        result = agent.verify(args.command)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(result.as_claim())
    for note in result.notes:
        print(f"  {note}")
    if not result.passed and result.raw_tail:
        print("\n--- output tail ---")
        print(result.raw_tail)
    return 0 if result.passed else 1


def cmd_depcheck(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    agent.depcheck.online = not args.offline
    verdicts = agent.vet_dependencies(args.names, ecosystem=args.ecosystem)
    exit_code = 0
    for v in verdicts:
        marker = {"ok": "OK ", "review": "?? ", "danger": "!! ",
                  "unverified": "?? "}[v.risk]
        print(f"{marker} {v.name} [{v.risk}] - {v.detail}")
        if v.risk in ("danger",):
            exit_code = 1
    return exit_code


def cmd_plan(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    plan = agent.reasoning.plan(args.request)
    print(plan.render())
    return 0


def cmd_critique(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    if not agent.fs.exists(args.path):
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return 2
    critique = agent.reasoning.critic.review_file(
        Path(agent.boundary.check(args.path))
    )
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps({
            "path": args.path,
            "summary": critique.summary(),
            "blocking": critique.blocking,
            "findings": [
                {"severity": f.severity.name, "rule": f.rule,
                 "line": f.line, "message": f.message}
                for f in critique.by_severity()
            ],
        }))
        return 1 if critique.blocking else 0
    print(f"{args.path}: {critique.summary()}")
    for f in critique.by_severity():
        loc = f":{f.line}" if f.line else ""
        print(f"  [{f.severity.name}] {f.rule}{loc}: {f.message}")
        if f.snippet:
            print(f"      {f.snippet}")
    return 1 if critique.blocking else 0


def cmd_loop(args: argparse.Namespace) -> int:
    from .loop import AutonomousLoop, LoopLimits, quality_sweep_workflow
    agent = _build_agent(args)
    limits = LoopLimits(
        max_runs=args.max_runs,
        max_seconds=args.max_seconds,
        completion_threshold=args.completion_threshold,
    )
    loop = AutonomousLoop(agent, limits=limits)
    workflow = quality_sweep_workflow(agent, verify_command=args.command)
    report = loop.run(args.task, workflow)
    print(report.render())
    print(f"\nshared notes: {loop.notes_path}")
    return 0 if report.completed else 1


def cmd_memory(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    stats = agent.memory.stats()
    print(f"episodes: {stats['episodes']} "
          f"(accepted={stats['accepted']}, rejected={stats['rejected']}, "
          f"verified={stats['verified']})")
    conv = agent.memory.conventions()
    if conv is None:
        print("\nconventions: not learned yet - run 'god learn'")
    else:
        print(f"\nconventions (from {conv.sample_size} files):")
        print(conv.render())
    skills = agent.memory.top_skills(n=args.top)
    if skills:
        print("\nskills (proven approaches to reuse):")
        for skill in skills:
            print(f"  {skill.render()}")
    else:
        print("\nskills: none yet (no verified successes)")
    lessons = agent.memory.top_lessons(n=args.top)
    if lessons:
        print("\nlessons learned:")
        for lesson in lessons:
            print(f"  {lesson.render()}")
    else:
        print("\nlessons: none yet (no recorded outcomes)")
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    conv = agent.memory.learn_conventions(force=True)
    print(f"learned conventions from {conv.sample_size} files:")
    print(conv.render())
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    report = agent.proactive.analyze()
    print(report.render(top=args.top))
    # exit non-zero if any security suggestion is HIGH+ so it works as a gate
    from .reasoning.critic import Severity
    serious = any(s.severity >= Severity.HIGH and s.category == "security"
                  for s in report.suggestions)
    return 1 if serious else 0


def cmd_watch(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    print(f"watching {agent.boundary.root} "
          f"(poll={args.poll}s, max_polls={args.max_polls}) - Ctrl-C to stop")

    def on_event(event):
        print(f"\nchange detected in {len(event.changed)} file(s): "
              f"{', '.join(event.changed)}")
        print(event.report.render(top=5))

    events = agent.proactive.watch(
        on_event=on_event, poll_interval=args.poll, max_polls=args.max_polls,
        max_seconds=args.max_seconds,
    )
    print(f"\nwatch ended after detecting {len(events)} change event(s).")
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    decision = agent.router.select(args.task)
    print(f"tier={decision.tier} model={decision.model}\nreason: {decision.reason}")
    return 0


def cmd_sandbox(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    sandbox = agent.sandbox.create(label=args.command)
    try:
        proc = agent.sandbox.run_command(sandbox, args.command)
        print(f"command exit code: {proc.returncode}")
        if proc.stdout.strip():
            print("--- stdout (tail) ---")
            print("\n".join(proc.stdout.splitlines()[-15:]))
        diff = agent.sandbox.diff(sandbox)
        if diff.empty:
            print("\nno file changes in the sandbox.")
        else:
            print(f"\nchanged in sandbox: {diff.changed}")
            if args.promote:
                if proc.returncode != 0:
                    print("refusing to promote: command exited non-zero.")
                    return 1
                promoted = agent.sandbox.promote(sandbox, approved=args.approve)
                print(f"promoted to workspace: {promoted}")
            else:
                print("(run again with --promote to apply these changes)")
        return 0 if proc.returncode == 0 else 1
    finally:
        agent.sandbox.destroy(sandbox)


def cmd_serve(args: argparse.Namespace) -> int:
    from .web import serve
    agent = _build_agent(args)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("SECURITY: the API has NO authentication. Binding to a non-local "
              "host exposes read access to your project. Proceed only behind an "
              "authenticating proxy.", file=sys.stderr)
    serve(agent, host=args.host, port=args.port)
    return 0


def cmd_team(args: argparse.Namespace) -> int:
    from . import team
    agent = _build_agent(args)
    if args.team_action == "export":
        rel = team.export_bundle(agent, args.path)
        print(f"exported knowledge bundle to {rel}")
    else:
        if not agent.fs.exists(args.path):
            print(f"error: bundle not found: {args.path}", file=sys.stderr)
            return 2
        n = team.import_bundle(agent, args.path)
        print(f"imported {n} episode(s) from {args.path}")
    return 0


def cmd_onboard(args: argparse.Namespace) -> int:
    from . import team
    agent = _build_agent(args)
    doc = team.generate_onboarding(agent)
    if args.output:
        agent.fs.write_file(args.output, doc)
        print(f"wrote onboarding guide to {args.output}")
    else:
        print(doc)
    return 0


def cmd_who(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    if not agent.git.is_repo():
        print("not a git repository.", file=sys.stderr)
        return 2
    owners = agent.git.find_who_knows(args.path)
    if not owners:
        print(f"no git history found for {args.path}")
        return 0
    print(f"contributors to {args.path}:")
    for author, count in owners:
        print(f"  {count:>4}  {author}")
    return 0


_DEFAULT_TOML = """# GOD agent project configuration.
[god-agent]
confirm_destructive = true
max_files_per_action = 25

llm_provider = "mock"          # "mock" (offline) or "anthropic"
llm_model = "claude-sonnet-4"
llm_fast_model = "claude-haiku"
llm_powerful_model = "claude-sonnet-4"
llm_api_key_env = "ANTHROPIC_API_KEY"

# test_command = "pytest"      # auto-detected from project markers if unset
# build_command = "python -m build"
"""

_PRECOMMIT_HOOK = """#!/bin/sh
# GOD agent pre-commit gate: block commits that fail the deterministic critique.
# Install: copy to .git/hooks/pre-commit and chmod +x.
set -e
files=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\\.py$' || true)
[ -z "$files" ] && exit 0
status=0
for f in $files; do
  god critique "$f" >/dev/null 2>&1 || { echo "GOD critique blocked: $f"; god critique "$f"; status=1; }
done
exit $status
"""


def cmd_init(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    created = []
    toml_path = agent.boundary.root / "god_agent.toml"
    if toml_path.exists() and not args.force:
        print("god_agent.toml already exists (use --force to overwrite)")
    else:
        agent.fs.write_file("god_agent.toml", _DEFAULT_TOML)
        created.append("god_agent.toml")
    if args.precommit:
        agent.fs.write_file(".god/hooks/pre-commit", _PRECOMMIT_HOOK)
        created.append(".god/hooks/pre-commit")
        print("pre-commit hook written to .god/hooks/pre-commit - install with:\n"
              "  cp .god/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit")
    # Seed conventions so guidance/onboarding work immediately.
    conv = agent.memory.learn_conventions(force=True)
    print(f"initialized GOD agent. created: {created or 'nothing new'}")
    print(f"detected conventions: {conv.function_naming}, {conv.indent}, "
          f"{conv.quote_style} quotes")
    return 0


def cmd_providers(args: argparse.Namespace) -> int:
    import os
    from .llm.registry import list_presets
    print(f"{'preset':<12} {'kind':<14} {'key env':<20} {'status':<14} model")
    print("-" * 88)
    for name, p in list_presets().items():
        if p.api_key_env is None:
            status = "local/no-key" if p.kind != "mock" else "always"
        elif os.environ.get(p.api_key_env):
            status = "configured"
        else:
            status = "needs key"
        free = " (free)" if p.free else ""
        print(f"{name:<12} {p.kind:<14} {str(p.api_key_env or '-'):<20} "
              f"{status:<14} {p.default_model}{free}")
    print("\nUse:  god --provider <preset> ask \"...\"   "
          "(set the key env var first, or run a local server)")
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    provider = agent.llm.provider
    base_url = getattr(provider, "base_url", None)
    if not base_url:
        print(f"listing models is not supported for provider '{provider.name}'.",
              file=sys.stderr)
        return 2
    from .llm.transport import get_json, LLMHTTPError
    headers = {}
    key = getattr(provider, "api_key", None)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        data = get_json(f"{base_url}/models", headers)
    except LLMHTTPError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    models = data.get("data", data.get("models", []))
    for m in models:
        mid = m.get("id") or m.get("name") if isinstance(m, dict) else m
        print(mid)
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    from .ui.repl import run_repl
    agent = _build_agent(args)
    run_repl(agent, color=not args.no_color, verify_command=args.command)
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    for entry in agent.safety.audit.tail(args.n):
        print(entry)
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    if agent.llm.provider.name == "mock" and not args.allow_mock:
        print("error: the 'mock' provider cannot generate real code. Re-run with "
              "--provider anthropic (and an API key), or pass --allow-mock to "
              "exercise the pipeline.", file=sys.stderr)
        return 2
    outcome = agent.reasoning.generate_and_apply(
        instruction=args.instruction,
        path=args.path,
        verify_command=args.command,
        max_passes=args.passes,
    )
    print(outcome.report())
    return 0 if outcome.accepted else 1


def cmd_ask(args: argparse.Namespace) -> int:
    agent = _build_agent(args)
    response = agent.llm.complete(args.prompt)
    print(response.text)
    print(f"\n[provider={response.provider} model={response.model} "
          f"usage={response.usage}]", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="god", description="GOD Coding Agent")
    parser.add_argument("--version", action="version", version=f"god-agent {__version__}")
    parser.add_argument("--root", default=".", help="project root (default: cwd)")
    parser.add_argument("--provider",
                        help="override LLM provider (any preset: openai, groq, "
                             "gemini, anthropic, ollama, openrouter, ... or 'mock')")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="project perception summary")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("tree", help="print project tree")
    p.add_argument("--depth", type=int, default=3)
    p.set_defaults(func=cmd_tree)

    p = sub.add_parser("search", help="relevance search")
    p.add_argument("query")
    p.add_argument("--top", type=int, default=8)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("graph", help="code graph stats + hotspots")
    p.add_argument("--top", type=int, default=8)
    p.set_defaults(func=cmd_graph)

    p = sub.add_parser("verify", help="run + parse the test command honestly")
    p.add_argument("--command", help="explicit verification command")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("depcheck", help="vet dependency names")
    p.add_argument("names", nargs="+")
    p.add_argument("--ecosystem", choices=["pypi", "npm"], default="pypi")
    p.add_argument("--offline", action="store_true", help="skip registry lookups")
    p.set_defaults(func=cmd_depcheck)

    p = sub.add_parser("audit", help="show audit log tail")
    p.add_argument("-n", type=int, default=20)
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("memory", help="show learned memory: episodes, conventions, lessons")
    p.add_argument("--top", type=int, default=8)
    p.set_defaults(func=cmd_memory)

    p = sub.add_parser("learn", help="detect and store the project's coding conventions")
    p.set_defaults(func=cmd_learn)

    p = sub.add_parser("health", help="proactive project-health analysis + suggestions")
    p.add_argument("--top", type=int, default=15)
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("watch", help="bounded watch mode: re-analyse changed files")
    p.add_argument("--poll", type=float, default=1.0, help="poll interval seconds")
    p.add_argument("--max-polls", type=int, default=60, dest="max_polls")
    p.add_argument("--max-seconds", type=float, default=None, dest="max_seconds")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("route", help="show which model tier a task would route to")
    p.add_argument("task")
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("sandbox", help="run a command in an isolated copy; optionally promote changes")
    p.add_argument("command")
    p.add_argument("--promote", action="store_true", help="apply sandbox changes to the workspace")
    p.add_argument("--approve", action="store_true", help="allow promoting deletions")
    p.set_defaults(func=cmd_sandbox)

    p = sub.add_parser("serve", help="run the local read-only dashboard + JSON API (no auth)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("team", help="share learned knowledge across a team")
    p.add_argument("team_action", choices=["export", "import"])
    p.add_argument("path", help="bundle file path")
    p.set_defaults(func=cmd_team)

    p = sub.add_parser("onboard", help="generate a project onboarding guide")
    p.add_argument("--output", help="write to this path instead of stdout")
    p.set_defaults(func=cmd_onboard)

    p = sub.add_parser("who", help="show contributors/owners of a file (git history)")
    p.add_argument("path")
    p.set_defaults(func=cmd_who)

    p = sub.add_parser("init", help="scaffold god_agent.toml (and optional pre-commit gate)")
    p.add_argument("--force", action="store_true", help="overwrite existing config")
    p.add_argument("--precommit", action="store_true", help="also write a pre-commit hook")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("loop", help="run an autonomous quality-sweep loop (offline)")
    p.add_argument("task", help="description of the loop's goal")
    p.add_argument("--command", help="explicit verification command")
    p.add_argument("--max-runs", type=int, default=5, dest="max_runs")
    p.add_argument("--max-seconds", type=float, default=None, dest="max_seconds")
    p.add_argument("--completion-threshold", type=int, default=2,
                   dest="completion_threshold")
    p.set_defaults(func=cmd_loop)

    p = sub.add_parser("plan", help="classify a request and produce a structured plan")
    p.add_argument("request")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("critique", help="deterministic code review (secrets/vulns/stubs)")
    p.add_argument("path")
    p.add_argument("--json", action="store_true", help="emit structured JSON output")
    p.set_defaults(func=cmd_critique)

    p = sub.add_parser("generate", help="generate code and run it through the guarded pipeline")
    p.add_argument("instruction")
    p.add_argument("path")
    p.add_argument("--command", help="explicit verification command")
    p.add_argument("--passes", type=int, default=2, help="max generation/fix passes")
    p.add_argument("--allow-mock", action="store_true",
                   help="exercise the pipeline with the offline mock provider")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("ask", help="send a prompt to the LLM provider")
    p.add_argument("prompt")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("providers", help="list LLM provider presets and their status")
    p.set_defaults(func=cmd_providers)

    p = sub.add_parser("models", help="list models offered by the active provider")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("chat", help="interactive REPL: converse, edit with diff-approval, verify")
    p.add_argument("--command", help="verification command used after edits")
    p.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    p.set_defaults(func=cmd_chat)

    return parser


def _ensure_utf8_output() -> None:
    """Render Unicode (em dashes, arrows, box characters) correctly on legacy
    Windows consoles whose default code page is not UTF-8.

    ``reconfigure`` exists on Python 3.7+ text streams; guard defensively so an
    exotic stdout (pipe, captured buffer) can never crash the CLI.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
