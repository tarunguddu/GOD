"""Safety & governance: risk assessment, audit logging, checkpoints, rollback.

Implements the "conscience" module from the blueprint with the mitigations the
realities doc calls for:
  - Tiered confirmation for destructive actions (not a single blanket prompt).
  - Default-on checkpoints/snapshots before mutations.
  - An append-only audit log of every consequential action.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .config import Config
from .workspace import WorkspaceBoundary


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Decision(str, Enum):
    ALLOW = "allow"
    ALLOW_WITH_CHECKPOINT = "allow_with_checkpoint"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass
class RiskAssessment:
    level: RiskLevel
    decision: Decision
    factors: list[str] = field(default_factory=list)

    @property
    def needs_approval(self) -> bool:
        return self.decision in (Decision.REQUIRE_APPROVAL, Decision.DENY)


class AuditLog:
    """Append-only JSON-lines audit log."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, **fields: object) -> None:
        entry = {"ts": time.time(), "event": event, **fields}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

    def tail(self, n: int = 20) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-n:] if line.strip()]


@dataclass
class Checkpoint:
    """Snapshot of a set of files, restorable on demand."""

    id: str
    label: str
    created: float
    storage: Path
    originals: dict[str, str]  # relative_path -> absolute original path


class SafetySystem:
    """Risk gating + checkpoint/rollback over a workspace boundary."""

    def __init__(self, config: Config, boundary: WorkspaceBoundary) -> None:
        self.config = config
        self.boundary = boundary
        self.audit = AuditLog(config.audit_path)
        self._blocked = [re.compile(p, re.IGNORECASE) for p in config.blocked_command_patterns]

    # ---- command screening -------------------------------------------------
    def is_command_blocked(self, command: str) -> str | None:
        """Return the matched pattern if the command is hard-blocked, else None."""
        for pattern in self._blocked:
            if pattern.search(command):
                return pattern.pattern
        return None

    def assess_command(self, command: str) -> RiskAssessment:
        blocked = self.is_command_blocked(command)
        if blocked:
            return RiskAssessment(
                RiskLevel.CRITICAL, Decision.DENY,
                [f"matches blocked pattern: {blocked}"],
            )
        factors: list[str] = []
        lowered = command.lower()
        side_effects = ("install", "publish", "deploy", "push", "delete", "del ",
                        "remove-item", "rm ", "drop ", "curl", "wget", "invoke-webrequest")
        if any(tok in lowered for tok in side_effects):
            factors.append("command has side effects")
        if not factors:
            return RiskAssessment(RiskLevel.LOW, Decision.ALLOW)
        return RiskAssessment(RiskLevel.MEDIUM, Decision.ALLOW_WITH_CHECKPOINT, factors)

    def assess_file_change(self, paths: list[str], deleting: bool = False) -> RiskAssessment:
        factors: list[str] = []
        level = RiskLevel.LOW
        if deleting:
            factors.append("deletes files")
            level = RiskLevel.HIGH
        if len(paths) > self.config.max_files_per_action:
            factors.append(f"affects {len(paths)} files (wide impact)")
            level = RiskLevel.HIGH
        critical_names = {"pyproject.toml", "package.json", ".env", "dockerfile",
                          "requirements.txt", "go.mod", "cargo.toml"}
        for p in paths:
            if Path(p).name.lower() in critical_names:
                factors.append(f"modifies critical file: {Path(p).name}")
                level = max(level, RiskLevel.MEDIUM, key=_risk_order)
        if level == RiskLevel.LOW:
            return RiskAssessment(level, Decision.ALLOW)
        if level == RiskLevel.MEDIUM:
            return RiskAssessment(level, Decision.ALLOW_WITH_CHECKPOINT, factors)
        decision = Decision.REQUIRE_APPROVAL if self.config.confirm_destructive else Decision.ALLOW_WITH_CHECKPOINT
        return RiskAssessment(level, decision, factors)

    # ---- checkpoints -------------------------------------------------------
    def create_checkpoint(self, paths: list[str], label: str = "") -> Checkpoint:
        """Snapshot the current contents of ``paths`` into checkpoint storage."""
        cid = uuid.uuid4().hex[:12]
        storage = self.config.checkpoint_path / cid
        storage.mkdir(parents=True, exist_ok=True)
        originals: dict[str, str] = {}
        for raw in paths:
            resolved = self.boundary.check(raw)
            rel = self.boundary.relative(resolved)
            if Path(resolved).exists():
                dest = storage / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(resolved, dest)
            originals[rel] = str(resolved)
        cp = Checkpoint(id=cid, label=label, created=time.time(),
                        storage=storage, originals=originals)
        self._write_manifest(cp)
        self.audit.record("checkpoint.create", id=cid, label=label, files=list(originals))
        return cp

    def _write_manifest(self, cp: Checkpoint) -> None:
        manifest = {
            "id": cp.id, "label": cp.label, "created": cp.created,
            "originals": cp.originals,
        }
        (cp.storage / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    def rollback(self, cp: Checkpoint) -> list[str]:
        """Restore files captured by ``cp``. Returns list of restored paths."""
        restored: list[str] = []
        for rel, original in cp.originals.items():
            snap = cp.storage / rel
            target = Path(original)
            if snap.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snap, target)
                restored.append(original)
            elif target.exists():
                # File did not exist at checkpoint time -> it was created since.
                target.unlink()
                restored.append(original)
        self.audit.record("checkpoint.rollback", id=cp.id, restored=restored)
        return restored


def _risk_order(level: RiskLevel) -> int:
    return [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL].index(level)
