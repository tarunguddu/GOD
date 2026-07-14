# Architecture

## Design philosophy

The agent is built around one conviction: **the deterministic parts are the
valuable parts.** Workspace boundaries, self-verification, reversible changes,
and dependency vetting need no model, run offline, and cannot be skipped by a
prompt. Each subsystem maps to a documented, real-world coding-agent failure:

| Real failure | Mitigation in this project |
|--------------|----------------------------|
| Agents inherit full filesystem permissions | `WorkspaceBoundary` resolves & checks every path in code |
| Confident but false "it's done" claims | `Verifier` runs tests, parses output, detects fake-green |
| Instructions followed inconsistently | Critical rules enforced in code, not prose |
| Autonomy causing unintended changes | Checkpoints + one-call rollback before every mutation |
| Hallucinated / "slopsquatted" deps | `DependencyChecker` registry + typosquat checks |
| No semantic code understanding | `CodeGraph` (AST) — symbols, callers, impact, hotspots |
| Elevated vulnerability rate in AI code | `SelfCritic` deterministic secrets/vuln scan before code lands |
| Repeating the same mistakes | `MemorySystem` learns and feeds lessons back into prompts |
| Reactive only | `ProactiveEngine` surfaces issues unprompted |
| Model lock-in | `ModelRouter` task-aware fast/powerful selection |
| Unpredictable cost | Usage accounting + token-budget caps |

## The guarded pipeline

The heart of the agent is `ReasoningEngine.safe_apply`:

```
critique  ->  checkpoint  ->  write  ->  verify  ->  (rollback on failure)
   |                                         |
 blocking findings abort               failed verification
 BEFORE writing to disk                reverts the change
```

`generate_and_apply` puts model generation in front of this pipeline; generated
code is never trusted on its own.

## Module map

```
god_agent/
├── workspace.py        # WorkspaceBoundary — deterministic path confinement
├── safety.py           # risk assessment, audit log, checkpoints, rollback
├── config.py           # layered config (defaults < god_agent.toml < flags)
├── verify.py           # self-verification: run tests, parse, detect fake-green
├── depcheck.py         # dependency hallucination / typosquat guard
├── proactive.py        # ProactiveEngine: health analysis + bounded watch
├── sandbox.py          # SandboxManager: isolated execution + promote-if-good
├── web.py              # zero-dependency read-only dashboard + JSON API
├── team.py             # knowledge bundles, onboarding docs, code ownership
├── loop.py             # AutonomousLoop: exit conditions, notes, circuit breaker
├── agent.py            # GodAgent façade wiring everything together
├── cli.py              # the `god` command
├── tools/
│   ├── filesystem.py   # read/write/edit/delete with backups + boundary checks
│   ├── shell.py        # screened, time-boxed command execution
│   └── git_tool.py     # status/diff, commit-message synthesis, who-knows
├── context/
│   ├── code_graph.py   # AST symbol/import graph, callers, impact, hotspots
│   └── engine.py       # stack detection + relevance search
├── reasoning/
│   ├── critic.py       # deterministic secrets/vuln/stub review + suppression
│   ├── planner.py      # scope classification + verify-anchored plans
│   ├── generator.py    # multi-pass LLM code generation (critique-driven)
│   └── engine.py       # safe_apply + generate_and_apply
├── memory/
│   ├── episodic.py     # durable JSONL log of actions + outcomes
│   ├── lessons.py      # error-pattern recognition -> lessons
│   ├── conventions.py  # deterministic house-style detection
│   └── system.py       # MemorySystem façade: guidance_for() closes the loop
└── llm/
    ├── base.py         # provider-agnostic interfaces
    ├── mock.py         # deterministic offline provider (default)
    ├── scripted.py     # scripted provider for tests/demos
    ├── anthropic_provider.py  # optional real Claude backend (retry + routing)
    ├── router.py       # task-aware fast/powerful routing
    └── orchestrator.py # provider selection + usage/budget accounting
```

## How the agent "gets better"

1. Every guarded change is recorded as an `Episode` (task, critique rules,
   verification verdict, accepted/rejected).
2. `LessonStore` aggregates recurring failures into short, actionable lessons.
3. `ConventionDetector` infers house style from the code itself.
4. `MemorySystem.guidance_for(task)` combines conventions + relevant lessons and
   the reasoning engine injects that block into future generation prompts.

So a mistake the critic catches once becomes guidance the model sees next time.

## Build phases (all implemented)

- **Phase 1 — Foundation:** CLI, tools, boundaries, backups, config.
- **Phase 2 — Intelligence:** code graph, verification, critic, generation, depcheck.
- **Phase 3 — Memory & Learning:** episodic memory, lessons, conventions, the loop-closer.
- **Phase 4 — Proactive & Advanced:** health analysis, watch, routing, sandbox.
- **Phase 5 — Polish & Scale:** web dashboard, VS Code extension, team features.
