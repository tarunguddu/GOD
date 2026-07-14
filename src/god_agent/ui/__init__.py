"""User-interface layer — interactive REPL and rendering helpers.

Stdlib-only. The REPL turns the agent's deterministic engine (plan, critique,
generate, verify, memory, providers) into a conversational, diff-and-approve
coding session.
"""

from .diffview import render_unified_diff
from .repl import Repl

__all__ = ["render_unified_diff", "Repl"]
