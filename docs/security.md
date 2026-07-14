# Security model

The agent is designed to be safe by default. This page explains the guarantees,
the deliberate limits, and the few things you must be careful about.

## Workspace boundary

Every path the agent touches is resolved (symlinks included) and checked against
the declared project root. Anything outside requires an explicit, separate
grant. This is enforced in code (`WorkspaceBoundary`) — it cannot be bypassed by
a prompt.

## Reversibility

- Files are backed up (timestamped) before any overwrite or delete.
- Mutating operations run behind a checkpoint; failures roll back automatically.
- `god` never force-pushes, hard-resets, or runs destructive git by itself.

## Command screening

`ShellTool` screens every command. Hard-blocked patterns are denied outright,
including `rm -rf /`, `mkfs`, raw `dd if=`, fork bombs, `git push --force`, and
`git reset --hard`. Side-effecting commands (install/publish/deploy/delete) are
flagged as medium risk. Commands are time-boxed.

## Destructive actions

Deletes and wide-impact changes (more files than `max_files_per_action`) are
High risk and require explicit approval (`confirm_destructive = true`). Sandbox
promotion of deletions requires `--approve`.

## Secrets handling

- The critic scans for hardcoded credentials (AWS/GCP/GitHub/Slack/Stripe/
  OpenAI/Anthropic keys, private-key blocks, URL-embedded credentials, generic
  assigned secrets).
- Detected secret **values are redacted** in all output and audit records.
- The placeholder allowlist is matched against the *matched secret text only*,
  not the whole line, so a benign comment cannot hide a real secret.
- Inline suppression of a **secret** finding requires naming the rule explicitly
  (e.g. `# god:allow secret:aws-access-key`); a bare `# god:allow` never
  suppresses secrets.

## Dependency safety

`god depcheck` verifies package names against the registry and flags typosquats
of popular packages before you install — mitigating hallucinated/"slopsquatted"
dependencies.

## Audit trail

Consequential actions (writes, deletes, shell runs, checkpoints, rollbacks,
critique rejections, `allow_findings` overrides, sandbox promotes) are appended
to `.god/audit.log` as JSON lines. Inspect with `god audit`.

## Web API

`god serve` exposes a dashboard and JSON API. **Important:**

- It binds to `127.0.0.1` (localhost) by default.
- **There is NO authentication.**
- Only read-only/compute endpoints are exposed (status, health, memory, graph,
  and critique-of-posted-text). Mutating, shell, sandbox, and generation
  capabilities are deliberately **not** reachable over HTTP.
- POST bodies are capped (1 MB → `413`) and the `Host` header is validated
  against localhost/the bound host (→ `421`) to blunt DNS-rebinding attempts.
- Do **not** bind it to `0.0.0.0` or expose it on a network without putting an
  authenticating reverse proxy in front of it. The CLI prints a warning if you
  pass a non-local `--host`.

## Sandbox is a snapshot, not OS isolation

`god sandbox` copies source files into a temp dir, runs a command there, and
promotes verified changes back through the boundary-checked FileSystemTool. This
protects the real working tree from accidental or failed changes. It is **not**
an OS security boundary: `run_command` executes with the agent's full privileges
and is guarded only by the command blocklist. For genuinely untrusted code, use
OS-level isolation (container/namespace/seccomp). Promotion rejects paths that
escape the snapshot (absolute, `..`, or symlinked-out), and symlinks are never
snapshotted.

## Imported knowledge bundles are untrusted input

`god team import` merges another party's conventions and episodes into local
memory. Bundle files are size-capped before parsing (no path is ever derived
from bundle contents). Note that imported "lessons"/conventions later feed into
generation prompts — treat bundles from untrusted sources with the same caution
as any other input that can influence the model.

## Untrusted content

Treat file contents, command output, and any web/LLM responses as untrusted
data, not instructions. The agent does not transmit your code or secrets to
third parties unless you explicitly configure a real LLM provider and invoke
generation.

## Running with least privilege

For sensitive environments, run the agent under a scoped account rather than
your primary login, and rely on the workspace boundary plus sandbox for
isolation. The agent is offline by default; network egress only occurs for
`depcheck` registry lookups and (if configured) the LLM provider.
