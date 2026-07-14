"""MemorySystem — the façade that makes learning usable.

It records episodes, derives lessons, caches detected conventions, and — the
part that closes the loop — produces ``guidance_for(task)``: a compact block of
the project's conventions plus the lessons most relevant to the task at hand.
The reasoning engine injects this into generation prompts, so the agent's own
history and the codebase's style actively shape new code.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from .conventions import Conventions, ConventionDetector
from .episodic import Episode, EpisodicMemory
from .lessons import Lesson, LessonStore
from .skills import Skill, SkillStore


class MemorySystem:
    def __init__(self, project_root: str | Path, memory_dir: str = ".god/memory") -> None:
        self.root = Path(project_root)
        self.dir = self.root / memory_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.episodic = EpisodicMemory(self.dir / "episodes.jsonl")
        self.lessons = LessonStore()
        self.skills = SkillStore()
        self._conventions_path = self.dir / "conventions.json"
        self._detector = ConventionDetector(project_root)

    # ---- recording ---------------------------------------------------------
    def record_episode(self, episode: Episode) -> Episode:
        return self.episodic.record(episode)

    # ---- conventions -------------------------------------------------------
    def learn_conventions(self, force: bool = False) -> Conventions:
        if not force and self._conventions_path.exists():
            cached = self._load_conventions()
            if cached is not None:
                return cached
        conv = self._detector.detect()
        self._write_conventions(conv)
        return conv

    def conventions(self) -> Conventions | None:
        if self._conventions_path.exists():
            return self._load_conventions()
        return None

    def _write_conventions(self, conv: Conventions) -> None:
        # Atomic write so an interrupted run cannot leave a truncated cache that
        # would then break every later load.
        tmp = self._conventions_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(conv), indent=2), encoding="utf-8")
        os.replace(tmp, self._conventions_path)

    def _load_conventions(self) -> Conventions | None:
        """Load the cached conventions, tolerating corruption / schema drift.

        Memory must never break the primary workflow, so a bad cache yields None
        (callers fall back to re-detecting or skipping guidance) rather than
        raising.
        """
        try:
            data = json.loads(self._conventions_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        known = {f for f in Conventions.__dataclass_fields__}
        return Conventions(**{k: v for k, v in data.items() if k in known})

    # ---- lessons -----------------------------------------------------------
    def top_lessons(self, n: int = 5) -> list[Lesson]:
        return self.lessons.top(self.episodic.all(), n=n)

    def relevant_lessons(self, task: str, n: int = 5) -> list[Lesson]:
        """Lessons drawn from globally-recurring patterns plus those seen on
        tasks similar to ``task``."""
        episodes = self.episodic.all()          # single read, reused below
        global_lessons = self.lessons.derive(episodes)
        similar = [ep for ep, _ in self.episodic.find_similar(task, top_k=10)]
        if not similar:
            return global_lessons[:n]
        similar_lessons = self.lessons.derive(similar)
        # Merge, preferring lessons that show up in similar tasks.
        seen: dict[str, Lesson] = {}
        for lesson in similar_lessons + global_lessons:
            if lesson.pattern not in seen:
                seen[lesson.pattern] = lesson
        return list(seen.values())[:n]

    # ---- skills (positive-pattern reuse) ----------------------------------
    def top_skills(self, n: int = 5) -> list[Skill]:
        return self.skills.top(self.episodic.all(), n=n)

    def relevant_skills(self, task: str, n: int = 5) -> list[Skill]:
        """Proven approaches drawn from globally-recurring successes plus those
        seen on tasks similar to ``task``."""
        episodes = self.episodic.all()          # single read, reused below
        global_skills = self.skills.derive(episodes)
        similar = [ep for ep, _ in self.episodic.find_similar(task, top_k=10)]
        if not similar:
            return global_skills[:n]
        similar_skills = self.skills.derive(similar)
        # Merge, preferring skills proven on similar tasks.
        seen: dict[str, Skill] = {}
        for skill in similar_skills + global_skills:
            if skill.pattern not in seen:
                seen[skill.pattern] = skill
        return list(seen.values())[:n]

    # ---- the closing of the loop ------------------------------------------
    def guidance_for(self, task: str, max_lessons: int = 4) -> str:
        """A compact guidance block (conventions + relevant lessons) suitable
        for injection into a generation prompt. Returns '' when there is nothing
        learned yet, so early prompts are not polluted with empty sections."""
        sections: list[str] = []
        conv = self.conventions()
        if conv is not None:
            sections.append("Project conventions (match these):\n" + conv.render())
        skills = self.relevant_skills(task, n=max_lessons)
        if skills:
            sections.append(
                "Proven approaches from this project's history (reuse these):\n"
                + "\n".join(skill.render() for skill in skills)
            )
        lessons = self.relevant_lessons(task, n=max_lessons)
        if lessons:
            sections.append(
                "Lessons from this project's history (avoid repeating these):\n"
                + "\n".join(lesson.render() for lesson in lessons)
            )
        return "\n\n".join(sections)

    def stats(self) -> dict:
        return self.episodic.stats()

    # ---- team knowledge sharing -------------------------------------------
    def export_bundle(self) -> dict:
        """A portable snapshot of learned knowledge a team can commit + share."""
        from dataclasses import asdict
        conv = self.conventions()
        return {
            "version": 1,
            "conventions": asdict(conv) if conv else None,
            "episodes": [asdict(e) for e in self.episodic.all()],
            "lessons": [l.render() for l in self.top_lessons(n=20)],
        }

    def import_bundle(self, bundle: dict) -> int:
        """Merge a shared bundle into local memory. Returns episodes imported.

        Conventions are adopted only if none are learned locally yet (local
        observations win). Episodes are appended so lessons compound.
        """
        if not isinstance(bundle, dict):
            raise ValueError("bundle must be a mapping")
        conv = bundle.get("conventions")
        if conv and self.conventions() is None:
            known = {f for f in Conventions.__dataclass_fields__}
            self._write_conventions(
                Conventions(**{k: v for k, v in conv.items() if k in known}))
        imported = 0
        for raw in bundle.get("episodes", []):
            try:
                self.episodic.record(Episode.from_dict(raw))
                imported += 1
            except (TypeError, AttributeError):
                continue
        return imported
