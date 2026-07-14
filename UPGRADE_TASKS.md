# GOD Agent — Task Notes (accuracy pass)

**Parent doc:** UPGRADE_2026_SPEC.md
**Status:** Most items below are already shipped; skill memory is newly added.

> Accuracy note: the previous version of this file listed a multi-day plan to
> build parallel execution, a shared memory bus, and Ollama-only "free" model
> presets with invented names. Those tasks are removed. The routing, budget,
> memory, loop, and safety features they described **already exist**. This file
> now records what is done and the one genuinely new addition.

---

## Already implemented (no work required)

### Cost-aware model routing — DONE
- File: `src/god_agent/llm/router.py` (`ModelRouter`, `RouteDecision`).
- Routes exploration/test scope to `llm_fast_model`, escalates long fast-scope
  instructions and all other scopes to `llm_powerful_model`.
- Wired into `reasoning/engine.py`. Deterministic and unit-tested.
- CLI: `py -m god_agent.cli route "<task>"`.

### Usage accounting + token budget — DONE
- File: `src/god_agent/llm/orchestrator.py` (`LLMOrchestrator`, `UsageTotals`).
- Tracks request/token/char totals; enforces optional `budget_tokens`.

### Provider registry — DONE
- File: `src/god_agent/llm/registry.py`.
- Real presets: `openai`, `groq`, `openrouter`, `deepseek`, `mistral`,
  `together`, `fireworks`, `xai`, `perplexity`, `anthropic`, `gemini`,
  `ollama`, `lmstudio`, `vllm`, `llamacpp`, `mock`.
- CLI: `py -m god_agent.cli providers`, `py -m god_agent.cli models`.

### Memory system — DONE
- Files: `src/god_agent/memory/{episodic,conventions,lessons,system}.py`.
- Deterministic, offline, JSONL under `.god/memory`.
- `guidance_for(task)` injects conventions + skills + lessons into prompts.
- `export_bundle`/`import_bundle` for team sharing.

### Autonomous loop — DONE
- File: `src/god_agent/loop.py` (`AutonomousLoop`).
- **Sequential**, one iteration at a time. Completion-signal threshold,
  consecutive-failure circuit breaker, token/time budgets, and
  `SHARED_TASK_NOTES.md` cross-iteration notes.
- Workflows: `quality_sweep_workflow` (offline, no LLM),
  `sequential_codegen_workflow` (LLM-driven).

### Safety — DONE
- `FileSystemTool` (boundary-checked, backups), `ShellTool` (screened),
  blocked command patterns, audit log, checkpoints + rollback.

---

## Newly added

### Skill memory (`SkillStore`) — DONE
- File: `src/god_agent/memory/skills.py`; tests in `tests/test_skills.py`.
- Deterministically distills **accepted + verified** episodes into reusable
  "skills" (proven approaches, with a count, a short reminder, and up to three
  example tasks/paths).
- Integrated into `MemorySystem.relevant_skills` / `top_skills` and surfaced by
  `guidance_for(task)` under "Proven approaches from this project's history".

**Acceptance checks**
- [x] Only accepted + verified episodes contribute.
- [x] Deterministic keyword taxonomy (no model, no embeddings).
- [x] Examples/paths capped for compact prompt injection.
- [x] Skills ranked by success count.
- [x] Suite stays green and runs fully offline: `py -m pytest`.

---

## Possible future work (NOT started, NOT scheduled)

These are ideas, not committed tasks. Do not treat them as shipped.

- **Parallel / multi-agent execution.** The loop is sequential by design.
  Concurrent subagents, DAG/wave scheduling, and a shared concurrent memory bus
  are not implemented and would require careful handling of ordering and
  concurrent filesystem/git access.
- **Long-context handling.** No long-context mode or context-pruning switch
  exists today.

---

## Verification

Never claim completion without running the suite:

```bash
py -m pytest
py -m god_agent.cli loop "self-check" --command "py -m pytest" --max-runs 2
```
