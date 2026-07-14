# GOD Agent — Summary

**Status:** Accurate description of shipped behaviour + one new feature

> Accuracy note: an earlier summary claimed parallel subagent execution, a
> shared memory bus, "3x speedup", invented model names, and specific benchmark
> percentages. None of those were real. This version reflects the code.

---

## What the agent actually is

GOD agent is a self-improving, offline-first autonomous coding agent with:

- A **reasoning engine** (plan → generate → critique → apply) with guarded
  apply (checkpoint, verify, remember).
- A **memory system** that learns conventions, lessons (failures to avoid), and
  now skills (successes to repeat) — all deterministic and offline.
- **Safety guardrails**: boundary-checked file writes with backups, screened
  shell execution, blocked command patterns, audit log, checkpoints + rollback.
- A **sequential autonomous loop** with budgets, a completion-signal threshold,
  a failure circuit breaker, and cross-iteration notes.

The core has **zero third-party runtime dependencies** (Python 3.11+ standard
library only). Optional provider integrations import lazily and degrade to the
offline mock provider.

---

## Existing capabilities (already shipped)

### Provider registry
Choose a provider by preset name with `llm_provider = "<preset>"`. Real presets
include hosted OpenAI-compatible services (`openai`, `groq`, `openrouter`,
`deepseek`, `mistral`, `together`, `fireworks`, `xai`, `perplexity`), native
`anthropic` and `gemini`, local `ollama`/`lmstudio`/`vllm`/`llamacpp`, and the
offline `mock` default.

### Cost-aware model routing
`ModelRouter` already routes trivial/exploration/test work to `llm_fast_model`
and complex/long work to `llm_powerful_model`, wired into the generate path.

### Usage accounting + token budget
`LLMOrchestrator` tracks tokens and enforces an optional `budget_tokens`.

### Memory
Episodic memory, convention detection, and lesson mining, all persisted as JSONL
under `.god/memory`. `guidance_for(task)` injects the relevant subset into
prompts. `export_bundle`/`import_bundle` share knowledge across a team.

### Autonomous loop
`AutonomousLoop` runs one iteration at a time with `quality_sweep_workflow`
(offline) and `sequential_codegen_workflow` (LLM-driven).

---

## New: Skill memory

`SkillStore` distills **accepted + verified** episodes into reusable skills —
the positive-pattern mirror of the existing lesson store. Each skill records a
task category, how many times it succeeded, a short reminder, and a few example
tasks/paths. Skills are injected into generation prompts alongside conventions
and lessons via `guidance_for(task)`. Derivation is deterministic (keyword
taxonomy, no model or embeddings) and offline.

---

## Possible future work (NOT implemented)

- **Parallel / multi-agent execution.** The loop is sequential; concurrent
  subagents, DAG scheduling, and a shared concurrent memory bus do not exist.
- **Long-context handling.** No long-context mode exists today.

These are ideas, not shipped features, and not currently scheduled.

---

## Getting started

Offline, no setup:

```bash
py -m god_agent.cli loop "self-check" --command "py -m pytest" --max-runs 2
```

Local and free with Ollama:

```bash
ollama pull llama3.2
```

```toml
# god_agent.toml
[god-agent]
llm_provider = "ollama"
llm_model = "llama3.2"
```

See `QUICKSTART_FREE_VARIANT.md` for the full local setup and
`UPGRADE_2026_SPEC.md` for the capability reference.

---

## Verification

```bash
py -m pytest
```

The suite must stay green and runs fully offline (no network, no API key).
