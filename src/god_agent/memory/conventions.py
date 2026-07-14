"""Convention detection — learning the project's house style, deterministically.

Infers conventions directly from the source (no model needed): indentation,
preferred string quote, function/class naming, type-hint coverage, and docstring
coverage. The result is a compact :class:`Conventions` value that feeds the
generation prompt so produced code matches the existing codebase.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import Counter
from dataclasses import dataclass, field
from math import gcd
from pathlib import Path

_SNAKE = re.compile(r"^[a-z_][a-z0-9_]*$")
_PASCAL = re.compile(r"^[A-Z][A-Za-z0-9]*$")

_IGNORE_DIRS = {".god", ".git", "__pycache__", ".venv", "venv", "build", "dist"}


@dataclass
class Conventions:
    indent: str = "4 spaces"
    quote_style: str = "double"            # "single" | "double" | "mixed"
    function_naming: str = "snake_case"    # snake_case | camelCase | mixed
    class_naming: str = "PascalCase"
    type_hint_coverage: float = 0.0        # 0..1 of functions with return/arg hints
    docstring_coverage: float = 0.0        # 0..1 of functions+classes with docstrings
    sample_size: int = 0

    def render(self) -> str:
        return (
            f"- indentation: {self.indent}\n"
            f"- string quotes: prefer {self.quote_style}\n"
            f"- function names: {self.function_naming}\n"
            f"- class names: {self.class_naming}\n"
            f"- type hints: used in {self.type_hint_coverage:.0%} of functions\n"
            f"- docstrings: present on {self.docstring_coverage:.0%} of defs"
        )


class ConventionDetector:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def detect(self, max_files: int = 40) -> Conventions:
        files = self._sample_files(max_files)
        single = double = 0
        space_indent = tab_indent = 0
        indent_widths: list[int] = []
        snake_fn = camel_fn = other_fn = 0
        pascal_cls = other_cls = 0
        fns = 0
        hinted = 0
        documented = 0
        defs = 0

        for path in files:
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            s, d = self._count_quotes(source)
            single += s
            double += d
            sp, tab, widths = self._count_indent(source)
            space_indent += sp
            tab_indent += tab
            indent_widths.extend(widths)

            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fns += 1
                    defs += 1
                    if _SNAKE.match(node.name):
                        snake_fn += 1
                    elif _is_camel(node.name):
                        camel_fn += 1
                    else:
                        other_fn += 1
                    if self._has_hints(node):
                        hinted += 1
                    if ast.get_docstring(node):
                        documented += 1
                elif isinstance(node, ast.ClassDef):
                    defs += 1
                    if _PASCAL.match(node.name):
                        pascal_cls += 1
                    else:
                        other_cls += 1
                    if ast.get_docstring(node):
                        documented += 1

        return Conventions(
            indent=self._indent_label(space_indent, tab_indent, indent_widths),
            quote_style=_ratio_label(double, single, "double", "single"),
            function_naming=_naming_label(snake_fn, camel_fn, other_fn),
            class_naming="PascalCase" if pascal_cls >= other_cls else "mixed",
            type_hint_coverage=(hinted / fns) if fns else 0.0,
            docstring_coverage=(documented / defs) if defs else 0.0,
            sample_size=len(files),
        )

    # ---- helpers -----------------------------------------------------------
    def _sample_files(self, limit: int) -> list[Path]:
        out: list[Path] = []
        for path in self.root.rglob("*.py"):
            if any(part in _IGNORE_DIRS for part in path.parts):
                continue
            out.append(path)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _count_quotes(source: str) -> tuple[int, int]:
        single = double = 0
        try:
            for tok in tokenize.generate_tokens(io.StringIO(source).readline):
                if tok.type == tokenize.STRING:
                    s = tok.string.lstrip("rbfuRBFU")
                    if s.startswith("'''") or s.startswith('"""'):
                        continue
                    if s.startswith("'"):
                        single += 1
                    elif s.startswith('"'):
                        double += 1
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
        return single, double

    @staticmethod
    def _count_indent(source: str) -> tuple[int, int, list[int]]:
        space = tab = 0
        widths: list[int] = []
        for line in source.splitlines():
            if not line or not line[0].isspace():
                continue
            if line[0] == "\t":
                tab += 1
            else:
                space += 1
                stripped = len(line) - len(line.lstrip(" "))
                if stripped:
                    widths.append(stripped)
        return space, tab, widths

    @staticmethod
    def _has_hints(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        if node.returns is not None:
            return True
        args = node.args
        all_args = (list(args.posonlyargs) + list(args.args)
                    + list(args.kwonlyargs))
        if any(a.annotation is not None for a in all_args):
            return True
        for extra in (args.vararg, args.kwarg):
            if extra is not None and extra.annotation is not None:
                return True
        return False

    @staticmethod
    def _indent_label(space: int, tab: int, widths: list[int]) -> str:
        if tab > space:
            return "tabs"
        positive = [w for w in widths if w > 0]
        if not positive:
            return "4 spaces"
        # The indent unit is the GCD of the *frequently occurring* widths, which
        # ignores rare continuation-line alignments that would otherwise drag a
        # min()-based estimate down to 1-3.
        counts = Counter(positive)
        threshold = max(counts.values()) * 0.2
        frequent = [w for w, c in counts.items() if c >= threshold]
        unit = frequent[0]
        for w in frequent[1:]:
            unit = gcd(unit, w)
        if unit not in (2, 3, 4, 8):
            unit = 4
        return f"{unit} spaces"


def _is_camel(name: str) -> bool:
    return bool(re.match(r"^[a-z]+[A-Z]", name))


def _ratio_label(a: int, b: int, a_label: str, b_label: str, mixed_band: float = 0.7) -> str:
    total = a + b
    if total == 0:
        return a_label
    if a / total >= mixed_band:
        return a_label
    if b / total >= mixed_band:
        return b_label
    return "mixed"


def _naming_label(snake: int, camel: int, other: int) -> str:
    total = snake + camel + other
    if total == 0:
        return "snake_case"
    if snake / total >= 0.6:
        return "snake_case"
    if camel / total >= 0.6:
        return "camelCase"
    return "mixed"
