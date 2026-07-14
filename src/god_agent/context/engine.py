"""Context engine — project understanding and relevance retrieval.

Detects the tech stack and conventions, builds a code graph, and offers a
lightweight, dependency-free relevance search over files (token-overlap scoring).
This is the "good enough offline" stand-in for a vector index; the interface is
designed so a real embedding backend can be slotted in later without changing
callers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .code_graph import CodeGraph


# marker file -> (stack label, default test command, default build command)
STACK_MARKERS: dict[str, tuple[str, str | None, str | None]] = {
    "pyproject.toml": ("python", "pytest", None),
    "setup.py": ("python", "pytest", None),
    "requirements.txt": ("python", "pytest", None),
    "package.json": ("node", "npm test", "npm run build"),
    "go.mod": ("go", "go test ./...", "go build ./..."),
    "Cargo.toml": ("rust", "cargo test", "cargo build"),
    "pom.xml": ("java/maven", "mvn test", "mvn package"),
}

_SOURCE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
               ".rb", ".c", ".cpp", ".h", ".hpp", ".cs", ".md", ".toml", ".yaml", ".yml"}

_IGNORE_DIRS = {".god", ".git", "__pycache__", "node_modules", ".venv", "venv",
                "dist", "build", ".pytest_cache", ".mypy_cache", "target"}

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")


@dataclass
class ProjectContext:
    root: str
    stacks: list[str] = field(default_factory=list)
    test_command: str | None = None
    build_command: str | None = None
    file_count: int = 0
    graph_stats: dict[str, int] = field(default_factory=dict)


@dataclass
class SearchHit:
    path: str
    score: float
    preview: str


class ContextEngine:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.graph = CodeGraph()
        self._files: list[Path] = []

    def _iter_source_files(self):
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _IGNORE_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in _SOURCE_EXT:
                yield path

    def build(self) -> ProjectContext:
        self._files = list(self._iter_source_files())
        self.graph.build(self.root)
        stacks, test_cmd, build_cmd = self._detect_stack()
        return ProjectContext(
            root=str(self.root),
            stacks=stacks,
            test_command=test_cmd,
            build_command=build_cmd,
            file_count=len(self._files),
            graph_stats=self.graph.stats(),
        )

    def _detect_stack(self) -> tuple[list[str], str | None, str | None]:
        stacks: list[str] = []
        test_cmd: str | None = None
        build_cmd: str | None = None
        for marker, (label, t, b) in STACK_MARKERS.items():
            if (self.root / marker).exists():
                if label not in stacks:
                    stacks.append(label)
                test_cmd = test_cmd or t
                build_cmd = build_cmd or b
        return stacks, test_cmd, build_cmd

    def search(self, query: str, top_k: int = 8) -> list[SearchHit]:
        """Token-overlap relevance search over indexed files."""
        if not self._files:
            self._files = list(self._iter_source_files())
        q_tokens = {t.lower() for t in _TOKEN_RE.findall(query)}
        if not q_tokens:
            return []
        hits: list[SearchHit] = []
        for path in self._files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            f_tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
            if not f_tokens:
                continue
            f_set = set(f_tokens)
            overlap = q_tokens & f_set
            if not overlap:
                continue
            # score: overlap weighted by frequency, normalised by file size
            freq = sum(f_tokens.count(tok) for tok in overlap)
            score = len(overlap) + freq / (len(f_tokens) ** 0.5)
            preview = self._preview(text, overlap)
            hits.append(SearchHit(
                path=str(path.relative_to(self.root)),
                score=round(score, 3),
                preview=preview,
            ))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    @staticmethod
    def _preview(text: str, tokens: set[str]) -> str:
        for line in text.splitlines():
            low = line.lower()
            if any(tok in low for tok in tokens):
                return line.strip()[:120]
        return ""
