"""Error-pattern recognition — distilling episodes into actionable lessons.

A :class:`Lesson` is a short, recurring failure pattern with a count and a piece
of advice. Lessons are derived deterministically from episodic memory: which
critique rules fired most often, and which kinds of verification failures
recurred. The reasoning engine injects the top lessons into generation prompts
so the same mistake is less likely to be repeated.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .episodic import Episode


# Map a critique rule (or rule family) to human advice for the model.
_RULE_ADVICE: dict[str, str] = {
    "secret": "Never hardcode credentials; read them from environment variables.",
    "vuln:dynamic-exec": "Avoid eval/exec/compile; use explicit dispatch instead.",
    "vuln:shell-injection": "Do not use shell=True; pass an argument list.",
    "vuln:sql-injection": "Use parameterised queries, never string formatting.",
    "vuln:pickle-loads": "Avoid pickle/marshal on untrusted data.",
    "stub:empty-function": "Implement functions fully; no pass/TODO/NotImplementedError stubs.",
    "smell:bare-except": "Catch specific exceptions, not bare except.",
    "syntax-error": "Ensure the code parses before returning it.",
}


@dataclass
class Lesson:
    pattern: str
    count: int
    advice: str

    def render(self) -> str:
        return f"- {self.advice} (seen {self.count}x as '{self.pattern}')"


class LessonStore:
    """Computes lessons from a collection of episodes (stateless aggregator)."""

    def derive(self, episodes: list[Episode], min_count: int = 1) -> list[Lesson]:
        rule_counts: Counter[str] = Counter()
        for ep in episodes:
            for rule in ep.critique_rules:
                rule_counts[rule] += 1

        # Verification failures are their own lesson family.
        verify_failures = sum(1 for ep in episodes if ep.verified is False)

        lessons: list[Lesson] = []
        for rule, count in rule_counts.items():
            if count < min_count:
                continue
            lessons.append(Lesson(pattern=rule, count=count,
                                  advice=_advice_for(rule)))

        if verify_failures >= min_count:
            lessons.append(Lesson(
                pattern="verification-failure", count=verify_failures,
                advice="Run and pass the test suite before considering work done.",
            ))

        lessons.sort(key=lambda lesson: lesson.count, reverse=True)
        return lessons

    def top(self, episodes: list[Episode], n: int = 5) -> list[Lesson]:
        return self.derive(episodes)[:n]


def _advice_for(rule: str) -> str:
    if rule in _RULE_ADVICE:
        return _RULE_ADVICE[rule]
    family = rule.split(":")[0]
    return _RULE_ADVICE.get(family, f"Avoid the pattern that triggers '{rule}'.")
