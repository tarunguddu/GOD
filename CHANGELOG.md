# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Skill memory — reusing what worked (2026-07-05).** A positive-pattern
  counterpart to lesson memory that distills successful episodes into reusable
  approaches and feeds them back into generation prompts.
  - New `god_agent.memory.skills` module with the `Skill` dataclass and
    `SkillStore`, the positive mirror of `LessonStore`. Skills are derived from
    episodes that were **both accepted and verified**, categorised by a
    deterministic keyword taxonomy (`test`, `refactor`, `document`, `optimize`,
    `fix`, `implement`, `add`), each with a count and deduplicated example task
    descriptions and file paths (capped at 3 each).
  - `MemorySystem.top_skills(n)` and `MemorySystem.relevant_skills(task, n)`,
    the latter preferring skills proven on similar past tasks via Jaccard token
    overlap (mirroring `relevant_lessons`).
  - `MemorySystem.guidance_for(task)` now injects a "Proven approaches from this
    project's history (reuse these)" section alongside conventions and lessons;
    this guidance is fed into generation prompts by
    `ReasoningEngine.generate_and_apply`.
  - `god memory` now prints a "skills (proven approaches to reuse)" section
    alongside conventions and lessons.
  - Documentation: [`docs/skills.md`](docs/skills.md).
  - Tests: `tests/test_skills.py` (14 tests).
  - Deterministic, offline, JSONL-backed (uses the existing
    `.god/memory/episodes.jsonl`), with no new third-party dependencies.
