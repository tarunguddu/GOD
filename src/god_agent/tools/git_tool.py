"""Git tool — status, diff, and deterministic commit-message generation.

The commit-message generator does NOT call an LLM: it derives a conventional-
commit style message from the actual staged diff. This keeps a useful capability
working offline and avoids the "confident but wrong" summaries an LLM can produce
about changes it did not actually inspect.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..workspace import WorkspaceBoundary


@dataclass
class FileStatus:
    path: str
    index: str   # staged status char
    work: str    # working-tree status char


class GitTool:
    name = "git"

    def __init__(self, boundary: WorkspaceBoundary) -> None:
        self.boundary = boundary
        self.root = boundary.root

    def _git(self, *args: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def is_repo(self) -> bool:
        return self._git("rev-parse", "--is-inside-work-tree").returncode == 0

    def current_branch(self) -> str | None:
        proc = self._git("rev-parse", "--abbrev-ref", "HEAD")
        return proc.stdout.strip() if proc.returncode == 0 else None

    def status(self) -> list[FileStatus]:
        proc = self._git("status", "--porcelain=v1")
        if proc.returncode != 0:
            return []
        out: list[FileStatus] = []
        for line in proc.stdout.splitlines():
            if len(line) < 3:
                continue
            out.append(FileStatus(path=line[3:].strip(), index=line[0], work=line[1]))
        return out

    def diff(self, staged: bool = False) -> str:
        args = ["diff"]
        if staged:
            args.append("--cached")
        return self._git(*args).stdout

    def stage(self, paths: list[str]) -> bool:
        safe = [self.boundary.relative(self.boundary.check(p)) for p in paths]
        return self._git("add", "--", *safe).returncode == 0

    # ---- commit message synthesis -----------------------------------------
    def generate_commit_message(self) -> str:
        """Build a conventional-commit message from the staged diff."""
        statuses = [s for s in self.status() if s.index not in (" ", "?")]
        if not statuses:
            return "chore: no staged changes"

        added = [s.path for s in statuses if s.index == "A"]
        modified = [s.path for s in statuses if s.index == "M"]
        deleted = [s.path for s in statuses if s.index == "D"]
        renamed = [s.path for s in statuses if s.index == "R"]

        kind = "feat" if added and not modified and not deleted else "chore"
        if deleted and not added:
            kind = "refactor"
        if modified and not added and not deleted:
            kind = "fix" if self._looks_like_fix() else "chore"

        scope = self._infer_scope([s.path for s in statuses])
        header_scope = f"({scope})" if scope else ""

        n = len(statuses)
        summary = self._summarize(added, modified, deleted, renamed)
        header = f"{kind}{header_scope}: {summary}"

        body_lines = []
        for label, items in (("added", added), ("modified", modified),
                             ("deleted", deleted), ("renamed", renamed)):
            for item in items:
                body_lines.append(f"- {label}: {item}")
        body = "\n".join(body_lines)
        return f"{header}\n\n{body}" if body else header

    def _looks_like_fix(self) -> bool:
        diff = self.diff(staged=True).lower()
        return any(tok in diff for tok in ("fix", "bug", "error", "exception", "patch"))

    @staticmethod
    def _infer_scope(paths: list[str]) -> str | None:
        tops = {Path(p).parts[0] for p in paths if Path(p).parts}
        if len(tops) == 1:
            top = next(iter(tops))
            return top if top not in (".", "") else None
        return None

    @staticmethod
    def _summarize(added, modified, deleted, renamed) -> str:
        parts = []
        if added:
            parts.append(f"add {len(added)} file(s)")
        if modified:
            parts.append(f"update {len(modified)} file(s)")
        if deleted:
            parts.append(f"remove {len(deleted)} file(s)")
        if renamed:
            parts.append(f"rename {len(renamed)} file(s)")
        return ", ".join(parts) or "update repository"

    def commit(self, message: str | None = None) -> tuple[bool, str]:
        msg = message or self.generate_commit_message()
        proc = self._git("commit", "-m", msg)
        return proc.returncode == 0, (proc.stdout + proc.stderr).strip()

    def find_who_knows(self, file: str, top: int = 5) -> list[tuple[str, int]]:
        """Return [(author, commit_count)] for a file, most active first.

        A deterministic 'who has expertise here' signal from git history; useful
        for routing reviews/questions on a team. Returns [] outside a repo or for
        an untracked file.
        """
        rel = self.boundary.relative(self.boundary.check(file))
        proc = self._git("log", "--follow", "--format=%an", "--", rel)
        if proc.returncode != 0 or not proc.stdout.strip():
            return []
        counts: dict[str, int] = {}
        for author in proc.stdout.splitlines():
            author = author.strip()
            if author:
                counts[author] = counts.get(author, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:top]
