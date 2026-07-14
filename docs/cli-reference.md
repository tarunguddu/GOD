# CLI reference

All commands are invoked as `god <command> [options]` (or
`python -m god_agent.cli <command>` if the console script isn't on PATH).

## Global options

These come **before** the subcommand:

| Option | Default | Description |
|--------|---------|-------------|
| `--version` | — | Print version and exit. |
| `--root PATH` | `.` | Project root to operate on. |
| `--provider {mock,anthropic}` | from config | Override the LLM provider for this run. |

Example: `god --root ../other-project --provider anthropic generate "..." x.py`

## Exit codes

Most commands return `0` on success. Gate-style commands return non-zero to fail
CI:

| Command | Non-zero when |
|---------|---------------|
| `verify` | verification failed / unverified |
| `critique` | blocking findings (syntax error, secret, HIGH+ vuln) |
| `health` | a HIGH+ **security** suggestion exists |
| `generate` | change rejected or not accepted |
| `loop` | did not reach completion |
| `depcheck` | a dependency is `danger` (hallucinated/typosquat) |

---

## Commands

### Perception

#### `god status`
Project summary: root, stacks, file count, code-graph stats, git branch, LLM
provider, usage.

#### `god tree [--depth N]`
Print the project tree (default depth 3).

#### `god search QUERY [--top N]`
Token-overlap relevance search across source files (default top 8).

#### `god graph [--top N]`
Code-graph statistics and the top-N complexity hotspots.

### Quality & verification

#### `god verify [--command CMD]`
Run the test command and report a parsed, honest verdict. Auto-detects the
command from project markers (e.g. `pytest` for Python) if `--command` is
omitted. Detects "vacuous green" (passing only via skips).

#### `god critique PATH [--json]`
Deterministic review of one file: secrets, vulnerabilities, stubs, smells.
`--json` emits structured output (used by the VS Code extension). Honors
`# god:allow <rule>` suppression comments.

#### `god health [--top N]`
Proactive whole-project analysis with a 0–100 score and prioritized suggestions
across security / complexity / testing / maintainability.

#### `god depcheck NAME... [--ecosystem {pypi,npm}] [--offline]`
Vet dependency names against the registry and for typosquatting proximity to
popular packages. `--offline` skips registry lookups (typosquat check still
runs).

### Reasoning & generation

#### `god plan REQUEST`
Classify a request (feature/bugfix/refactor/test/exploration) and print a
structured, verify-anchored plan.

#### `god generate INSTRUCTION PATH [--command CMD] [--passes N] [--allow-mock]`
Generate code for INSTRUCTION and run it through the guarded pipeline
(critique → checkpoint → write → verify → rollback). Requires a real provider;
use `--allow-mock` to exercise the pipeline offline. `--passes` caps
generation/fix attempts (default 2).

#### `god route TASK`
Show which model tier (fast/powerful) a task would route to, and why.

### Autonomous operation

#### `god loop TASK [--command CMD] [--max-runs N] [--max-seconds S] [--completion-threshold N]`
Run a bounded autonomous quality-sweep loop. Stops at completion (default: two
consecutive clean iterations), max runs (default 5), optional wall-clock, or
after consecutive failures.

#### `god watch [--poll S] [--max-polls N] [--max-seconds S]`
Bounded watch mode: poll for source changes and re-analyse what changed. Always
terminates (poll/time-boxed).

#### `god sandbox COMMAND [--promote] [--approve]`
Run COMMAND inside an isolated copy of the project; show what changed. With
`--promote`, write verified changes back (only if the command exited 0).
`--approve` permits promoting deletions.

### Memory & learning

#### `god learn`
Detect and store the project's coding conventions.

#### `god memory [--top N]`
Show recorded episodes, learned conventions, and distilled lessons.

### Team & collaboration

#### `god onboard [--output PATH]`
Generate a Markdown onboarding guide from the code graph (stacks, module map,
hotspots, conventions). Prints to stdout, or writes to `--output`.

#### `god who PATH`
Show contributors/owners of a file from git history (most active first).
Requires a git repo.

#### `god team {export|import} PATH`
Export the agent's learned knowledge (conventions + episodes) to a portable JSON
bundle, or import one into the local project to share learning across a team.

### Setup & ops

#### `god chat [--command CMD] [--no-color]`
Start an **interactive REPL** — the conversational coding session. Converse with
the model, or use slash commands. It opens with a proactive health nudge, and
every edit is previewed as a colored diff and applied only on approval, then
critiqued + verified + auto-rolled-back through the guarded pipeline.

In-session commands: `/help`, `/edit <path> <task>` (generate → preview diff →
approve), `/critique <path>`, `/plan <request>`, `/health`, `/verify [cmd]`,
`/memory`, `/changes`, `/undo` (roll back the last applied change),
`/provider`, `/quit`. Plain text (no slash) is sent to the model. `--command`
sets the verification command run after edits.

#### `god init [--force] [--precommit]`
Scaffold `god_agent.toml` and detect conventions. `--force` overwrites existing
config; `--precommit` also writes a pre-commit critique gate to `.god/hooks/`.

#### `god serve [--host HOST] [--port PORT]`
Run the local read-only dashboard + JSON API (default `127.0.0.1:8787`).
**No authentication** — see [Security](security.md#web-api).

#### `god audit [-n N]`
Show the last N entries of the append-only audit log (default 20).

#### `god ask PROMPT`
Send a prompt to the configured LLM provider (mock by default).

### LLM providers

#### `god providers`
List every provider preset (OpenAI, Groq, Gemini, Anthropic, OpenRouter,
DeepSeek, Mistral, Together, xAI, Perplexity, Ollama, LM Studio, vLLM,
llama.cpp, mock) with its kind, key env var, status (configured / needs key /
local-no-key), and default model.

#### `god models`
List the models offered by the active provider (OpenAI-compatible endpoints
only — queries `/models`).

Select a provider per-command with the global `--provider` flag, or persist it
in `god_agent.toml`. See [providers.md](providers.md) for full setup.

## JSON output

`god critique --json` emits:

```json
{
  "path": "src/app.py",
  "summary": "1 critical, 1 high",
  "blocking": true,
  "findings": [
    {"severity": "CRITICAL", "rule": "secret:aws-access-key", "line": 4, "message": "..."}
  ]
}
```

The web API (`god serve`) exposes JSON at `/api/status`, `/api/health`,
`/api/memory`, `/api/graph`, and `POST /api/critique`.
