# GOD Coding Agent

> A safety-first, self-verifying agentic coding system. The high-value parts run
> fully offline (no API key) — workspace boundaries, self-verification,
> reversible changes, dependency vetting — and the agent learns from its own
> history to improve future work.

[**→ Free Variant Quickstart**](QUICKSTART_FREE_VARIANT.md) · [**→ Documentation**](docs/README.md)

### What's new

- **Skill memory** — the agent now learns *positive* patterns, not just
  mistakes. Successful tasks (accepted **and** verified) are distilled into
  reusable "proven approaches" that are injected back into generation prompts
  and shown by `god memory`. It is deterministic, offline, and adds no
  dependencies. See [`docs/skills.md`](docs/skills.md).
- **Model routing** — reach any OpenAI-compatible, Anthropic, Gemini, or local
  (Ollama/LM Studio/vLLM) model over the standard library, with optional
  cost-aware selection and a token budget cap.

---

A working implementation
of the architecture in [`god_coding_agent_blueprint.md`](../god_coding_agent_blueprint.md),
deliberately engineered to avoid the failure modes catalogued in
[`claude-code-hard-realities.md`](../claude-code-hard-realities.md).

The guiding idea: **the most valuable parts of a coding agent are the
deterministic ones** — workspace boundaries, self-verification, reversible
changes, dependency vetting. Those need no model, run fully offline, and can't
be "forgotten" by a prompt. The LLM is a pluggable layer on top.

## Documentation

Full guides live in [`docs/`](docs/README.md):

- [Installation](docs/installation.md) · [Getting started](docs/getting-started.md)
- [CLI reference](docs/cli-reference.md) · [Configuration](docs/configuration.md)
- [LLM providers](docs/providers.md) (any model — OpenAI, Groq, Gemini, OpenRouter, Anthropic, Ollama, local, custom)
- [Workflows](docs/workflows.md) · [Architecture](docs/architecture.md)
- [Security model](docs/security.md) · [Contributing](docs/contributing.md) · [Troubleshooting & FAQ](docs/troubleshooting.md)

## Why it's built this way

Each module maps to a documented, real-world agent failure and its mitigation:

| Real failure (from the realities doc)        | What this project does about it                                   |
|----------------------------------------------|-------------------------------------------------------------------|
| Agents inherit full filesystem permissions   | `WorkspaceBoundary` — every path is resolved & checked in code    |
| Confident but false "it's done" claims       | `Verifier` — actually runs tests, parses output, detects fake-green |
| Memory/instructions followed inconsistently  | Critical rules enforced in code (boundaries, blocked commands), not prose |
| Autonomy causing unintended changes          | `SafetySystem` checkpoints + one-call rollback before every mutation |
| Hallucinated / "slopsquatted" dependencies   | `DependencyChecker` — registry verification + typosquat proximity |
| No semantic code understanding (no LSP)       | `CodeGraph` — AST-based symbols, callers, impact, complexity hotspots |
| Elevated vulnerability rate in AI code        | `SelfCritic` — deterministic secrets + vuln scan, runs before code lands |
| Repeating the same mistakes / no learning     | `MemorySystem` — learns conventions + recurring failures, feeds them back into prompts |
| Reactive only (never anticipates)             | `ProactiveEngine` — unprompted health analysis + bounded watch mode |
| Model lock-in / no routing flexibility        | `ModelRouter` + universal providers — any OpenAI-compatible / Anthropic / Gemini / local model |
| Unpredictable cost on long runs              | `LLMOrchestrator` usage accounting + optional token budget cap    |
| Destructive commands                          | Hard-blocked patterns (`rm -rf /`, force-push, `mkfs`, fork bombs) |

## Install

No third-party dependencies are required for the core (Python 3.11+).

```bash
pip install -e .            # editable install, exposes the `god` command
pip install -e ".[dev]"     # + pytest + pytest-cov
```

No provider SDKs are needed — every LLM (OpenAI, Groq, Gemini, OpenRouter,
Anthropic, DeepSeek, Mistral, local Ollama/LM Studio/vLLM, or any custom
OpenAI-compatible endpoint) is reached over the standard library. Run
`god providers` to see them all.

Then adopt it in any project in one step:

