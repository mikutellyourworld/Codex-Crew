# LLM provider abstraction

Codex Crew has one provider interface and two public backends. `LLMProvider` in
`providers/base.py` is the consumer-facing contract. `AcpProvider` in
`providers/acp.py` is the factory implementation. The selected transport comes
from `agent.acp_backend`, not from a second provider field.

## Public backend set

`acp_backends.BASELINE_SELECTABLE_BACKENDS` is the product boundary:

- `codex` is the default and uses the Codex ACP adapter.
- `openai_compatible` uses a named OpenAI-compatible profile and an API key.

No other backend is selectable, probed, installed, or displayed by this public
distribution. Persisted values outside this set normalize to `codex` instead of
reaching a dormant inherited compatibility branch.

## Codex

The Codex backend runs one ACP adapter process per session. Desktop builds stage
the pinned adapter under `codex_crew/_vendor/node_modules`; the Electron shell
provides its executable as the Node runner. Source installs can use a project or
global adapter installation. Codex account state remains owned by Codex and is
switched through the account modal rather than copied into Codex Crew.

Every Codex tool call is routed through the native PreToolUse gate assembled by
`codex_tool_gate.py`. This preserves the repository security policy even when a
Codex configuration would otherwise grant a call.

## OpenAI-compatible and FreeChain profiles

`openai_profiles.py` stores multiple named profiles. Each profile has a base
URL, model, and explicit API key. The adapter rejects startup when the key is
blank after trimming. The public UI may label a profile for FreeChain, a local
gateway, or another OpenAI-compatible service, but all use the same authenticated
wire contract.

Profile status shown in Settings is derived from the stored and validated
configuration. It does not claim a connection merely because a row exists.

## Shared behavior

Both backends expose the same `LLMProvider` streaming interface to chat,
schedules, channels, subagents, and apps. Completion events carry context and
usage counters through `AcpPromptStats` and `TurnUsage`. Model defaults remain
`auto`; a model id is selected by the backend or by an explicit profile.

## Tests

The public boundary is pinned by:

- `test/test_public_agent_backends.py`
- `test/test_codex_crew_public_contract.py`
- `test/test_codex_tool_gate.py`
- `test/test_openai_compatible_adapter.py`
- `test/test_openai_compatible_profiles.py`
- `test/test_openai_provider_factory.py`
