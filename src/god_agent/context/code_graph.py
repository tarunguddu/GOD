"""AST-based code graph for Python sources.

Provides the semantic, structure-aware understanding the realities doc calls out
as missing in text-search-only agents. Built on the stdlib ``ast`` module (no
third-party dependency), it indexes symbols (functions, classes, methods) and
import-based relationships, and supports impact analysis: "what depends on this?"
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SymbolNode:
    name: str
    qualified_name: str
    kind: str            # "function" | "class" | "method"
    file: str
    line: int
    end_line: int
    signature: str
    docstring: str | None
    calls: set[str] = field(default_factory=set)
    complexity: int = 1


@dataclass
class ImportEdge:
    source_file: str
    module: str
    names: tuple[str, ...]


class CodeGraph:
    """Queryable graph of symbols and imports across a Python project."""

    def __init__(self) -> None:
        self.nodes: dict[str, SymbolNode] = {}
        self.imports: list[ImportEdge] = []
        # module path (dotted) -> file
        self._module_index: dict[str, str] = {}

    # ---- building ----------------------------------------------------------
    def build(self, root: str | Path, ignore: tuple[str, ...] = (".god", ".git",
              "__pycache__", "node_modules", ".venv", "venv")) -> "CodeGraph":
        root = Path(root)
        for path in root.rglob("*.py"):
            if any(part in ignore for part in path.parts):
                continue
            try:
                self.add_file(path, root)
            except (SyntaxError, UnicodeDecodeError):
                continue
        return self

    def add_file(self, path: str | Path, root: str | Path | None = None) -> None:
        path = Path(path)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        rel = str(path.relative_to(root)) if root else str(path)
        module_dotted = rel.replace("\\", "/").removesuffix(".py").replace("/", ".")
        self._module_index[module_dotted] = rel

        for node in ast.iter_child_nodes(tree):
            self._visit(node, rel, prefix="")

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.imports.append(ImportEdge(rel, alias.name, ()))
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = tuple(a.name for a in node.names)
                self.imports.append(ImportEdge(rel, node.module, names))

    def _visit(self, node: ast.AST, file: str, prefix: str) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qn = f"{prefix}{node.name}" if not prefix else f"{prefix}.{node.name}"
            kind = "method" if prefix else "function"
            self.nodes[f"{file}::{qn}"] = SymbolNode(
                name=node.name,
                qualified_name=qn,
                kind=kind,
                file=file,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                signature=self._signature(node),
                docstring=ast.get_docstring(node),
                calls=self._extract_calls(node),
                complexity=self._complexity(node),
            )
        elif isinstance(node, ast.ClassDef):
            qn = f"{prefix}{node.name}" if not prefix else f"{prefix}.{node.name}"
            self.nodes[f"{file}::{qn}"] = SymbolNode(
                name=node.name,
                qualified_name=qn,
                kind="class",
                file=file,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                signature=f"class {node.name}",
                docstring=ast.get_docstring(node),
            )
            for child in node.body:
                self._visit(child, file, prefix=qn)

    @staticmethod
    def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        args = [a.arg for a in node.args.args]
        if node.args.vararg:
            args.append("*" + node.args.vararg.arg)
        if node.args.kwarg:
            args.append("**" + node.args.kwarg.arg)
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(args)})"

    @staticmethod
    def _extract_calls(node: ast.AST) -> set[str]:
        calls: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Name):
                    calls.add(func.id)
                elif isinstance(func, ast.Attribute):
                    calls.add(func.attr)
        return calls

    @staticmethod
    def _complexity(node: ast.AST) -> int:
        """Approximate cyclomatic complexity by counting branch points."""
        score = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.And, ast.Or,
                                  ast.ExceptHandler, ast.With, ast.AsyncFor,
                                  ast.AsyncWith)):
                score += 1
            elif isinstance(child, ast.BoolOp):
                score += len(child.values) - 1
        return score

    # ---- queries -----------------------------------------------------------
    def find(self, name: str) -> list[SymbolNode]:
        return [n for n in self.nodes.values()
                if n.name == name or n.qualified_name == name]

    def callers_of(self, name: str) -> list[SymbolNode]:
        """Symbols whose body calls ``name`` (best-effort, name-based)."""
        return [n for n in self.nodes.values() if name in n.calls]

    def impact_of(self, name: str) -> dict[str, list[str]]:
        """Best-effort impact analysis: direct callers + files importing it."""
        callers = [n.qualified_name for n in self.callers_of(name)]
        importing_files = [
            e.source_file for e in self.imports if name in e.names or e.module.endswith(name)
        ]
        return {"direct_callers": sorted(set(callers)),
                "importing_files": sorted(set(importing_files))}

    def hotspots(self, top: int = 5) -> list[SymbolNode]:
        """Highest-complexity symbols — candidates for refactor/extra tests."""
        funcs = [n for n in self.nodes.values() if n.kind != "class"]
        return sorted(funcs, key=lambda n: n.complexity, reverse=True)[:top]

    def stats(self) -> dict[str, int]:
        kinds = {"function": 0, "class": 0, "method": 0}
        for n in self.nodes.values():
            kinds[n.kind] = kinds.get(n.kind, 0) + 1
        return {
            "files": len(self._module_index),
            "symbols": len(self.nodes),
            "imports": len(self.imports),
            **kinds,
        }
