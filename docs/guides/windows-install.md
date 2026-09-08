# Windows installation

The Windows desktop package is an assisted per-user NSIS installer. It installs
Codex Crew under the current user, creates a Start Menu shortcut, and does not
delete `~/.codex-crew` during uninstall.

## Build locally

Use Git Bash from the repository root:

```bash
bash packaging/build-desktop.sh
```

The build produces the installer under `website/electron/dist`. It includes the
Python backend, production dashboard, Drive Sentinel, and the pinned Codex ACP
adapter. The desktop shell uses Electron's Node mode to run the adapter.

## Install and sign in

1. Run the generated setup executable.
2. Launch Codex Crew from the Start Menu.
3. Open the Codex account control and sign in or choose an existing Codex
   account.
4. Send a short prompt and confirm that text and usage counters appear.

For an API-key provider, add an authenticated OpenAI-compatible or FreeChain
profile in Settings and select it for the session.

## Data and ports

- Data home: `%USERPROFILE%\.codex-crew`
- Gateway: `http://127.0.0.1:5486`
- Drive Sentinel app backend: a free loopback port selected from the app-manager
  range at launch

The product identity and data home are separate from any upstream installation.

## Updates

Automatic updates are disabled in 0.7 until this public repository publishes a
signed release feed. Install a newer signed package over the existing per-user
installation when one is available.
