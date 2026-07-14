# GOD Agent — Capabilities & Skill Memory Spec

**Version:** 2.0 (accuracy pass)
**Status:** Describes shipped behaviour + one new feature
**Scope:** This document describes what the GOD agent actually does today, documents the newly added **skill memory** feature, and lists clearly-labeled ideas for possible future work.

> Accuracy note: earlier drafts of this document described parallel multi-agent
> execution, a shared memory bus, invented model presets, and benchmark
> numbers. None of those were implemented. This version has been rewritten to
> match the code in `src/god_agent/`.

---

## Design principles (actual)

- **Zero third-party runtime dependencies.** The core runs on the Python 3.11+
  standard library only (`tomllib`, `json`, `pathlib`, `urllib`, …). Optional
  provider integrations import lazily and degrade to the offline mock provider
  when unavailable.
- **Offline-first.** The default provider is `mock` (deterministic, offline).
  Memory, conventions, lessons, and skills are computed deterministically from
  local JSONL — no network, no embeddings, no API key.
- **Guarded mutation.** All filesystem writes go through `FileSystemTool`
  (boundary-checked, backed up); all shell execution goes through `ShellTool`
  (screened, time-boxed). Generated code flows through `ReasoningEngine`'s
  guarded apply path so it is critiqued, checkpointed, verified, and remembered.

---

## Part 1 — Existing capabilities

### 1.1 LLM provider registry

Providers are selected by a **preset name** via `llm_provider = "<preset>"` in
`god_agent.toml`. Each preset maps to a provider kind, base URL, API-key env
var, and default model. See `src/god_agent/llm/registry.py`.

**Hosted, OpenAI-compatible:** `openai`, `groq`, `openrouter`, `deepseek`,
`mistral`, `together`, `fireworks`, `xai`, `perplexity`.

**Native schemas:** `anthropic` (default model `claude-sonnet-4`),
`gemini` (default model `gemini-1.5-flash`).

**Local (no API key, fully offline once the server is running):**
`ollama` (default model `llama3.2`), `lmstudio`, `vllm`, `llamacpp`.

**Offline default:** `mock` (deterministic stub, default model `mock-1`).

If a chosen provider is unavailable (missing key, server not running), the
orchestrator falls back to the mock provider rather than failing.

List presets and their live status with:

```bash
py -m god_agent.cli providers
py -m god_agent.cli models
```

### 1.2 Cost-aware model routing (already implemented)

`src/god_agent/llm/router.py` provides `ModelRouter`, which returns a
`RouteDecision(tier, model, reason)` for a task:

- Work classified as **exploration** or **test** scope routes to
  `llm_fast_model`.
- A fast-scope task whose instruction is long (>= 180 chars) is *escalated* to
  `llm_powerful_model`.
- All other scopes route to `llm_powerful_model`.

Routing is deterministic and unit-tested. It is wired into
`reasoning/engine.py`'s generate-and-apply path. Configure the two tiers:

```toml
[god-agent]
llm_fast_model = "claude-haiku"        # default
llm_powerful_model = "claude-sonnet-4" # default
```

Inspect a routing decision from the CLI:

```bash
py -m god_agent.cli route "add tests for the config loader"
```

### 1.3 Usage accounting and token budget (already implemented)

`LLMOrchestrator` (`src/god_agent/llm/orchestrator.py`) tracks cumulative usage
(`requests`, `input_tokens`, `output_tokens`, char counts) and enforces an
optional `budget_tokens`. When the budget is exhausted, further completions
raise rather than silently spending more.

### 1.4 Memory system (already implemented)

`MemorySystem` (`src/god_agent/memory/system.py`) is a deterministic, offline
learning layer persisted as JSONL under `.god/memory`:

- **EpisodicMemory** — records each task attempt (task, path, accepted,
  verified) to `episodes.jsonl`.
- **ConventionDetector** — infers the project's coding conventions and caches
  them to `conventions.json`.
- **LessonStore** — distills recurring *failure* patterns into lessons to
  avoid.
- **SkillStore** — **new**; see Part 2.

`guidance_for(task)` assembles a compact block of conventions + relevant skills
+ relevant lessons and injects it into generation prompts, so history and style
actively shape new code. `export_bundle`/`import_bundle` let a team commit and
share learned knowledge.

Inspect learned memory:

```bash
py -m god_agent.cli memory
py -m god_agent.cli learn        # detect + store conventions
py -m god_agent.cli team export knowledge.json
py -m god_agent.cli team import knowledge.json
```

### 1.5 Autonomous loop (already implemented)

`AutonomousLoop` (`src/god_agent/loop.py`) runs **one iteration at a time**
(sequential). It owns only the cross-iteration concerns:

- **Exit conditions:** `max_runs`, optional `max_tokens` (spend during the
  loop), optional `max_seconds`, and a completion signal that must repeat
  `completion_threshold` times (default 2) so one stray "done" cannot stop the
  loop early.
- **Circuit breaker:** aborts after `max_consecutive_failures` (default 3)
  consecutive failing iterations.
