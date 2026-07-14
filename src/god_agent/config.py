"""Runtime configuration for the GOD agent.

Configuration is layered:
  1. Built-in defaults (this file).
  2. ``god_agent.toml`` discovered at the project root (optional).
  3. Explicit overrides passed in code / CLI flags.

Kept dependency-free: uses the stdlib ``tomllib`` (Python 3.11+).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    tomllib = None  # type: ignore[assignment]


# Commands that are never run automatically without an explicit confirmation,
# regardless of risk scoring. These are intentionally conservative.
DEFAULT_BLOCKED_COMMAND_PATTERNS: tuple[str, ...] = (
    r"\brm\s+-rf\s+/",          # rm -rf /  (and / prefixed absolute roots)
    r"\bmkfs\b",                # format a filesystem
    r"\bdd\s+if=",              # raw disk writes
    r":\(\)\s*\{",              # fork bomb
    r"\bgit\s+push\s+.*--force", # force push
    r"\bgit\s+reset\s+--hard",  # destructive reset
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bformat\b",              # windows format
    r"\bRemove-Item\b.*-Recurse.*-Force.*[\\/]\s*$",
)


@dataclass(frozen=True)
class Config:
    """Immutable runtime configuration."""

    project_root: Path
    backup_dir: str = ".god/backups"
    checkpoint_dir: str = ".god/checkpoints"
    audit_log: str = ".god/audit.log"

    # Safety
    confirm_destructive: bool = True
    max_files_per_action: int = 25
    blocked_command_patterns: tuple[str, ...] = DEFAULT_BLOCKED_COMMAND_PATTERNS

    # LLM
    llm_provider: str = "mock"          # any registry preset, "custom", or "mock"
    llm_model: str | None = None        # None => preset default
    llm_api_key_env: str | None = None  # None => preset's key env
    llm_base_url: str | None = None     # override / custom or local endpoint
    llm_fast_model: str = "claude-haiku"
    llm_powerful_model: str = "claude-sonnet-4"
    llm_extra_headers: dict[str, str] = field(default_factory=dict)

    # Verification
    test_command: str | None = None      # auto-detected if None
    build_command: str | None = None

    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def backup_path(self) -> Path:
        return self.project_root / self.backup_dir

    @property
    def checkpoint_path(self) -> Path:
        return self.project_root / self.checkpoint_dir

    @property
    def audit_path(self) -> Path:
        return self.project_root / self.audit_log

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, project_root: str | os.PathLike[str], **overrides: Any) -> "Config":
        """Load configuration for ``project_root`` applying file + overrides."""
        root = Path(project_root).resolve()
        cfg = cls(project_root=root)

        toml_path = root / "god_agent.toml"
        if toml_path.exists() and tomllib is not None:
            with toml_path.open("rb") as fh:
                data = tomllib.load(fh)
            section = data.get("god-agent", data)
            cfg = cfg._apply_dict(section)

        if overrides:
            cfg = cfg._apply_dict(overrides)
        return cfg

    def _apply_dict(self, data: dict[str, Any]) -> "Config":
        known = {f for f in self.__dataclass_fields__ if f != "project_root"}
        changes: dict[str, Any] = {}
        extra = dict(self.extra)
        for key, value in data.items():
            if key in known:
                if key == "blocked_command_patterns":
                    value = tuple(value)
                changes[key] = value
            else:
                extra[key] = value
        changes["extra"] = extra
        return replace(self, **changes)
