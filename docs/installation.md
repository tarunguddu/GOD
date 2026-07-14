# Installation

## Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | **3.11 or newer** | Uses `tomllib`, structural pattern matching, and `X | Y` typing. |
| pip | any recent | For installing the package. |
| git | optional | Enables `god who` and history-based features; everything else works without it. |

The **core has zero third-party runtime dependencies** — it relies only on the
Python standard library, including all LLM access (every provider is reached
over stdlib HTTP, so **no vendor SDK is required**).

Check your Python version:

```bash
python --version      # or: py --version   (Windows launcher)
```

If `python` is not found on Windows, use the `py` launcher in every command
below (e.g. `py -m pip ...`, `py -m god_agent.cli ...`).

## Install methods

### 1. Editable install (recommended for now)

From the `god_agent` project directory:

```bash
pip install -e .
```

This exposes the `god` command. Variants:

```bash
pip install -e ".[dev]"        # adds pytest + pytest-cov (for running tests)
```

No vendor SDKs are required for LLM access — every provider (OpenAI, Groq,
Gemini, Anthropic, OpenRouter, Ollama, …) is reached over the standard library.
See [providers.md](providers.md).

### 2. Run from source without installing

If you'd rather not install, set `PYTHONPATH` to the `src` directory:

```bash
# from the god_agent directory
PYTHONPATH=src python -m god_agent.cli status        # macOS/Linux
```

```powershell
# Windows PowerShell
$env:PYTHONPATH="src"; py -m god_agent.cli status
```

## Verify the install

```bash
god --version
# -> god-agent 0.1.0

god --help          # lists all commands
```

If you installed editable but `god` is "not found", the console script directory
may not be on your `PATH` (common on Windows — pip prints a warning showing the
`Scripts` directory). Either add that directory to `PATH`, or invoke the module
directly:

```bash
python -m god_agent.cli --version
```

## First run in your project

```bash
cd /path/to/your/project
god init            # scaffolds god_agent.toml and detects your conventions
god status          # confirms detection (stacks, file count, git branch)
```

`god init --precommit` additionally writes a pre-commit critique gate you can
install into `.git/hooks`.

## Uninstall

```bash
pip uninstall god-agent
```

Runtime data the agent writes (backups, checkpoints, audit log, learned memory)
lives under a `.god/` directory in each project — delete it to reset:

```bash
rm -rf .god          # macOS/Linux
Remove-Item -Recurse -Force .god   # Windows PowerShell
```
