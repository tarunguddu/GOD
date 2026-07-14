"""Workspace boundary enforcement.

This addresses one of the most damaging real-world failure modes of coding
agents: they run with the full filesystem permissions of the launching user, so
an instruction like "clean up this directory" can reach and delete anything the
user can access.

``WorkspaceBoundary`` is a *deterministic* gate. Every path the agent intends to
touch is resolved (symlinks included) and checked against the declared project
root. Anything outside requires an explicit, separately-granted allow path.
There is no prose instruction involved — it cannot be "forgotten" by a model.
"""

from __future__ import annotations

import os
from pathlib import Path


class BoundaryViolation(PermissionError):
    """Raised when a path falls outside the permitted workspace."""


class WorkspaceBoundary:
    """Confines filesystem access to an explicit set of roots."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        extra_allowed: list[str | os.PathLike[str]] | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        if not self.root.exists():
            raise FileNotFoundError(f"Workspace root does not exist: {self.root}")
        self._allowed: list[Path] = [self.root]
        for p in extra_allowed or []:
            self.grant(p)

    def grant(self, path: str | os.PathLike[str]) -> Path:
        """Explicitly allow access to an additional path (and its subtree)."""
        resolved = Path(path).resolve()
        if resolved not in self._allowed:
            self._allowed.append(resolved)
        return resolved

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        return tuple(self._allowed)

    # ------------------------------------------------------------------
    def _resolve_candidate(self, path: str | os.PathLike[str]) -> Path:
        """Resolve a path even if it does not yet exist.

        We resolve the nearest existing ancestor so that symlink escapes in the
        existing portion of the path are caught, while still permitting creation
        of new files/dirs inside the boundary.
        """
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        # Resolve existing ancestor strictly, then re-append the missing tail.
        existing = p
        tail: list[str] = []
        while not existing.exists():
            tail.append(existing.name)
            parent = existing.parent
            if parent == existing:  # reached filesystem root
                break
            existing = parent
        resolved_existing = existing.resolve()
        for part in reversed(tail):
            resolved_existing = resolved_existing / part
        return resolved_existing

    def is_within(self, path: str | os.PathLike[str]) -> bool:
        resolved = self._resolve_candidate(path)
        for allowed in self._allowed:
            try:
                resolved.relative_to(allowed)
                return True
            except ValueError:
                continue
        return False

    def check(self, path: str | os.PathLike[str]) -> Path:
        """Return the resolved path if permitted, else raise ``BoundaryViolation``."""
        resolved = self._resolve_candidate(path)
        if not self.is_within(resolved):
            raise BoundaryViolation(
                f"Path '{resolved}' is outside the workspace boundary. "
                f"Allowed roots: {[str(p) for p in self._allowed]}. "
                f"Grant access explicitly if this is intended."
            )
        return resolved

    def relative(self, path: str | os.PathLike[str]) -> str:
        """Return ``path`` relative to the project root for display."""
        resolved = self._resolve_candidate(path)
        try:
            return str(resolved.relative_to(self.root))
        except ValueError:
            return str(resolved)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"WorkspaceBoundary(root={self.root!r}, allowed={len(self._allowed)})"
