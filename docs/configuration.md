# Configuration

Configuration is layered, later sources overriding earlier ones:

1. Built-in defaults
2. `god_agent.toml` at the project root (optional)
3. CLI flags (`--provider`, `--command`, etc.)

Create the file with `god init`, or write it by hand.

## `god_agent.toml`

```toml
[god-agent]
# --- safety ---
confirm_destructive = true       # require approval for deletes/wide changes
max_files_per_action = 25        # changes touching more files are treated as high-risk

# --- llm ---
llm_provider = "mock"            # "mock" (offline, default) or "anthropic"
llm_model = "claude-sonnet-4"    # default model
llm_fast_model = "claude-haiku"  # fast tier (routing)
llm_powerful_model = "claude-sonnet-4"   # capable tier (routing)
llm_api_key_env = "ANTHROPIC_API_KEY"    # env var the API key is read from

# --- verification ---
# test_command = "pytest"        # leave unset to auto-detect from project markers
# build_command = "python -m build"
```

## Settings reference

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `confirm_destructive` | bool | `true` | Deletes and wide-impact changes require explicit approval. |
| `max_files_per_action` | int | `25` | Above this, a file change is High risk. |
| `llm_provider` | str | `"mock"` | Any preset (`god providers`): `openai`, `groq`, `gemini`, `anthropic`, `openrouter`, `ollama`, `lmstudio`, `deepseek`, `mistral`, `together`, `xai`, … or `custom`/`mock`. |
| `llm_model` | str | preset default | Model id; preset's default if unset. |
| `llm_api_key_env` | str | preset default | Env var holding the key; preset's default if unset. |
| `llm_base_url` | str | preset default | Override / custom / self-hosted endpoint URL. |
| `llm_extra_headers` | table | `{}` | Extra HTTP headers some gateways require. |
| `llm_fast_model` | str | `"claude-haiku"` | Model the router picks for light/exploration/test tasks. |
| `llm_powerful_model` | str | `"claude-sonnet-4"` | Model for feature/refactor/bugfix tasks. |
| `test_command` | str | auto | Verification command; auto-detected if unset. |
| `build_command` | str | auto | Build command. |

Auto-detection maps project markers to commands, e.g. `pyproject.toml`/
`requirements.txt` → `pytest`, `package.json` → `npm test`, `go.mod` →
`go test ./...`, `Cargo.toml` → `cargo test`, `pom.xml` → `mvn test`.

## LLM providers

The agent works with **any** LLM — free, paid, or local — with no SDK to
install (all HTTP via the standard library). Most services (OpenAI, Groq,
OpenRouter, Mistral, DeepSeek, Together, xAI, and every local runner like Ollama
/ LM Studio / vLLM) are reached through one OpenAI-compatible adapter; Anthropic
and Gemini have native adapters.

```bash
god providers              # list presets + which are configured
export GROQ_API_KEY=...    # e.g. Groq's free tier
god --provider groq generate "add pagination" src/api/users.py
god --provider ollama ask "explain this module"   # local, no key
```

See [Configuration → LLM providers](configuration.md#llm-providers) for the
default (offline mock) and the full setup matrix.

### Mock (default, offline)

No setup. Deterministic responses let you exercise the full workflow — planning,
the guarded pipeline, verification, memory — without a network or API key. The
mock provider does **not** produce real code, so `god generate` will report "no
usable code" unless you pass `--allow-mock` (which just exercises the pipeline).

### Real models (hosted or local)

Pick any provider preset and set its key (or run a local server). Full matrix
and copy-paste commands are in **[providers.md](providers.md)**. Examples:

```bash
god providers                              # list presets + status

export GROQ_API_KEY=gsk_...                # free, fast
god --provider groq generate "..." src/x.py

export GEMINI_API_KEY=...                  # free tier
god --provider gemini ask "..."

god --provider ollama ask "..."            # local, no key (ollama serve)
```

Or set it in `god_agent.toml` (`llm_provider`, optional `llm_model`,
`llm_base_url`). If a hosted provider's key is missing, the agent **falls back to
mock** rather than failing.

Native providers (Anthropic, Gemini) and the generic OpenAI-compatible adapter
all support per-request model selection (wired to `god route`) and retry
transient errors (429/5xx/network) with exponential backoff.

## Runtime data (`.god/`)

The agent writes operational data under `.god/` in each project:

| Path | Contents |
|------|----------|
| `.god/backups/` | Timestamped backups taken before edits. |
| `.god/checkpoints/` | Snapshots for rollback. |
| `.god/audit.log` | Append-only JSON-lines log of consequential actions. |
| `.god/memory/episodes.jsonl` | Episodic memory (actions + outcomes). |
| `.god/memory/conventions.json` | Cached detected conventions. |
| `.god/SHARED_TASK_NOTES.md` | Cross-iteration notes for autonomous loops. |

Add `.god/` to your `.gitignore` (the project's own `.gitignore` already does).
Delete the folder to reset all runtime state.
