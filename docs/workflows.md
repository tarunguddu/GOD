# Workflows

Practical, end-to-end recipes. All work offline unless a real LLM provider is
noted.

## Pre-commit / CI quality gate

Use the deterministic gates to block bad code before it lands.

```bash
# fail if any tracked source file has blocking findings
for f in $(git ls-files '*.py'); do god critique "$f" || exit 1; done

# fail on serious project-health regressions
god health

# never trust "done" — re-run and parse the suite
god verify --command "pytest"
```

`god init --precommit` writes a ready-made hook to `.god/hooks/pre-commit`;
install it with:

```bash
cp .god/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

Or use the provided `.pre-commit-config.yaml` with the
[pre-commit](https://pre-commit.com) framework.

## Reviewing code

```bash
god critique src/payments/charge.py          # human-readable
god critique src/payments/charge.py --json    # machine-readable
```

Findings are severity-ranked. Blocking = syntax error, any secret, or a HIGH+
vulnerability. To allow an intentional, mitigated pattern:

```python
yaml.load(data)  # god:allow vuln:yaml-unsafe
API_KEY = os.environ["KEY"]   # not flagged — reads from env
```

## Generating code safely (real model)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
god --provider anthropic generate "add pagination to list_users()" src/api/users.py --command "pytest"
```

What happens, in order:

1. The agent gathers context (relevant files + learned conventions + past lessons).
2. The model generates code; the deterministic critic reviews it.
3. If blocking, the model is re-prompted with the findings (up to `--passes`).
4. A checkpoint is taken, the code is written, and the test command runs.
5. If verification fails, the change is **automatically rolled back**.
6. The outcome is recorded as an episode (so the agent learns).

Bad code (secrets/vulns/syntax errors) is rejected **before it touches disk**.

## Autonomous quality loop

```bash
god loop "raise project health to green" --command "pytest" --max-runs 8
```

Bounded by max runs, optional `--max-seconds`, a completion signal (two
consecutive clean iterations), and a consecutive-failure circuit breaker. Cross-
iteration progress is persisted to `.god/SHARED_TASK_NOTES.md`.

## Experimenting in isolation (sandbox)

Run something risky against a throwaway copy; promote only if it succeeds:

```bash
god sandbox "python scripts/migrate.py" --promote
```

The real tree is untouched unless the command exits 0 and you pass `--promote`.
Promotion goes through the backup/boundary layer.

## Watch mode

```bash
god watch --max-polls 240 --poll 1.0
```

Re-analyses files as they change and prints fresh suggestions. Always
terminates (poll/time-boxed) — there is no open-ended run.

## Dependency hygiene

```bash
god depcheck requests pydantic some-new-pkg
god depcheck react axios --ecosystem npm
```

Catches hallucinated/non-existent packages and typosquats before you install
them.

## Team knowledge sharing

```bash
# on one machine / clone
god team export team-knowledge.json
git add team-knowledge.json && git commit -m "share agent knowledge"

# on another clone
god team import team-knowledge.json     # merges conventions + episodes
```

Generate onboarding docs for new contributors:

```bash
god onboard --output ONBOARDING.md
god who src/core/scheduler.py           # who to ask about this file
```

## Dashboard

```bash
god serve                # http://127.0.0.1:8787
```

Read-only: status, health, memory, code-graph, and ad-hoc critique of pasted
code. See [Security](security.md#web-api) before changing the bind host.
