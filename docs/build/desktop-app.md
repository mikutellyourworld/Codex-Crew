# Codex Crew desktop app

The Electron shell packages the production React dashboard with a standalone
Python 3.12 backend. End users do not need system Python or Node.

## Build

```bash
bash packaging/build-desktop.sh
```

The build performs these stages:

1. Install dashboard dependencies and run the production Vite build.
2. Provision a standalone Python 3.12 runtime.
3. Install Codex Crew and desktop voice dependencies into that runtime.
4. Install the pinned Codex ACP adapter into the package vendor tree.
5. Stage dashboard assets and verify the backend launcher.
6. Package the platform artifact with electron-builder.

Windows produces an assisted NSIS installer. macOS produces a DMG and zip.
Linux produces AppImage, deb, and rpm artifacts.

## Identity

- Product name: Codex Crew
- Application id: `io.github.mikutellyourworld.codexcrew`
- Windows executable: `codexcrew-desktop`
- Default gateway port: `5486`
- Default data home: `~/.codex-crew`

The icon, tray art, loading screen, installer panels, and disk image background
use the terminal mark in `packaging/branding`.

## Codex adapter

The staged adapter version is pinned in `packaging/build-desktop.sh`. The
installed gateway resolves it from `codex_crew/_vendor/node_modules`. Electron
passes its own executable through `CODEXCREW_NODE_EXECUTABLE`; the ACP client
sets `ELECTRON_RUN_AS_NODE=1` only for the adapter child.

The build fails if the adapter entry point or ACP SDK dependency is absent.

## Updates

The 0.7 public build disables automatic updates. Enable a platform only after a
signed public release feed exists and the update signature and rollback paths
have been verified.
