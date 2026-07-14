# Contributing

## Dev setup

```bash
pip install -e ".[dev]"      # editable install + pytest + pytest-cov
```

Run from source without installing by setting `PYTHONPATH=src`.

## Running the tests

```bash
pytest                                   # full suite (offline)
pytest -q                                # quiet
pytest tests/test_critic.py -k secret    # a subset
pytest --cov=god_agent --cov-report=term-missing   # with coverage (~86%)
```

The suite runs **fully offline**. One test (`test_anthropic_provider.py::
test_live_roundtrip`) makes a real API call and is skipped automatically unless
`ANTHROPIC_API_KEY` is set.

On Windows, `pytest` may not be on PATH — use `py -m pytest`.

## Project conventions

These are enforced by the agent's own critic and CI; they mirror the conventions
`ConventionDetector` infers from the codebase:

- Python 3.11+, 4-space indentation, double quotes.
- `snake_case` functions, `PascalCase` classes; type hints on public functions;
  module docstrings on every file.
- **Zero third-party runtime dependencies** in the core package. Optional
  integrations must import lazily and degrade gracefully.
- All filesystem mutation goes through `FileSystemTool`; all shell execution
  through `ShellTool`. If a call legitimately needs `shell=True`, annotate it
  `# god:allow shell-injection`.
- Generated/applied code must flow through `ReasoningEngine.safe_apply`.
- Memory writes must never break the primary workflow (wrap defensively).

A workspace steering file (`.kiro/steering/god-agent.md`) encodes the same rules.

## The project eats its own dog food

Before opening a PR, run the agent's own gates:

```bash
god critique <changed files>     # must have no blocking findings
god health                       # must exit 0
god verify --command "pytest"    # must pass
god loop "self-check" --command "pytest" --max-runs 3   # should complete
```

If `god critique` flags an intentional, mitigated pattern, add a justified
`# god:allow <rule>` — never to silence a real issue.

## CI

`.github/workflows/ci.yml` runs across Python 3.11–3.13 and enforces, as hard
gates:

1. `pytest --cov`
2. a `god critique` sweep over every source file
3. `god health`

`.pre-commit-config.yaml` wires the critique + tests into a local pre-commit
hook (`pip install pre-commit && pre-commit install`).

## Adding a feature

1. Add the module under `src/god_agent/...` following the conventions above.
2. Add tests under `tests/` (the suite must stay green and offline).
3. Wire any new CLI command into `cli.py` and document it in
   [docs/cli-reference.md](cli-reference.md).
4. Run the dog-food gates above.
5. Keep the README's roadmap/test-count accurate.

## Where things live

See [architecture.md](architecture.md) for the full module map.
