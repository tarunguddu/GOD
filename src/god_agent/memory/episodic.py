"""Episodic memory — a durable, queryable log of the agent's actions.

Each :class:`Episode` records a single attempted change: what was asked, which
file, the critique rules that fired, the verification verdict, and whether it
was ultimately accepted. Stored as JSON-lines so it is append-only, diffable,
and trivially inspectable. Recall is by token-overlap similarity (no embedding
backend required), matching the offline-first philosophy of the rest of the
agent.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")


@dataclass
class Episode:
    task: str
    path: str | None = None
    accepted: bool = False
    critique_rules: list[str] = field(default_factory=list)
    verified: bool | None = None
    verdict: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> "Episode":
        if not isinstance(data, dict):
            raise TypeError("episode record is not an object")
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


class EpisodicMemory:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, episode: Episode) -> Episode:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(episode.to_json() + "\n")
        return episode

    def all(self) -> list[Episode]:
        if not self.path.exists():
            return []
        episodes: list[Episode] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                episodes.append(Episode.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue
        return episodes

    def recent(self, n: int = 10) -> list[Episode]:
        return self.all()[-n:]

    def find_similar(self, task: str, top_k: int = 5) -> list[tuple[Episode, float]]:
        """Return past episodes most similar to ``task`` (Jaccard token overlap)."""
        query = _tokenize(task)
        if not query:
            return []
        scored: list[tuple[Episode, float]] = []
        for ep in self.all():
            tokens = _tokenize(ep.task)
            if not tokens:
                continue
            score = _jaccard(query, tokens)
            if score > 0:
                scored.append((ep, round(score, 3)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def stats(self) -> dict[str, int]:
        episodes = self.all()
        accepted = sum(1 for e in episodes if e.accepted)
        verified = sum(1 for e in episodes if e.verified)
        return {
            "episodes": len(episodes),
            "accepted": accepted,
            "rejected": len(episodes) - accepted,
            "verified": verified,
        }


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
