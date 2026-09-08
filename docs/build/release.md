# Release process

Codex Crew 0.7 is published from a clean, sanitized tree with one public history.

## Required gates

1. Run the focused provider, governance, Drive Sentinel, and public-contract
   backend tests.
2. Build the production dashboard.
3. Run the Electron test suite.
4. Build and install the Windows package on a clean per-user path.
5. Verify the Start Menu shortcut and a real Codex response.
6. Scan the exact outgoing tree for secrets, user paths, private infrastructure,
   stale branding, and unsupported selectable providers.
7. Verify the public repository anonymously after push.

## Versioning

The Python package and desktop package must carry the same stable version. A
stable release must not contain a prerelease suffix.

## Update feed

Automatic updates remain disabled until signed artifacts and a public feed are
available. Do not point a public build at an inherited or private update host.
