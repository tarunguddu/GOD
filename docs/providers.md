# LLM providers

The agent works with **any** LLM — free, paid, or local — through one of two
mechanisms:

1. A generic **OpenAI-compatible** adapter (covers ~90% of services and every
   local runner).
2. Native adapters for **Anthropic** and **Google Gemini**.

Everything uses the Python standard library — **no SDK to install**. Pick a
provider by name and set its key (or run a local server).

```bash
god providers          # list every preset and whether it's configured
```

## Quick start by provider

Set the key as an environment variable, then select the provider. You can do it
per-command with `--provider`, or persist it in `god_agent.toml`.

### Free / cheap hosted

**Groq** (free tier, very fast):
```bash
export GROQ_API_KEY=gsk_...
god --provider groq ask "explain this repo"
god --provider groq generate "add a CLI flag --verbose" src/app.py
```

**Google Gemini** (generous free tier):
```bash
export GEMINI_API_KEY=...
god --provider gemini ask "summarize the architecture"
```

**OpenRouter** (one key, 200+ models incl. free ones):
```bash
export OPENROUTER_API_KEY=sk-or-...
god --provider openrouter --root . generate "..." src/x.py     # default model
# pick any model via config: llm_model = "meta-llama/llama-3.3-70b-instruct:free"
```

**DeepSeek / Mistral / Together / Fireworks / xAI / Perplexity** — same pattern,
each with its own `*_API_KEY` (see `god providers`).

### Paid

**OpenAI:**
```bash
export OPENAI_API_KEY=sk-...
god --provider openai generate "..." src/x.py     # default model gpt-4o-mini
```

**Anthropic:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
god --provider anthropic generate "..." src/x.py
```

### Local (free, fully offline)

No key required — just run the local server and point the agent at it.

**Ollama:**
```bash
ollama serve            # then: ollama pull llama3.2  (or qwen2.5-coder, etc.)
god --provider ollama --root . ask "explain this module"
# choose the pulled model:  llm_model = "qwen2.5-coder" in god_agent.toml
```

**LM Studio** (start its local server), **vLLM**, **llama.cpp** (`--server`):
```bash
god --provider lmstudio ask "..."     # http://localhost:1234/v1
god --provider vllm     ask "..."     # http://localhost:8000/v1
god --provider llamacpp ask "..."     # http://localhost:8080/v1
```

## Configure it permanently

In `god_agent.toml`:

```toml
[god-agent]
llm_provider = "groq"
llm_model = "llama-3.3-70b-versatile"     # optional; preset default otherwise
# llm_api_key_env = "GROQ_API_KEY"        # optional; preset default otherwise
```

For a local model:

```toml
[god-agent]
llm_provider = "ollama"
llm_model = "qwen2.5-coder:7b"
```

## Custom / self-hosted endpoints

Any OpenAI-compatible URL works — set `llm_base_url`:

```toml
[god-agent]
llm_provider = "custom"
llm_base_url = "https://my-gateway.internal/v1"
llm_api_key_env = "MY_GATEWAY_KEY"        # omit for a keyless internal endpoint
llm_model = "my-model"
```

Some gateways want extra headers (e.g. OpenRouter app attribution):

```toml
[god-agent.llm_extra_headers]
"HTTP-Referer" = "https://your-app.example"
"X-Title" = "GOD Agent"
```

## How selection & fallback work

- `god providers` lists presets and their status (`configured` / `needs key` /
  `local/no-key`).
- `god models` lists the models the active provider offers (OpenAI-compatible
  endpoints only).
- If you select a hosted provider but its key isn't set, the agent **falls back
  to the offline mock provider** rather than erroring — so the deterministic
  features keep working. `god generate` will say "no usable code (provider=mock)"
  in that case; set the key (or use `--allow-mock` to just exercise the
  pipeline).
- The `ModelRouter` (`god route "<task>"`) picks the fast vs. powerful model per
  task; set `llm_fast_model` / `llm_powerful_model` to your provider's models.

## Adding a new provider

If a service speaks the OpenAI `/chat/completions` schema, add a one-line preset
to `src/god_agent/llm/registry.py`:

```python
"myservice": Preset("openai_compat", "https://api.myservice.com/v1",
                    "MYSERVICE_API_KEY", "default-model"),
```

Native (non-OpenAI) schemas get a small provider class like
`anthropic_provider.py` / `gemini_provider.py` and a preset with the matching
`kind`.
