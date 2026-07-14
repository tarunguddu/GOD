"""Shell tool — bounded command execution.

Commands are screened by the SafetySystem first: hard-blocked patterns (rm -rf /,
force pushes, disk writes, fork bombs) are denied outright, and side-effecting
commands are flagged. Execution is confined to the workspace root by default and
is time-boxed so a runaway process cannot hang indefinitely.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..safety import Decision, SafetySystem
from ..workspace import WorkspaceBoundary


@dataclass
class ShellResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class ShellCommandDenied(PermissionError):
    pass


class ShellTool:
    name = "shell"

    def __init__(self, boundary: WorkspaceBoundary, safety: SafetySystem) -> None:
        self.boundary = boundary
        self.safety = safety

    def run(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float | None = 120.0,
        approved: bool = False,
    ) -> ShellResult:
        assessment = self.safety.assess_command(command)
        if assessment.decision == Decision.DENY:
            self.safety.audit.record("shell.denied", command=command,
                                     factors=assessment.factors)
            raise ShellCommandDenied(
                f"Command denied (critical risk): {assessment.factors}"
            )
        if assessment.needs_approval and not approved:
            raise ShellCommandDenied(
                f"Command requires approval (risk={assessment.level.value}: "
                f"{assessment.factors})."
            )

        work_dir = Path(self.boundary.check(cwd)) if cwd else self.boundary.root
        self.safety.audit.record("shell.run", command=command,
                                 cwd=str(work_dir), risk=assessment.level.value)
        try:
            proc = subprocess.run(
                command,
                cwd=str(work_dir),
                shell=True,  # god:allow shell-injection — commands are screened by SafetySystem first
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return ShellResult(command, proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            return ShellResult(
                command, returncode=124,
                stdout=exc.stdout or "" if isinstance(exc.stdout, str) else "",
                stderr=f"Timed out after {timeout}s",
                timed_out=True,
            )
