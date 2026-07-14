# GOD Agent — Choosing a Provider

**How to pick an LLM provider preset for the agent.**

> Accuracy note: an earlier version of this file compared "Free / Hybrid /
> Enterprise variants" with invented benchmark percentages, per-task cost
> tables, and model names that do not exist here. It also listed
> parallel-execution and long-context features as shipped. The agent has no
> such "variants" or features. What actually varies is which **provider preset**
> you configure. This version documents that honestly.

---

## The one thing that changes: the provider preset

The agent's behaviour is the same regardless of model. You choose a provider by
setting `llm_provider` (and optionally `llm_model`, `llm_fast_model`,
`llm_powerful_model`) in `god_agent.toml`. Everything else — routing, memory,
loop, safety — is identical.

There are three practical categories of preset:

| Category | Presets | API key | Runs offline |
|----------|---------|---------|--------------|
| Offline default | `mock` | none | yes (deterministic stub) |
| Local model server | `ollama`, `lmstudio`, `vllm`, `llamacpp` | none | yes (after model pulled) |
| Hosted API | `openai`, `groq`, `openrouter`, `deepseek`, `mistral`, `together`, `fireworks`, `xai`, `perplexity`, `anthropic`, `gemini` | yes (per preset) | no |

Some hosted presets advertise a free tier (`groq`, `openrouter`, `mistral`,
`gemini`); this is noted in `registry.py`. The agent does not measure or claim
model quality, and no benchmark numbers are asserted here.

---

## Recommendations by situation

| Situation | Suggested preset | Why |
|-----------|------------------|-----|
| Trying the agent, no setup | `mock` | Deterministic, offline, zero config |
| Fully local / private | `ollama` (model `llama3.2`) | No API key, runs offline once pulled |
| Want a hosted free tier | `groq` or `gemini` | Free tier available, just set the env key |
| Already have an OpenAI/Anthropic key | `openai` / `anthropic` | Uses your existing key |
| Access many models via one key | `openrouter` | Gateway to many hosted models |

---

## What is the same across every preset

- **Zero third-party runtime dependencies** in the core (stdlib only).
- **Cost-aware routing** via `ModelRouter` — trivial/exploration/test work goes
  to `llm_fast_model`, complex/long work to `llm_powerful_model`.
- **Token budget** via `LLMOrchestrator.budget_tokens`.
- **Deterministic offline memory**: conventions, lessons, and skills.
- **Sequential autonomous loop** with budgets, completion threshold, failure
  circuit breaker, and shared cross-iteration notes.
- **Safety**: boundary-checked writes, screened shell, blocked patterns, audit
  log, checkpoints + rollback.
- **Graceful fallback**: if a hosted/local provider is unavailable, the
  orchestrator falls back to the `mock` provider instead of failing.

---

## Local vs hosted trade-offs (qualitative)

**Local (`ollama`, etc.)**
- No API key, no per-request cost, runs offline.
- Quality and speed depend entirely on the model you pull and your hardware.
- You manage the model server yourself.

**Hosted (`openai`, `anthropic`, `groq`, …)**
- No local hardware needed; you provide an API key.
- Requests leave your machine; usage may incur cost depending on the provider.
- Some presets offer a free tier.

**Offline (`mock`)**
- Deterministic stub for tests, demos, and exercising the loop with no model.

---

## Switching providers

Switching is a config change; no code change required:

```toml
# god_agent.toml
[god-agent]
llm_provider = "ollama"      # was "mock"
llm_model = "llama3.2"
```

Then confirm what is live:

```bash
py -m god_agent.cli providers   # list presets + status
py -m god_agent.cli models      # models offered by the active provider
```

---

## Possible future work (NOT implemented)

- **Parallel / multi-agent execution** and a **shared concurrent memory bus** —
  not implemented; the loop is sequential.
- **Long-context mode** — not implemented.

These are ideas only and do not vary by provider today.

---

## Next steps

1. Pick a preset from the table above.
2. For local use, follow `QUICKSTART_FREE_VARIANT.md`.
3. For the full capability reference, see `UPGRADE_2026_SPEC.md`.
