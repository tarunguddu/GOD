"""Positive-pattern memory — distilling successful episodes into reusable skills.

The mirror image of :mod:`lessons`. Where a :class:`Lesson` captures a recurring
*failure* to avoid, a :class:`Skill` captures a recurring *success* to repeat: a
category of task the agent has completed and verified before, with a count and a
short, actionable reminder. Skills are derived deterministically from episodic
memory (accepted **and** verified episodes only) and injected into generation
prompts alongside lessons, so proven approaches actively shape new work.

Categorisation is a small, deterministic keyword taxonomy — no model, no
embeddings — matching the offline-first philosophy of the rest of the agent.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .episodic import Episode


# Action category -> the reusable reminder surfaced back to the model.
_SKILL_ADVICE: dict[str, str] = {
    "test": "Reuse the project's proven testing approach (offline, table-driven pytest).",
    "refactor": "Refactor in small, individually-verified steps as done successfully before.",
    "document": "Follow the established docstring/README style already applied here.",
    "implement": "Mirror the structure of features you implemented and verified before.",
    "fix": "Apply the same focused, minimal-diff fix approach that verified cleanly before.",
    "add": "Follow the established pattern for adding this kind of component.",
    "optimize": "Reuse the measurement-first optimisation approach proven here.",
}

# Keywords that map a task description to an action category. Order matters only
# for determinism; the first matching category wins.
_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("test", ("test", "tests", "pytest", "coverage")),
    ("refactor", ("refactor", "restructure", "rename", "extract")),
    ("document", ("document", "docstring", "readme", "docs", "comment")),
    ("optimize", ("optimize", "optimise", "performance", "faster", "speed")),
    ("fix", ("fix", "bug", "patch", "repair")),
    ("implement", ("implement", "build", "create", "feature")),
    ("add", ("add",)),
)


# How many concrete examples/paths to retain per skill — enough to be
# actionable, few enough to keep injected guidance compact.
_MAX_EXAMPLES = 3


@dataclass
class Skill:
    pattern: str                       # action category, e.g. "test"
    count: int                         # number of successful, verified episodes
    advice: str
    examples: list[str] = field(default_factory=list)  # representative tasks
    paths: list[str] = field(default_factory=list)     # files it was applied to

    def render(self) -> str:
        detail = ""
        if self.examples:
            detail = f'; e.g. "{self.examples[0]}"'
            if self.paths:
                detail += f" -> {self.paths[0]}"
        elif self.paths:
            detail = f"; e.g. {self.paths[0]}"
        return (f"- {self.advice} "
                f"(proven {self.count}x on '{self.pattern}' work{detail})")


def _categorize(task: str) -> str | None:
    low = (task or "").lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(kw in low for kw in keywords):
            return category
    return None


def _add_capped(items: list[str], value: str | None) -> None:
    """Append ``value`` to ``items`` if truthy, unique, and under the cap.

    Keeps retained examples/paths deduplicated and bounded so the guidance
    block injected into prompts stays compact regardless of history size.
    """
    if value and value not in items and len(items) < _MAX_EXAMPLES:
        items.append(value)


class SkillStore:
    """Computes reusable skills from successful episodes (stateless aggregator)."""

    @staticmethod
    def _successful(episodes: list[Episode]) -> list[Episode]:
        return [ep for ep in episodes if ep.accepted and ep.verified]

    def derive(self, episodes: list[Episode], min_count: int = 1) -> list[Skill]:
        counts: Counter[str] = Counter()
        examples: dict[str, list[str]] = {}
        paths: dict[str, list[str]] = {}
        for ep in self._successful(episodes):
            category = _categorize(ep.task)
            if category is None:
                continue
            counts[category] += 1
            _add_capped(examples.setdefault(category, []), ep.task)
            if ep.path:
                _add_capped(paths.setdefault(category, []), ep.path)

        skills = [
            Skill(
                pattern=category,
                count=count,
                advice=_SKILL_ADVICE.get(
                    category, f"Reuse your proven approach to '{category}' work."),
                examples=examples.get(category, []),
                paths=paths.get(category, []),
            )
            for category, count in counts.items()
            if count >= min_count
        ]
        skills.sort(key=lambda skill: skill.count, reverse=True)
        return skills

    def top(self, episodes: list[Episode], n: int = 5) -> list[Skill]:
        return self.derive(episodes)[:n]
