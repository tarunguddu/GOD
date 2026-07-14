"""Self-verification.

The single most damaging failure mode documented for coding agents is the
confident "it's done / tests pass" claim that isn't true. This module makes
verification a first-class, executed step: it actually runs the test/build
command, parses the real output, and returns a structured, non-negotiable
verdict. A "done" claim is only ever derived from a real, parsed result here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .tools.shell import ShellTool


@dataclass
class VerificationResult:
    command: str
    passed: bool
    returncode: int
    summary: str
    passed_count: int | None = None
    failed_count: int | None = None
    timed_out: bool = False
    raw_tail: str = ""
    notes: list[str] = field(default_factory=list)

    def as_claim(self) -> str:
        if self.timed_out:
            return f"UNVERIFIED — verification command timed out: {self.command!r}"
        status = "VERIFIED PASS" if self.passed else "VERIFIED FAIL"
        return f"{status} via {self.command!r}: {self.summary}"


# Covers pytest ("5 passed", "2 failed, 5 passed", "1 error") and
# jest/vitest ("Tests:  2 failed, 5 passed, 7 total"). A single regex avoids
# double-counting the same token across multiple patterns.
_COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped)")


class Verifier:
    """Runs and interprets verification commands."""

    def __init__(self, shell: ShellTool) -> None:
        self.shell = shell

    def run(self, command: str, timeout: float = 600.0) -> VerificationResult:
        result = self.shell.run(command, timeout=timeout, approved=True)
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        tail = "\n".join(combined.splitlines()[-25:])

        passed_count, failed_count = self._parse_counts(combined)
        notes: list[str] = []

        # Detect a classic dishonest pattern: tests "passing" only because they
        # were skipped wholesale.
        if passed_count == 0 and "skipped" in combined.lower() and result.ok:
            notes.append("WARNING: 0 tests passed but skips present — possible "
                         "vacuous green. Treating as not verified.")
            return VerificationResult(
                command=command, passed=False, returncode=result.returncode,
                summary="no tests actually passed (only skips)",
                passed_count=passed_count, failed_count=failed_count,
                timed_out=result.timed_out, raw_tail=tail, notes=notes,
            )

        passed = result.ok and (failed_count in (0, None))
        if result.timed_out:
            summary = "timed out"
        elif failed_count:
            summary = f"{failed_count} failing"
        elif passed_count:
            summary = f"{passed_count} passing"
        elif result.ok:
            summary = "command succeeded (no test counts parsed)"
        else:
            summary = f"exit code {result.returncode}"

        return VerificationResult(
            command=command, passed=passed, returncode=result.returncode,
            summary=summary, passed_count=passed_count, failed_count=failed_count,
            timed_out=result.timed_out, raw_tail=tail, notes=notes,
        )

    @staticmethod
    def _parse_counts(text: str) -> tuple[int | None, int | None]:
        passed = failed = None
        for num, kind in _COUNT_RE.findall(text):
            n = int(num)
            if kind.startswith("pass"):
                passed = (passed or 0) + n
            elif kind.startswith("fail") or kind.startswith("error"):
                failed = (failed or 0) + n
        return passed, failed
