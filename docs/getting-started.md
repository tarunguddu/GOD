# Getting started

This walkthrough takes about ten minutes and uses only the offline (no API key)
features. Run it inside any Python/JS/Go/Rust project.

## 1. Adopt the agent

```bash
god init
```

This scaffolds `god_agent.toml`, detects your project's coding conventions
(indentation, quotes, naming, type-hint/docstring coverage), and stores them.

## 2. Understand the project

```bash
god status        # stacks, file/symbol counts, git branch, LLM provider
god tree          # directory tree
god graph         # code-graph stats + complexity hotspots
god search "auth token"   # token-overlap relevance search across files
```

## 3. Ask "what should I fix?" (proactive)

```bash
god health
```

Produces a prioritized, scored report across four categories — **security**
(secrets/vulns), **complexity** (hotspots), **testing** (modules with no test
file), and **maintainability** (large files, TODO density). It exits non-zero if
there's a HIGH+ security issue, so it doubles as a CI gate.

## 4. Review a file (deterministic, offline)

```bash
god critique src/app/handler.py
god critique src/app/handler.py --json    # structured output (used by the IDE extension)
```

Flags hardcoded secrets, dangerous patterns (`eval`, `shell=True`, SQL string
interpolation, unsafe deserialization, …), and unfinished stubs. Secret *values*
are redacted in output. Exits non-zero on blocking findings.

To deliberately allow a flagged-but-intentional pattern, annotate the line:

```python
subprocess.run(cmd, shell=True)  # god:allow shell-injection
```

(A bare `# god:allow` suppresses non-secret findings on that line; secrets must
be named explicitly, so a stray comment can never hide a credential.)

## 5. Verify — never trust "done"

```bash
god verify --command "pytest"
```

Actually runs the command, parses the real result, and reports a verdict like
`VERIFIED PASS via 'pytest': 42 passing`. It even detects "vacuous green" (a
suite that passes only because everything was skipped).

## 6. Run an autonomous quality loop

```bash
god loop "keep the project green and clean" --command "pytest" --max-runs 5
```

Each iteration verifies the suite and critiques the source tree, stopping when
the project is green and clean (or when bounds are hit). It's always bounded —
max runs, optional wall-clock, and a consecutive-failure circuit breaker.

## 7. Let it learn

```bash
god learn         # (re)detect + store conventions
god memory        # show episodes, learned conventions, and lessons
```

Every guarded change the agent makes is recorded. Recurring mistakes become
"lessons" that get injected back into future generation prompts — the agent gets
better with use.

## 8. Optional: a local dashboard

```bash
god serve         # http://127.0.0.1:8787  (read-only, localhost, no auth)
```

## Next

- The full command list and flags: [CLI reference](cli-reference.md)
- Generating code with a real model: [Configuration → LLM providers](configuration.md#llm-providers)
- Recipes for common tasks: [Workflows](workflows.md)