- **Cross-iteration context:** a persistent `SHARED_TASK_NOTES.md` file under
  `.god/` that each iteration reads, then appends its progress to. This is a
  single sequential notes file, not a concurrent message bus.
- **Failure carryover:** a failed iteration's error is fed into the next.

Two built-in workflows are provided:

- `quality_sweep_workflow` — a fully deterministic, **no-LLM** loop body that
  verifies the project and critiques every source file, signalling completion
  once it both verifies and has no blocking findings.
- `sequential_codegen_workflow` — an LLM-driven pipeline that executes one
  `(instruction, path)` step per iteration, retrying a rejected step next
  iteration.

Run the offline quality sweep:

```bash
py -m god_agent.cli loop "self-check" --command "py -m pytest" --max-runs 2
```

CLI flags: `task`, `--command`, `--max-runs` (default 5), `--max-seconds`,
`--completion-threshold` (default 2).

### 1.6 Safety (already implemented)

- `FileSystemTool` — boundary-checked writes with backups.
- `ShellTool` — screened, time-boxed command execution.
- Blocked command patterns (`rm -rf /`, `mkfs`, fork bombs, force push,
  `git reset --hard`, `shutdown`, Windows recursive force-delete, …).
- Append-only audit log under `.god/audit.log`.
- Checkpoints + rollback around applied changes.

---

## Part 2 — New feature: Skill memory

### Summary

`SkillStore` (`src/god_agent/memory/skills.py`) is the positive-pattern mirror
of `LessonStore`. Where a lesson captures a recurring *failure* to avoid, a
**skill** captures a recurring *success* to repeat.

### How it works

- Skills are derived **deterministically** from episodic memory, considering
  only episodes that were both **accepted and verified**.
- Each successful episode's task text is mapped to an action category via a
  small keyword taxonomy (`test`, `refactor`, `document`, `optimize`, `fix`,
  `implement`, `add`) — no model, no embeddings.
- A `Skill` records the category, a count of successful verified episodes, a
  short actionable reminder, and up to three representative example tasks and
  file paths.
- `MemorySystem.relevant_skills(task)` merges skills proven on similar tasks
  with globally-recurring ones, and `guidance_for(task)` injects them into
  generation prompts under "Proven approaches from this project's history".

### Behaviour notes

- Skill derivation is stateless aggregation over the episode log; there is no
  separate skills file to corrupt.
- Like all memory writes, it must never break the primary workflow — skill
  guidance is additive and optional.

### Acceptance criteria

- Only accepted + verified episodes contribute to skills.
- Skills are ranked by success count, capped in examples/paths for compact
  prompts, and rendered as single-line reminders.
- Guidance injection degrades to nothing when no skills have been learned yet.

---

## Part 3 — Possible future work (NOT implemented)

The following are ideas only. None of this exists in the codebase today. They
are recorded here so they are not mistaken for shipped features.

### 3.1 Parallel / multi-agent execution (future idea)

The loop currently executes strictly one iteration at a time. Concepts such as
concurrent subagents, DAG/wave scheduling, a shared concurrent memory bus, or
"Nx speedup" claims are **not implemented**. A future design would need to
address ordering, safe concurrent filesystem/git access, and deterministic
verification before any of it could ship.

### 3.2 Long-context handling (future idea)

There is no special long-context mode or "skip context pruning" switch today.
Context is assembled by the existing context engine regardless of model. A
future enhancement could adapt context assembly to a model's advertised context
window.

---

## Appendix A — Configuration examples (real presets only)

### Local / free (Ollama)

```toml
[god-agent]
llm_provider = "ollama"
llm_model = "llama3.2"          # or any model you have pulled
llm_fast_model = "llama3.2"
llm_powerful_model = "llama3.2"
```

### Hosted with a free tier (Groq / Gemini)

```toml
[god-agent]
llm_provider = "groq"           # reads GROQ_API_KEY
# llm_model defaults to the preset's default; override if you like
```

### Hosted (Anthropic)

```toml
[god-agent]
llm_provider = "anthropic"      # reads ANTHROPIC_API_KEY
llm_fast_model = "claude-haiku"
llm_powerful_model = "claude-sonnet-4"
```

### Offline default (no setup)

```toml
[god-agent]
llm_provider = "mock"
```

---

## Appendix B — Relevant source files

```
src/god_agent/
├── llm/
│   ├── registry.py       # provider presets (openai, groq, ollama, mock, …)
│   ├── router.py         # ModelRouter — cost-aware routing (implemented)
│   └── orchestrator.py   # usage accounting + token budget (implemented)
├── memory/
│   ├── episodic.py       # EpisodicMemory
│   ├── conventions.py    # ConventionDetector
│   ├── lessons.py        # LessonStore (failure patterns)
│   ├── skills.py         # SkillStore (NEW — success patterns)
│   └── system.py         # MemorySystem façade + guidance_for()
├── loop.py               # AutonomousLoop (sequential) + workflows
├── safety.py             # audit, checkpoints, blocked patterns
└── tools/                # FileSystemTool, ShellTool, git_tool
```
