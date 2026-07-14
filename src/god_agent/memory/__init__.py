"""Memory & learning — the subsystem that makes the agent improve with use.

Everything here is deterministic and offline (JSONL-backed under ``.god/memory``):

  - EpisodicMemory: a durable, queryable log of what the agent did and how it
    turned out (critique findings + verification verdict per change).
  - LessonStore: error-pattern recognition over episodes — which critique rules
    and verification failures recur, distilled into short, actionable lessons.
  - SkillStore: the positive mirror of LessonStore — recurring *successes*
    (accepted + verified episodes) distilled into proven approaches to reuse.
  - ConventionDetector: infers the project's coding conventions (indentation,
    quotes, naming, typing, docstrings) straight from the code.
  - MemorySystem: the façade. Its ``guidance_for(task)`` produces a compact
    block of lessons + conventions that is injected back into generation
    prompts — closing the loop so past mistakes and house style shape future
    code.
"""

from .episodic import Episode, EpisodicMemory
from .lessons import Lesson, LessonStore
from .skills import Skill, SkillStore
from .conventions import Conventions, ConventionDetector
from .system import MemorySystem

__all__ = [
    "Episode",
    "EpisodicMemory",
    "Lesson",
    "LessonStore",
    "Skill",
    "SkillStore",
    "Conventions",
    "ConventionDetector",
    "MemorySystem",
]
