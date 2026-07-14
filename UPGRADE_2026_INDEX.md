# GOD Agent — Documentation Index

**Navigation for the capability and setup docs.**

> Accuracy note: an earlier index described a multi-phase plan to build parallel
> execution, a shared memory bus, and free-model "variants" with invented model
> names and benchmark numbers. Those features were never implemented. These docs
> now describe what the agent actually does, the newly added skill memory, and a
> clearly-labeled list of possible future work.

---

## Documents

### 1. UPGRADE_2026_SUMMARY.md — start here
A short overview: what the agent is, the capabilities that already ship, the new
skill-memory feature, and what is explicitly *not* implemented.

### 2. VARIANT_COMPARISON.md — choosing a provider
There are no product "variants". What varies is the **provider preset** you
configure. This doc lists the real presets (offline `mock`, local `ollama`/etc.,
hosted APIs) and helps you pick one. No benchmark claims.

### 3. QUICKSTART_FREE_VARIANT.md — local setup
Step-by-step local setup with the real `ollama` preset: install Ollama,
`ollama pull llama3.2`, set `llm_provider = "ollama"` and `llm_model`, then run
`py -m god_agent.cli ...`.

### 4. UPGRADE_2026_SPEC.md — capability reference
The detailed reference: provider registry, cost-aware routing, usage/budget,
memory (including new skill memory), the sequential loop, and safety. Includes a
"Possible future work" section for parallel execution and long-context.

### 5. UPGRADE_TASKS.md — status notes
Records what is already implemented, the one newly added feature (skill memory),
and future ideas that are not scheduled.

### 6. UPGRADE_2026_INDEX.md — this file
Navigation.

---

## What the agent actually does (at a glance)

- **Zero third-party runtime dependencies** in the core (Python 3.11+ stdlib).
- **Provider registry** with presets: `openai`, `groq`, `openrouter`,
  `deepseek`, `mistral`, `together`, `fireworks`, `xai`, `perplexity`,
  `anthropic`, `gemini`, `ollama`, `lmstudio`, `vllm`, `llamacpp`, `mock`.
- **Cost-aware routing** (`ModelRouter`) — already implemented and wired in.
- **Usage accounting + token budget** (`LLMOrchestrator`).
- **Deterministic offline memory**: episodic memory, convention detection,
  lessons (failures), and **skills** (successes, new). `guidance_for(task)`
  injects the relevant subset into prompts. `export_bundle`/`import_bundle`
  share knowledge across a team.
- **Sequential autonomous loop** (`AutonomousLoop`) with `quality_sweep_workflow`
  (offline) and `sequential_codegen_workflow`, completion threshold, failure
  circuit breaker, token/time budgets, and `SHARED_TASK_NOTES.md`.
- **Safety**: boundary-checked file writes with backups, screened shell, blocked
  command patterns, audit log, checkpoints + rollback.

## New feature

- **Skill memory** (`src/god_agent/memory/skills.py`): distills accepted +
  verified episodes into reusable, injectable skills. Deterministic, offline.

## Possible future work (NOT implemented)

- Parallel / multi-agent execution and a shared concurrent memory bus. The loop
  is sequential.
- Long-context handling.

---

## File map

```
d:\GOD\god_agent\
├── UPGRADE_2026_INDEX.md        ← this file
├── UPGRADE_2026_SUMMARY.md      ← overview
├── VARIANT_COMPARISON.md        ← choosing a provider preset
├── QUICKSTART_FREE_VARIANT.md   ← local Ollama setup
├── UPGRADE_2026_SPEC.md         ← capability reference
└── UPGRADE_TASKS.md             ← status + future ideas
```

## Common commands

```bash
# Offline quality-sweep loop (no model calls)
py -m god_agent.cli loop "self-check" --command "py -m pytest" --max-runs 2

# Inspect providers, models, routing, memory
py -m god_agent.cli providers
py -m god_agent.cli models
py -m god_agent.cli route "<task>"
py -m god_agent.cli memory

# Run the test suite (fully offline)
py -m pytest
```
