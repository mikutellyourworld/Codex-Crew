# Security policy

## Supported version

Security fixes target the current 0.7 release line.

## Report a vulnerability

Use the repository's GitHub Security tab and choose **Report a vulnerability**.
That creates a private advisory visible only to the project owner and invited
collaborators.

Do not include API keys, access tokens, account data, private paths, or exploit
details in a public issue.

## Runtime boundary

Codex Crew applies its policy, profile, sandbox, approval, and audit controls to
tool execution. Codex native tools are routed through the generated PreToolUse
gate. OpenAI-compatible profiles require an explicit API key, which is stored in
the local data home and never returned in full by dashboard APIs.
