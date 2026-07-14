# GOD Coding Agent — Documentation

A safety-first, self-verifying agentic coding system. This guide covers
everything you need to install, configure, and use it.

> **Core idea:** the most valuable parts of a coding agent are the
> *deterministic* ones — workspace boundaries, self-verification, reversible
> changes, dependency vetting. They run fully offline (no API key), and can't be
> "forgotten" by a prompt. The LLM is a pluggable layer on top.

## Table of contents

| Guide | What it covers |
|-------|----------------|
| [Installation](installation.md) | Requirements, install methods, verifying the install |
| [Getting started](getting-started.md) | Your first 10 minutes — the commands that matter |
| [CLI reference](cli-reference.md) | Every command, flag, and exit code |
| [Configuration](configuration.md) | `god_agent.toml`, environment variables, model tiers |
| [Workflows](workflows.md) | End-to-end recipes: review, generate, autonomous loops, sandbox, memory, team |
| [LLM providers](providers.md) | Use any model — OpenAI, Groq, Gemini, OpenRouter, Anthropic, Ollama, local, custom |
| [Architecture](architecture.md) | How it works, the modules, and the design philosophy |
| [Security model](security.md) | Boundaries, safe execution, the web API's no-auth posture |
| [Contributing](contributing.md) | Dev setup, tests, coverage, CI, and dogfooding |
| [Troubleshooting & FAQ](troubleshooting.md) | Common issues and answers |

## 60-second overview

```bash
pip install -e .          # install the `god` command
god init                  # adopt it in your project (scaffold config, learn conventions)
god health                # unprompted: what should I fix?
god critique src/app.py   # deterministic secrets/vuln/stub review
god verify --command "pytest"   # run tests and report an HONEST verdict
god loop "keep it green"  # bounded autonomous quality loop
```

Everything works offline by default via a deterministic mock LLM provider. Wire
any real model — OpenAI, Groq, Gemini, OpenRouter, Anthropic, or a local one
(Ollama/LM Studio) — when you want generation. See
[LLM providers](providers.md).

## Requirements at a glance

- **Python 3.11+** (uses `tomllib`, `match`, modern typing)
- **git** (optional — enables `god who` and history features)
- **No third-party runtime dependencies** — works with every LLM (hosted or
  local) over the standard library; no provider SDK needed
