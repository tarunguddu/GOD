# Skill memory — reusing what worked

Skill memory is the positive mirror of [lesson memory](workflows.md#autonomous-quality-loop).
Where lessons capture recurring **failures to avoid**, skills capture recurring
**successes to repeat** — categories of task the agent has already completed and
verified in this project, distilled into short, actionable reminders and fed
back into generation prompts.

Like the rest of the memory system, it is **deterministic, offline, and adds no
third-party dependencies**. Skills are computed on demand from the existing
episodic log (`.god/memory/episodes.jsonl`) — there is no model, no embeddings,
and nothing new to persist.

## Skills vs. lessons

| | Lessons (`LessonStore`) | Skills (`SkillStore`) |
|---|---|---|
| Learns from | Failures — recurring critique rules and verification failures | Successes — episodes that were **accepted and verified** |
| Produces | "Avoid these" reminders | "Reuse these" reminders |
| Surfaces in | `guidance_for()`, `god memory` | `guidance_for()`, `god memory` |

Both are derived the same way (aggregate over episodes, rank by recurrence) and
both are injected into the prompt so the agent's own history actively shapes new
work.

## How a skill is derived

`SkillStore.derive()` walks the episodic log and:

1. **Filters to proven successes.** Only episodes that are *both* `accepted` and
   `verified` are considered. An accepted-but-unverified change, or a verified
   change that was rejected, is ignored — a skill is only claimed once the work
   actually landed and passed verification.
2. **Categorises each task** with a small, fixed keyword taxonomy. The first
   matching category wins, in this order: `test`, `refactor`, `document`,
   `optimize`, `fix`, `implement`, `add`. Tasks that match no keyword are
   skipped.
3. **Aggregates per category** into a `Skill` with:
   - `count` — how many proven episodes fell into the category;
   - `advice` — the reusable reminder for that category;
   - `examples` — representative task descriptions (deduplicated, capped at 3);
   - `paths` — files the work touched (deduplicated, capped at 3).

Skills are sorted by `count` (most-proven first). The caps keep the guidance
block compact no matter how long the history grows.

### The `Skill` dataclass

```python
@dataclass
class Skill:
    pattern: str          # action category, e.g. "test"
    count: int            # number of accepted + verified episodes
    advice: str           # the reusable reminder
    examples: list[str]   # representative task descriptions (<= 3)
    paths: list[str]      # files it was applied to (<= 3)
```

## How skills surface

### In generation prompts (`guidance_for`)

`MemorySystem.guidance_for(task)` assembles a compact guidance block that the
`ReasoningEngine.generate_and_apply` flow injects into the model prompt. It now
has three sections when data is available:

1. **Project conventions** (match these)
2. **Proven approaches from this project's history** (reuse these) — skills
3. **Lessons from this project's history** (avoid repeating these) — lessons

The skills shown are `relevant_skills(task)`, which prefers approaches proven on
tasks similar to the current one (Jaccard token overlap over past task
descriptions), falling back to the globally most-proven skills — exactly
mirroring how `relevant_lessons` works.

### On the command line (`god memory`)

`god memory` prints a `skills (proven approaches to reuse)` section alongside
conventions and lessons:

```text
$ god memory
episodes: 12 (accepted=9, rejected=3, verified=7)

conventions (from 24 files):
  functions=snake_case, indent=4 spaces, quotes=double

skills (proven approaches to reuse):
  - Reuse the project's proven testing approach (offline, table-driven pytest). (proven 4x on 'test' work; e.g. "add tests for the config loader" → tests/test_config.py)
  - Apply the same focused, minimal-diff fix approach that verified cleanly before. (proven 2x on 'fix' work; e.g. "fix path traversal in loader" → src/god_agent/workspace.py)

lessons learned:
  - ...
```

When no episode has yet been both accepted and verified, the section reads
`skills: none yet (no verified successes)`.

## Using it from Python

```python
from god_agent.memory.system import MemorySystem

memory = MemorySystem(project_root=".")

# The most-proven approaches across all history.
for skill in memory.top_skills(n=5):
    print(skill.pattern, skill.count, skill.advice)

# Approaches proven on tasks similar to the one at hand, preferred first.
for skill in memory.relevant_skills("add unit tests for the parser", n=4):
    print(skill.render())
```

`top_skills(n)` returns the globally most-proven skills; `relevant_skills(task,
n)` biases toward skills proven on similar past tasks and is what
`guidance_for` uses.

## Design notes

- **Zero dependencies, fully offline.** Categorisation is keyword matching and
  similarity is token-overlap Jaccard — no network, no API key, no model.
- **Deterministic.** The same episodic log always yields the same skills,
  ordered the same way.
- **Non-destructive.** `SkillStore` is a stateless aggregator over the existing
  `episodes.jsonl`; it writes nothing and cannot break the primary workflow.
- **Bounded output.** Examples and paths are deduplicated and capped so injected
  guidance stays small regardless of history size.

## See also

- [Workflows](workflows.md) — where episodes are recorded and memory is used
- [Architecture](architecture.md) — how `MemorySystem` fits the wider design
- [CLI reference](cli-reference.md) — the `god memory` command
