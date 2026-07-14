"""Sandboxed execution — run operations against an isolated copy, promote if good.

``SandboxManager`` copies the project's source files into a throwaway temp
directory (a filesystem *snapshot*), lets a command run there, diffs what
changed by content hash, and promotes selected changes back into the real
workspace *through the FileSystemTool* (so promotion is itself boundary-checked
and backed up).

NOTE ON ISOLATION: this is a filesystem snapshot, **not** an OS security
sandbox. ``run_command`` executes with the agent process's full privileges and
is guarded only by the SafetySystem command blocklist. Treat commands as
trusted; for running genuinely untrusted code, use OS-level isolation
(container / namespace / seccomp). The snapshot's value is protecting the real
working tree from accidental or failed changes, not containing hostile code.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_SOURCE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
               ".rb", ".c", ".cpp", ".h", ".hpp", ".cs", ".md", ".toml",
               ".yaml", ".yml", ".json", ".cfg", ".ini", ".txt"}
_IGNORE_DIRS = {".god", ".git", "__pycache__", ".venv", "venv", "build",
                "dist", ".pytest_cache", ".mypy_cache", "node_modules", "target"}


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@dataclass
class Sandbox:
    id: str
    path: Path
    source_root: Path
    manifest: dict[str, str] = field(default_factory=dict)  # rel -> sha256 at creation

    def file(self, rel: str) -> Path:
        return self.path / rel


@dataclass
class SandboxDiff:
    modified: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    @property
    def changed(self) -> list[str]:
        return sorted(self.modified + self.created + self.deleted)

    @property
    def empty(self) -> bool:
        return not (self.modified or self.created or self.deleted)


class SandboxManager:
    def __init__(self, agent) -> None:  # agent: GodAgent
        self.agent = agent
        self.root = agent.boundary.root

    # ---- lifecycle ---------------------------------------------------------
    def create(self, label: str = "") -> Sandbox:
        tmp = Path(tempfile.mkdtemp(prefix="god-sandbox-"))
        try:
            manifest: dict[str, str] = {}
            for src in self._iter_source(self.root):
                rel = str(src.relative_to(self.root))
                dest = tmp / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                manifest[rel] = _hash(src)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)  # don't leak the temp dir
            raise
        sandbox = Sandbox(id=tmp.name, path=tmp, source_root=self.root,
                          manifest=manifest)
        self.agent.safety.audit.record("sandbox.create", id=sandbox.id,
                                        label=label, files=len(manifest))
        return sandbox

    def destroy(self, sandbox: Sandbox) -> None:
        shutil.rmtree(sandbox.path, ignore_errors=True)
        self.agent.safety.audit.record("sandbox.destroy", id=sandbox.id)

    def _iter_source(self, root: Path):
        for p in root.rglob("*"):
            if p.is_symlink():          # never follow symlinks (escape / cycle risk)
                continue
            if not p.is_file():
                continue
            # Match ignore dirs against the path RELATIVE to root, so a workspace
            # that itself lives under e.g. a 'build' dir isn't wrongly skipped.
            rel_parts = p.relative_to(root).parts
            if any(part in _IGNORE_DIRS for part in rel_parts):
                continue
            if p.suffix.lower() in _SOURCE_EXT:
                yield p

    # ---- execution ---------------------------------------------------------
    def run_command(self, sandbox: Sandbox, command: str,
                    timeout: float = 300.0) -> subprocess.CompletedProcess:
        """Run a command inside the sandbox dir (screened by SafetySystem)."""
        blocked = self.agent.safety.is_command_blocked(command)
        if blocked:
            raise PermissionError(f"command blocked in sandbox: {blocked}")
        self.agent.safety.audit.record("sandbox.run", id=sandbox.id, command=command)
        return subprocess.run(
            command, cwd=str(sandbox.path),
            shell=True,  # god:allow shell-injection — screened by SafetySystem above
            capture_output=True, text=True, timeout=timeout,
        )

    # ---- diff & promote ----------------------------------------------------
    def diff(self, sandbox: Sandbox) -> SandboxDiff:
        diff = SandboxDiff()
        current: dict[str, str] = {}
        for src in self._iter_source(sandbox.path):
            rel = str(src.relative_to(sandbox.path))
            current[rel] = _hash(src)
        for rel, digest in current.items():
            if rel not in sandbox.manifest:
                diff.created.append(rel)
            elif sandbox.manifest[rel] != digest:
                diff.modified.append(rel)
        for rel in sandbox.manifest:
            if rel not in current:
                diff.deleted.append(rel)
        return diff

    def promote(self, sandbox: Sandbox, paths: list[str] | None = None,
                approved: bool = False) -> list[str]:
        """Copy changed sandbox files back into the real workspace via the
        FileSystemTool (boundary-checked + backed up). Deletions require
        ``approved`` like any destructive op."""
        diff = self.diff(sandbox)
        targets = paths if paths is not None else (diff.modified + diff.created)
        sandbox_root = sandbox.path.resolve()
        promoted: list[str] = []
        for rel in targets:
            # Defence-in-depth: reject paths that escape the sandbox snapshot
            # (absolute, '..', or symlinked out). The destination write is also
            # boundary-checked by FileSystemTool.
            sbx_file = (sandbox.path / rel)
            try:
                resolved = sbx_file.resolve()
                resolved.relative_to(sandbox_root)
            except (ValueError, OSError):
                continue
            if sbx_file.is_symlink():
                continue
            if sbx_file.exists():
                content = sbx_file.read_text(encoding="utf-8", errors="surrogateescape")
                self.agent.fs.write_file(rel, content)
                promoted.append(rel)
        if paths is None:
            for rel in diff.deleted:
                if self.agent.fs.exists(rel):
                    self.agent.fs.delete_file(rel, approved=approved)
                    promoted.append(rel)
        self.agent.safety.audit.record("sandbox.promote", id=sandbox.id,
                                        promoted=promoted)
        return promoted
