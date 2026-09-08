# Harness parity

Codex Crew exposes exactly two public backends: Codex and authenticated
OpenAI-compatible profiles. Parity means both reach the shared session lifecycle
without weakening the controls each transport requires.

## Invariants

- **H1 Public set:** only `codex` and `openai_compatible` are selectable.
- **H2 Default:** an empty or unsupported persisted selection resolves to
  `codex`.
- **H3 Factory:** both public ids construct `AcpProvider`; no alternate provider
  bypasses the shared lifecycle.
- **H4 Authentication:** OpenAI-compatible startup requires a non-empty API key.
- **H5 Settings truth:** status reflects validated runtime configuration, not a
  static label.
- **H6 Usage:** both paths use the shared prompt-stat and completion helpers.
- **H7 Positive identity:** security and transport decisions test the selected
  backend positively. They never infer identity from the absence of another id.
- **H8 Process ownership:** both paths use the standard spawn, tracking,
  cancellation, and cleanup code.
- **H9 Environment:** credentials outside the selected backend are scrubbed
  before spawn.
- **H10 Handshake:** each backend owns its ACP protocol version and capability
  translation.
- **H11 Models:** the default model remains `auto`; only an explicit profile or
  backend result chooses a concrete model.
- **H12 UI:** the backend selector, install status, and account controls list
  only public backends.
- **H13 Seam isolation:** backend-specific setup stays inside its positive
  branch and does not add failure points to the other public path.

## Desktop invariant

The desktop build stages the pinned Codex ACP adapter in the bundled Python
tree. The Electron executable is supplied as the Node runner, removing a global
Node dependency from installed use. A build fails when the adapter entry point
or ACP SDK dependency is missing.

## Gate

The focused release gate is the union of the public backend, native Codex tool
gate, OpenAI-compatible profile, adapter, provider factory, usage, and desktop
packaging tests. The repository CI runs that gate and a production frontend
build on every push and pull request.
