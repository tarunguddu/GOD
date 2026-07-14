# GOD Agent — VS Code extension

A thin client over the `god` CLI. It surfaces the agent's deterministic critique
as native editor diagnostics and shows the project-health report in an output
channel. All analysis runs in the CLI; the extension only invokes it.

## Prerequisites

The `god` CLI must be installed and on PATH, or set `god.command` to how you
invoke it (e.g. `py -m god_agent.cli`).

```bash
pip install -e .            # from the god_agent project root
```

## Install (development)

1. Copy or symlink this folder into your VS Code extensions dir, or open it in
   VS Code and press F5 to launch an Extension Development Host.
2. Open a Python project.

## Commands

- **GOD: Critique Current File** — runs `god critique <file> --json` and shows
  findings as diagnostics (secrets/vulns as errors, stubs/smells as warnings).
- **GOD: Project Health** — runs `god health` and prints the prioritized report.

Critique also runs automatically on save (toggle with `god.critiqueOnSave`).

## Settings

| Setting | Default | Description |
|---|---|---|
| `god.command` | `god` | How to invoke the CLI (e.g. `py -m god_agent.cli`). |
| `god.critiqueOnSave` | `true` | Run critique automatically when a `.py` file is saved. |

## Note

This scaffold is intentionally minimal and dependency-free (no build step). For
publishing you would add bundling (esbuild) and a `.vscodeignore`.