```bash
god init                    # scaffold god_agent.toml + detect conventions
god init --precommit        # also emit a pre-commit critique gate
```

Or run straight from source without installing:

```bash
# from this directory
PYTHONPATH=src python -m god_agent.cli status
```

## CLI

```
god status                     # project perception: stacks, code-graph stats, git
god tree --depth 3             # project tree
god search "checkpoint logic"  # relevance search across the project
god graph --top 8              # code-graph stats + complexity hotspots
god verify                     # run + parse the test command, report an HONEST verdict
god verify --command "pytest"  # explicit verification command
god depcheck requests reqeusts # vet dependency names (registry + typosquat)
god depcheck react axios --ecosystem npm
god plan "add OAuth login to the API"   # classify request -> structured plan
god critique src/app/handler.py         # secrets/vuln/stub scan (exit!=0 if blocking)
god generate "add a rate limiter" src/app/limiter.py --provider groq
god loop "keep the project green and clean" --command "pytest" --max-runs 5
god learn                      # detect + store this project's coding conventions
god memory                     # show episodes, learned conventions, and lessons
god health                     # proactive health analysis: prioritized suggestions
god watch --max-polls 120      # bounded watch mode: re-analyse files as they change
god route "refactor the auth module"   # show which model tier a task routes to
god sandbox "py -m pytest"     # run a command in an isolated copy of the project
god serve                      # local read-only dashboard + JSON API (no auth)
god onboard                    # generate a project onboarding guide
god who src/app/handler.py     # contributors/owners of a file (git history)
god team export team.json      # share learned conventions + lessons with a team
god audit -n 20                # tail the append-only audit log
god providers                  # list LLM providers (free/paid/local) + status
god chat                       # interactive REPL: converse, edit-with-diff-approval, verify
god ask "explain this module"  # send a prompt to the configured LLM provider
```

`god verify` exits non-zero when verification fails, and `god critique` exits
non-zero on blocking findings, so both slot into CI as hard gates rather than
courtesies.

### Suppressing an intentional finding

The critic supports auditable inline suppression for deliberate, mitigated
patterns:

```python
subprocess.run(cmd, shell=True)  # god:allow shell-injection
```

A bare `# god:allow` suppresses non-secret findings on that line; secret
findings require the rule to be named explicitly (e.g.
`# god:allow secret:aws-access-key`) so a stray blanket comment can never hide a
credential.

## Programmatic use

```python
from god_agent import Config
from god_agent.agent import GodAgent

agent = GodAgent(Config.load("."))
agent.perceive()                       # build project understanding

# The guarded write pipeline — critique -> checkpoint -> write -> verify -> rollback:
outcome = agent.reasoning.safe_apply(
    description="add greeting",
    path="src/app/hello.py",
    content="def hi():\n    return 'hi'\n",
    verify_command="pytest",
)
print(outcome.report())
# Bad code (secrets, vulns, syntax errors) is rejected BEFORE it touches disk;
# code that fails verification is written, tested, and automatically rolled back.

# Lower-level building blocks are also available directly:
rec = agent.apply_change(
    "manual edit",
    ["src/app/x.py"],
    lambda: agent.fs.write_file("src/app/x.py", "X = 1\n"),
)
if not agent.verify("pytest").passed:
    agent.rollback_last()
```

## Architecture (implemented modules)

