# GOD Agent — Local / Free Setup (Ollama)

**Run the agent against a local model with no API key and no per-request cost.**

> Accuracy note: an earlier version of this guide referenced models that do not
> exist as presets here (`qwen3-coder-next`, `deepseek-v4-pro`) and quoted
> benchmark percentages. This version uses the agent's real `ollama` preset and
> a model you actually pull yourself. It makes no quality or benchmark claims.

---

## What you get

- The `ollama` preset talks to a local Ollama server (OpenAI-compatible
  endpoint at `http://localhost:11434/v1`), so no API key is required.
- Requests stay on your machine.
- The core agent adds **zero third-party runtime dependencies** — it uses the
  Python 3.11+ standard library only.

The agent does not bundle or endorse a specific model. Speed and quality depend
on the model you pull and your hardware.

---

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) installed and running
- Enough disk/RAM for the model you choose (varies by model)

---

## Setup

### 1. Install Ollama

- **Windows:** `winget install Ollama.Ollama` (or download from
  <https://ollama.com>)
- **macOS:** `brew install ollama`
- **Linux:** `curl -fsSL https://ollama.com/install.sh | sh`

### 2. Start the Ollama server (if not already running)

```bash
ollama serve
```

### 3. Pull a model

The `ollama` preset's default model is `llama3.2`. Pull it (or any other model
you prefer):

```bash
ollama pull llama3.2
# or another model you have, e.g.:
# ollama pull qwen2.5-coder
# ollama pull codellama
```

Verify:

```bash
ollama list
```

### 4. Configure the agent

Create or edit `god_agent.toml` in your project root:

```toml
# god_agent.toml — local / free via Ollama
[god-agent]
llm_provider = "ollama"
llm_model = "llama3.2"           # must match a model you pulled
llm_fast_model = "llama3.2"      # routing tiers (optional to change)
llm_powerful_model = "llama3.2"
```

If you pulled a different model, set `llm_model` (and the fast/powerful tiers)
to that model's name as shown by `ollama list`.

### 5. Verify the agent sees the provider

```bash
py -m god_agent.cli providers   # ollama should show as available
py -m god_agent.cli models      # lists models the local server offers
```

---

## Try it

Run the offline quality-sweep loop (this workflow does not call the model — it
verifies and critiques deterministically, and is a good end-to-end check):

```bash
py -m god_agent.cli loop "self-check" --command "py -m pytest" --max-runs 2
```

Ask the configured model something directly:

```bash
py -m god_agent.cli ask "Explain what this project's loop does."
```

Generate code through the guarded pipeline (critique → checkpoint → verify →
remember):

```bash
py -m god_agent.cli generate "add a docstring to the top of utils" src/god_agent/workspace.py --command "py -m pytest"
```

See which model tier a task would route to:

```bash
py -m god_agent.cli route "add tests for the config loader"
```

---

## Troubleshooting

**`ollama` shows as unavailable / falls back to mock**
- Confirm the server is running: `curl http://localhost:11434/api/tags`
- Start it with `ollama serve`.
- The agent falls back to the offline `mock` provider when Ollama is
  unreachable, so commands still run — they just use the stub.

**"model not found"**
- Make sure `llm_model` in `god_agent.toml` matches a name from `ollama list`.
- Pull it: `ollama pull <model>`.

**Slow responses**
- Local speed depends on the model size and your hardware. Try a smaller model
  and set `llm_model` accordingly.

---

## Using a hosted provider instead

If you would rather use a hosted API (some offer a free tier), set the preset
and its API-key env var. For example, Groq:

```toml
[god-agent]
llm_provider = "groq"   # reads GROQ_API_KEY from the environment
```

See `VARIANT_COMPARISON.md` for the full list of presets.

---

## Notes

- All filesystem changes go through the boundary-checked, backed-up
  `FileSystemTool`; shell runs through the screened `ShellTool`.
- The test suite runs fully offline: `py -m pytest`.
