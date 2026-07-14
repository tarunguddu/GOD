# Troubleshooting & FAQ

## Installation & invocation

**`god: command not found` after install.**
The console script directory isn't on your PATH (pip prints a warning showing
it, commonly a `Scripts` dir on Windows). Either add it to PATH or run the module
directly: `python -m god_agent.cli ...` (or `py -m god_agent.cli ...`).

**`python` not found on Windows.**
Use the `py` launcher: `py -m pip install -e .`, `py -m god_agent.cli status`.

**`ModuleNotFoundError: god_agent` when running from source.**
Set `PYTHONPATH=src` (PowerShell: `$env:PYTHONPATH="src"`) or do an editable
install (`pip install -e .`).

## Verification

**`god verify` says "no test counts parsed" but the command succeeded.**
Some runners buffer their summary line under `-q`. Run without `-q`, or pass an
explicit `--command`. The verdict (pass/fail) is still correct.

**Auto-detected test command is wrong / not on PATH.**
Set it explicitly: `god verify --command "py -m pytest"` or add
`test_command = "py -m pytest"` to `god_agent.toml`.

## Critique

**The critic flagged something intentional (e.g. a needed `shell=True`).**
Add an inline suppression on the flagged line:
`subprocess.run(cmd, shell=True)  # god:allow shell-injection`. Put it on the
exact line of the finding (for `shell=True`, that's the `shell=True` line). For
secrets, name the rule explicitly.

**A real-looking key in a test fixture gets flagged.**
Test files (`tests/`, `test_*.py`, `conftest.py`) are excluded from the
project-health sweep, but `god critique <file>` still scans them on demand. Use a
clearly-fake value (containing `example`, `your-`, `xxxx`, `<...>`) or an inline
suppression.

## Generation

**`god generate` says "no usable code (provider=mock)".**
The default mock provider doesn't produce real code. Configure the Anthropic
provider (see [Configuration](configuration.md#llm-providers)) or pass
`--allow-mock` just to exercise the pipeline.

**`AnthropicProvider unavailable`.**
Install the SDK (`pip install -e ".[anthropic]"`) and set the API key env var
(`ANTHROPIC_API_KEY`). Without them, the agent falls back to mock.

## Loops & watch

**`god loop` stops with "aborted after N consecutive failures".**
The circuit breaker tripped — the iteration kept failing (e.g. a broken verify
command or unfixable blocking files). Check the failure reason in the report and
`.god/SHARED_TASK_NOTES.md`.

**`god watch` exits immediately / after a while.**
By design it's bounded by `--max-polls` (default 60) and optional
`--max-seconds`. Raise them for longer sessions; it will always terminate.

## Web

**Can't reach the dashboard from another machine.**
It binds to localhost with no auth on purpose. Don't expose it directly; front
it with an authenticating proxy. See [Security](security.md#web-api).

## Git features

**`god who` prints "not a git repository".**
The feature needs git history. Initialize/clone with full history
(`fetch-depth: 0` in CI).

## Resetting state

Delete the per-project runtime directory to clear backups, checkpoints, audit
log, and learned memory:

```bash
rm -rf .god                         # macOS/Linux
Remove-Item -Recurse -Force .god    # Windows PowerShell
```

## FAQ

**Does it work without an API key?** Yes — almost everything (perception,
critique, verify, health, loop, memory, sandbox, web, team) is deterministic and
offline. Only `god generate`/`ask` need a real model.

**Will it send my code anywhere?** No, unless you configure a real LLM provider
and invoke generation. The only other network calls are optional `depcheck`
registry lookups.

**Is it production-ready?** It's a complete, tested reference implementation
(184 tests, ~86% coverage). The Anthropic path is hardened but exercise it with
your own key before relying on generation in production.

**Which Python versions?** 3.11, 3.12, 3.13 (tested in CI).