```
god_agent/
├── workspace.py        # WorkspaceBoundary — deterministic path confinement
├── safety.py           # risk assessment, audit log, checkpoints, rollback
├── config.py           # layered config (defaults < god_agent.toml < overrides)
├── verify.py           # self-verification: run tests, parse, detect fake-green
├── depcheck.py         # dependency hallucination / typosquat guard
├── agent.py            # GodAgent façade: perceive -> act-with-checkpoint -> VERIFY
├── cli.py              # `god` command
├── reasoning/
│   ├── critic.py       # SelfCritic — deterministic secrets/vuln/stub review + inline suppression
│   ├── planner.py      # scope classification + structured, verify-anchored plans
│   ├── generator.py    # multi-pass LLM code generation (critique-driven fix loop)
│   └── engine.py       # ReasoningEngine: safe_apply + generate_and_apply
├── loop.py             # AutonomousLoop: exit conditions, shared notes, circuit breaker
├── proactive.py        # ProactiveEngine: health analysis + bounded watch mode
├── sandbox.py          # SandboxManager: isolated execution + promote-if-good
├── web.py              # zero-dependency read-only dashboard + JSON API
├── ui/                 # interactive REPL (god chat) + colored diff rendering
├── team.py             # knowledge bundles, onboarding docs, code ownership
├── memory/
│   ├── episodic.py     # durable JSONL log of actions + outcomes, similarity recall
│   ├── lessons.py      # error-pattern recognition -> actionable lessons
│   ├── conventions.py  # deterministic house-style detection (ast/tokenize)
│   └── system.py       # MemorySystem façade: guidance_for() closes the loop
├── tools/
│   ├── filesystem.py   # read/write/edit/delete with backups + boundary checks
│   ├── shell.py        # bounded, screened, time-boxed command execution
│   └── git_tool.py     # status/diff + deterministic conventional-commit messages
├── context/
│   ├── code_graph.py   # AST symbol/import graph, callers, impact, hotspots
│   └── engine.py       # stack detection + token-overlap relevance search
└── llm/
    ├── base.py         # provider-agnostic interfaces
    ├── transport.py    # dependency-free HTTP (urllib) + retry
    ├── mock.py         # deterministic offline provider (default)
    ├── scripted.py     # scripted provider for tests/demos
    ├── openai_compat.py # universal OpenAI-compatible adapter (most services + local)
    ├── anthropic_provider.py  # native Anthropic (urllib, no SDK)
    ├── gemini_provider.py     # native Google Gemini (urllib, no SDK)
    ├── registry.py     # provider presets (openai, groq, gemini, ollama, …)
    ├── router.py       # task-aware fast/powerful model routing
    └── orchestrator.py # provider selection + usage/budget accounting
```

## Roadmap status (vs. blueprint phases)

- **Phase 1 — Foundation:** done (CLI, filesystem/shell/git tools, boundaries,
  backups, config).
- **Phase 2 — Intelligence:** done (AST code graph, relevance search,
  self-verification, dependency vetting, planner + decomposer, deterministic
  self-critique loop, multi-pass code generation, and the `safe_apply` /
  `generate_and_apply` pipelines).
- **Phase 4 (partial) — Autonomous operation:** `AutonomousLoop` with exit
  conditions (max-runs / token-budget / wall-clock / completion-signal),
  cross-iteration shared notes, a consecutive-failure circuit breaker, and two
  built-in workflows (offline quality sweep, LLM sequential codegen).
- **Phase 3 — Memory & Learning:** done (episodic memory, error-pattern
  recognition / lessons, deterministic convention detection, and the
  `guidance_for` loop-closer that injects learned conventions + lessons back
  into generation prompts — the agent gets better with use).
- **Phase 4 — Proactive & Advanced:** done (proactive project-health analysis
  with prioritized suggestions, a bounded poll-based watch mode, task-aware
  multi-model routing, and sandboxed execution — run risky ops in an isolated
  copy and promote only verified changes).
- **Phase 5 — Polish & Scale:** done (a zero-dependency local web dashboard +
  JSON API, a VS Code extension scaffold under `ide/vscode/`, and team features:
  shareable knowledge bundles, git-based code-ownership lookup, and onboarding
  doc generation).
- **LLM providers:** works with **any** model — a single OpenAI-compatible
  adapter covers OpenAI, Groq, OpenRouter, Mistral, DeepSeek, Together, xAI,
  Perplexity, and every local runner (Ollama, LM Studio, vLLM, llama.cpp), plus
  native Anthropic and Gemini adapters — all dependency-free (stdlib HTTP). Keys
  resolved per-provider; graceful fallback to the offline mock when unset.

## Tests

```bash
PYTHONPATH=src python -m pytest        # runs offline (live provider tests skipped without keys)
pytest --cov=god_agent --cov-report=term-missing   # coverage report
```

## CI & dogfooding

`.github/workflows/ci.yml` runs the suite across Python 3.11–3.13 **and** runs
the agent's own gates as hard CI checks: a deterministic `god critique` sweep
over every source file and a `god health` gate. `.pre-commit-config.yaml` wires
the same critique + tests into a local pre-commit hook. The project passes its
own gates — `god loop` self-check completes with 0 blocking files.
