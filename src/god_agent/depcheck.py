"""Dependency safety checks — guarding against hallucinated / "slopsquatted" deps.

Models fabricate plausible-but-nonexistent package names in a meaningful share
of outputs, and attackers register those names on public registries. Before any
agent-introduced dependency is installed, it is screened here:
  - verified against the public registry (PyPI / npm),
  - checked for typosquatting similarity to popular packages,
  - newly-introduced deps in a diff are flagged for human review.

Network checks are optional and fail safe: if the registry can't be reached, the
package is reported UNVERIFIED rather than silently trusted.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher


# A small set of very popular packages used for typosquat proximity checks.
POPULAR_PYPI = {
    "requests", "numpy", "pandas", "flask", "django", "pytest", "setuptools",
    "urllib3", "boto3", "click", "pydantic", "sqlalchemy", "scipy", "pillow",
    "matplotlib", "fastapi", "rich", "tqdm", "pyyaml", "anthropic", "openai",
}
POPULAR_NPM = {
    "react", "express", "lodash", "axios", "chalk", "commander", "next",
    "typescript", "webpack", "vite", "eslint", "jest", "vitest", "zod",
}


@dataclass
class DepVerdict:
    name: str
    ecosystem: str
    exists: bool | None          # None == could not verify (network/etc.)
    typosquat_of: str | None
    risk: str                    # "ok" | "review" | "danger" | "unverified"
    detail: str


class DependencyChecker:
    def __init__(self, online: bool = True, timeout: float = 6.0) -> None:
        self.online = online
        self.timeout = timeout

    # ---- public ------------------------------------------------------------
    def check(self, name: str, ecosystem: str = "pypi") -> DepVerdict:
        popular = POPULAR_PYPI if ecosystem == "pypi" else POPULAR_NPM
        squat = self._closest(name, popular)

        exists: bool | None = None
        if self.online:
            exists = self._exists(name, ecosystem)

        if squat and squat != name:
            return DepVerdict(
                name, ecosystem, exists, squat, "danger",
                f"Name is suspiciously close to popular package '{squat}'. "
                f"Possible typosquat — verify manually.",
            )
        if exists is False:
            return DepVerdict(
                name, ecosystem, exists, None, "danger",
                "Package not found on registry — likely hallucinated. Do not install.",
            )
        if exists is None:
            return DepVerdict(
                name, ecosystem, exists, None, "unverified",
                "Could not reach registry; treat as unverified and confirm manually.",
            )
        return DepVerdict(name, ecosystem, exists, None, "ok",
                          "Found on registry; no typosquat proximity flagged.")

    def check_many(self, names: list[str], ecosystem: str = "pypi") -> list[DepVerdict]:
        return [self.check(n, ecosystem) for n in names]

    # ---- internals ---------------------------------------------------------
    @staticmethod
    def _closest(name: str, popular: set[str]) -> str | None:
        best, best_ratio = None, 0.0
        low = name.lower()
        for pkg in popular:
            if low == pkg:
                return None  # exact match of a popular package is fine
            ratio = SequenceMatcher(None, low, pkg).ratio()
            if ratio > best_ratio:
                best, best_ratio = pkg, ratio
        # high similarity but not identical => suspicious
        return best if best_ratio >= 0.82 else None

    def _exists(self, name: str, ecosystem: str) -> bool | None:
        if ecosystem == "pypi":
            url = f"https://pypi.org/pypi/{name}/json"
        elif ecosystem == "npm":
            url = f"https://registry.npmjs.org/{name}"
        else:
            return None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "god-agent-depcheck"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    resp.read(1)  # touch the body
                    return True
                return False
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            return None
        except (urllib.error.URLError, TimeoutError, OSError):
            return None
        except json.JSONDecodeError:
            return None
