"""Team features — shared knowledge and onboarding.

Deterministic, offline collaboration helpers:

  - Knowledge bundles: export/import the agent's learned conventions + episodes
    (delegated to :class:`MemorySystem`) so a team shares one evolving memory.
  - Onboarding doc generation: a Markdown overview of the project synthesised
    from the code graph — stacks, module map, entry points, and complexity
    hotspots a new contributor should know about.
  - Code ownership: who-knows lookups via git history (on ``GitTool``).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

_MAX_BUNDLE_BYTES = 10_000_000      # reject oversized bundles before parsing


def export_bundle(agent, path: str) -> str:
    bundle = agent.memory.export_bundle()
    # Write through the FileSystemTool so the export is boundary-checked + backed up.
    agent.fs.write_file(path, json.dumps(bundle, indent=2))
    return agent.boundary.relative(agent.boundary.check(path))


def import_bundle(agent, path: str) -> int:
    source = agent.boundary.check(path)
    size = Path(source).stat().st_size
    if size > _MAX_BUNDLE_BYTES:
        raise ValueError(
            f"bundle too large ({size} bytes > {_MAX_BUNDLE_BYTES}); refusing to import")
    bundle = json.loads(Path(source).read_text(encoding="utf-8"))
    return agent.memory.import_bundle(bundle)


def generate_onboarding(agent) -> str:
    """Produce a Markdown onboarding overview from project perception."""
    project = agent.perceive(refresh=True)
    graph = agent.context.graph
    stats = graph.stats()

    # Group symbols by file to build a module map (classes/functions per file).
    by_file: dict[str, list[str]] = defaultdict(list)
    for node in graph.nodes.values():
        if node.kind in ("class", "function"):
            by_file[node.file].append(f"{node.kind} {node.qualified_name}")

    lines: list[str] = []
    lines.append(f"# Onboarding: {Path(project.root).name}\n")
    lines.append("## Tech stack")
    lines.append(f"- detected: {', '.join(project.stacks) or 'unknown'}")
    if project.test_command:
        lines.append(f"- tests: `{project.test_command}`")
    if project.build_command:
        lines.append(f"- build: `{project.build_command}`")
    lines.append("")

    lines.append("## At a glance")
    lines.append(f"- {project.file_count} source files, {stats.get('symbols', 0)} "
                 f"symbols ({stats.get('class', 0)} classes, "
                 f"{stats.get('function', 0)} functions, "
                 f"{stats.get('method', 0)} methods)")
    lines.append("")

    lines.append("## Module map")
    for file in sorted(by_file)[:30]:
        members = by_file[file][:6]
        more = "" if len(by_file[file]) <= 6 else f" … (+{len(by_file[file]) - 6})"
        lines.append(f"- `{file}`: {', '.join(members)}{more}")
    lines.append("")

    hotspots = graph.hotspots(top=8)
    if hotspots:
        lines.append("## Complexity hotspots (read these carefully)")
        for node in hotspots:
            lines.append(f"- `{node.file}::{node.qualified_name}` "
                         f"(complexity {node.complexity})")
        lines.append("")

    lines.append("## Conventions")
    conv = agent.memory.conventions()
    if conv is not None:
        lines.append(conv.render())
    else:
        lines.append("- run `god learn` to detect and record project conventions")
    lines.append("")
    return "\n".join(lines)
