"""Filesystem tool with boundary enforcement, backups, and surgical edits.

Every mutation:
  - is checked against the workspace boundary (deterministic),
  - creates a timestamped backup of the prior contents (reversible),
  - is recorded in the audit log.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from ..safety import SafetySystem
from ..workspace import WorkspaceBoundary


@dataclass
class WriteResult:
    path: str
    created: bool
    bytes_written: int
    backup: str | None


@dataclass
class EditResult:
    path: str
    replacements: int
    backup: str | None


class FileSystemTool:
    name = "filesystem"

    def __init__(self, boundary: WorkspaceBoundary, safety: SafetySystem) -> None:
        self.boundary = boundary
        self.safety = safety

    # ---- reads -------------------------------------------------------------
    def read_file(self, path: str, encoding: str = "utf-8") -> str:
        resolved = self.boundary.check(path)
        return Path(resolved).read_text(encoding=encoding)

    def exists(self, path: str) -> bool:
        try:
            return Path(self.boundary.check(path)).exists()
        except Exception:
            return False

    def list_dir(self, path: str = ".") -> list[str]:
        resolved = self.boundary.check(path)
        return sorted(p.name for p in Path(resolved).iterdir())

    def tree(self, path: str = ".", depth: int = 3, _prefix: str = "") -> str:
        resolved = Path(self.boundary.check(path))
        lines: list[str] = []
        self._tree(resolved, depth, "", lines)
        return "\n".join(lines)

    def _tree(self, root: Path, depth: int, prefix: str, lines: list[str]) -> None:
        if depth < 0 or not root.is_dir():
            return
        entries = sorted(
            [e for e in root.iterdir() if not e.name.startswith(".god")],
            key=lambda e: (e.is_file(), e.name),
        )
        for i, entry in enumerate(entries):
            last = i == len(entries) - 1
            connector = "└── " if last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
            if entry.is_dir() and depth > 0:
                extension = "    " if last else "│   "
                self._tree(entry, depth - 1, prefix + extension, lines)

    # ---- writes ------------------------------------------------------------
    def _backup(self, resolved: Path) -> str | None:
        if not resolved.exists():
            return None
        rel = self.boundary.relative(resolved)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = self.safety.config.backup_path / f"{rel}.{stamp}.bak"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved, dest)
        return str(dest)

    def write_file(self, path: str, content: str, encoding: str = "utf-8") -> WriteResult:
        resolved = Path(self.boundary.check(path))
        assessment = self.safety.assess_file_change([str(resolved)])
        self.safety.audit.record(
            "fs.write", path=self.boundary.relative(resolved),
            risk=assessment.level.value, decision=assessment.decision.value,
        )
        existed = resolved.exists()
        backup = self._backup(resolved)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode(encoding)
        resolved.write_bytes(data)
        return WriteResult(
            path=self.boundary.relative(resolved),
            created=not existed,
            bytes_written=len(data),
            backup=backup,
        )

    def edit_file(self, path: str, old: str, new: str, count: int = -1,
                  encoding: str = "utf-8") -> EditResult:
        """Replace ``old`` with ``new`` in a file.

        Requires ``old`` to be present; raises ``ValueError`` otherwise so the
        agent can never silently no-op an edit (a source of false "done" claims).
        """
        resolved = Path(self.boundary.check(path))
        if not resolved.exists():
            raise FileNotFoundError(self.boundary.relative(resolved))
        text = resolved.read_text(encoding=encoding)
        occurrences = text.count(old)
        if occurrences == 0:
            raise ValueError(
                f"Edit target not found in {self.boundary.relative(resolved)}: "
                f"{old[:60]!r}"
            )
        backup = self._backup(resolved)
        replaced = text.replace(old, new) if count < 0 else text.replace(old, new, count)
        actual = occurrences if count < 0 else min(count, occurrences)
        resolved.write_text(replaced, encoding=encoding)
        self.safety.audit.record(
            "fs.edit", path=self.boundary.relative(resolved), replacements=actual,
        )
        return EditResult(
            path=self.boundary.relative(resolved),
            replacements=actual,
            backup=backup,
        )

    def delete_file(self, path: str, approved: bool = False) -> bool:
        """Delete a file. Refuses unless ``approved`` for destructive intent."""
        resolved = Path(self.boundary.check(path))
        assessment = self.safety.assess_file_change([str(resolved)], deleting=True)
        if assessment.needs_approval and not approved:
            raise PermissionError(
                f"Refusing to delete {self.boundary.relative(resolved)} without "
                f"approval (risk={assessment.level.value}: {assessment.factors})."
            )
        self._backup(resolved)
        if resolved.exists():
            resolved.unlink()
            self.safety.audit.record("fs.delete", path=self.boundary.relative(resolved))
            return True
        return False
