# Codex Crew contributor guide

Codex Crew 0.7 is a Python gateway with a React and Electron dashboard. The
backend package is `src/codex_crew`, the browser app is `website`, and the
desktop shell is `website/electron`.

## Product contract

- The public runtime supports only `codex` and `openai_compatible` backends.
- Codex is the default. The desktop package carries the pinned Codex ACP
  adapter and runs it with Electron's Node mode.
- OpenAI-compatible profiles require an explicit API key. Never add a keyless
  profile fallback.
- User data belongs under `~/.codex-crew`, or `CODEXCREW_HOME` when overridden.
- Drive Sentinel is installed and enabled by default. Its unattended cleanup
  remains restricted to system-drive targets, and startup never begins a scan.
- Do not add another selectable model provider without an explicit product
  decision and corresponding tests and documentation.

## Security

- Preserve the existing policy and profile intersection. The tighter rule wins.
- Keep security policy, profiles, admission policy, and computer-use policy in
  the protected home directories for both read and write operations.
- Do not weaken command denial, credential scrubbing, sandboxing, or native
  Codex tool governance.
- Never commit credentials, user-specific paths, private endpoints, or local
  runtime state.

## Development

- Read the owning file under `docs/system-specs` before changing a subsystem.
- Update the owning specification in the same change.
- Use `platform_compat` for process, signal, lock, and other platform-specific
  operations.
- Format only touched Python files. Do not mechanically reformat the full tree.
- Run focused tests while iterating, then the relevant backend, frontend, and
  packaging checks before release.
- Do not edit shipped changelog sections for feature work.

## Verification

```bash
python -m pytest -n 0 test/test_codex_crew_public_contract.py \
  test/test_public_agent_backends.py test/test_codex_tool_gate.py \
  test/test_openai_compatible_adapter.py test/test_openai_compatible_profiles.py \
  test/test_openai_provider_factory.py test/test_drive_sentinel.py
cd website && npm ci && npm run build
cd electron && npm ci && npm test
```

Before publishing, inspect the exact outgoing tree for secrets, user paths,
private infrastructure, stale product names, and unsupported provider choices.
