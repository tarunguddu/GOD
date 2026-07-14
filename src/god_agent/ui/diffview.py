"""Colored unified-diff rendering (stdlib only).

Produces a readable, optionally ANSI-colored unified diff between two texts —
used by the REPL to preview a proposed change before it is written.
"""

from __future__ import annotations

import difflib

# ANSI colors
_GREEN = "\033[32m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def render_unified_diff(old: str, new: str, path: str = "", color: bool = True,
                        context: int = 3) -> str:
    """Return a unified diff of ``old`` -> ``new``.

    When ``color`` is True, additions are green, removals red, and hunk headers
    cyan. Returns a short '(no changes)' marker when the texts are identical.
    """
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    a_name = f"a/{path}" if path else "before"
    b_name = f"b/{path}" if path else "after"
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=a_name,
                                     tofile=b_name, n=context))
    if not diff:
        return "(no changes)"

    out: list[str] = []
    for line in diff:
        line = line.rstrip("\n")
        if not color:
            out.append(line)
            continue
        if line.startswith("+++") or line.startswith("---"):
            out.append(f"{_DIM}{line}{_RESET}")
        elif line.startswith("@@"):
            out.append(f"{_CYAN}{line}{_RESET}")
        elif line.startswith("+"):
            out.append(f"{_GREEN}{line}{_RESET}")
        elif line.startswith("-"):
            out.append(f"{_RED}{line}{_RESET}")
        else:
            out.append(line)
    return "\n".join(out)


def diff_stat(old: str, new: str) -> tuple[int, int]:
    """Return (added_lines, removed_lines) between two texts."""
    added = removed = 0
    for line in difflib.unified_diff(old.splitlines(), new.splitlines(), n=0):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed
