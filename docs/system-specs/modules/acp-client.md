# ACP client module

## Scope

The ACP layer adapts a session subprocess to `LLMProvider`. The public Codex
Crew 0.7 build exposes two session paths:

1. `codex`, one Codex ACP adapter process per session.
2. `openai_compatible`, one local adapter process per session that calls the
   configured OpenAI-compatible endpoint with an API key.

The selectable registry is authoritative. Compatibility branches inherited
from the upstream codebase are unreachable through public configuration and are
not installed, probed, or presented in the dashboard.

## Codex adapter resolution

`_resolve_codex_acp_bin()` resolves in this order:

1. `CODEX_ACP_BIN`, when it names an existing adapter script or executable.
2. The package-local `_vendor/node_modules` tree.
3. `CODEXCREW_PROJECT_DIR/node_modules` for a source checkout.
4. The app-owned `tools/codex-acp/node_modules` tree created by one-click setup.
5. Managed Node installations and the augmented process path.

A vendored tree is accepted only when both the adapter entry point and its ACP
SDK dependency are present. Desktop packaging pins the adapter version and
stages its complete production dependency closure in the installed backend.
The Electron gateway sets `CODEXCREW_NODE_EXECUTABLE` to the desktop executable.
When that runner is selected, the client adds `ELECTRON_RUN_AS_NODE=1` only to
the adapter child environment.

Before a Codex spawn, `codex_cli.find_codex_cli()` searches a bounded set of
platform-native locations plus the augmented path. It validates every candidate
with a fixed `--version` invocation and accepts only `codex-cli` output. On
Windows this includes OpenAI's versioned per-user install tree and npm shim; on
macOS and Linux it includes the user bin, npm, Homebrew, and system-local paths.
The validated absolute path is sent to `codex-acp` as `CODEX_PATH`. An explicit
operator-supplied `CODEX_PATH` always wins.

The adapter uses Codex account storage. Codex Crew never copies the account
token into its configuration. The account modal lists and activates accounts
through Codex's own runtime surface. If no external CLI is found, the adapter's
bundled runtime remains the non-destructive fallback.

## OpenAI-compatible adapter

The OpenAI-compatible branch starts
`python -m codex_crew.acp_adapters.openai_compatible_server`. The adapter loads
the selected profile, trims the access key, and refuses to start when the key is
empty. It translates ACP prompt and streaming events to the provider's
OpenAI-compatible API.

Profiles are managed through authenticated dashboard handlers. Secret fields
are never returned in full. Multiple profiles may coexist, including profiles
that point at FreeChain-compatible endpoints.

## Tool governance

Codex sessions receive a generated `CODEX_CONFIG` that enables hooks and appends
the Codex Crew PreToolUse command. The gate evaluates every native tool request
against the same security policy used by the rest of the gateway. Gate setup
fails closed before the adapter starts.

Both session paths keep the shared approval, security-hook, audit, process
tracking, sandbox, environment scrub, and cleanup lifecycle. Backend identity is
tested positively. The absence of a different backend is never used as an
authorization decision.

## Usage and completion

ACP usage updates are validated before they reach `AcpPromptStats`. Context
window counters, input and output token counts, cached token counts, credits,
and cost fields are folded into `TurnUsage`. Completion construction uses the
same helper for dashboard, channel, scheduled, and subagent sessions.

## Lifecycle and errors

- Adapter stdout is line-delimited JSON-RPC and is subject to bounded frame
  sizes and timeouts.
- Stderr is drained so a noisy child cannot deadlock the pipe.
- Session prompts are serialized by the existing turn lock.
- Child processes and descendants are tracked for shutdown and orphan cleanup.
- Spawn environments are scrubbed before a child receives them.
- Missing adapters, missing keys, malformed responses, and authentication
  failures surface as actionable provider errors.

## Verification

Resolver, spawn, transport, governance, usage, and public-boundary behavior are
covered by `test/test_acp_client.py`, `test/test_codex_tool_gate.py`,
`test/test_openai_compatible_adapter.py`, and
`test/test_public_agent_backends.py`.
