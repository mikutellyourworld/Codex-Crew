# Getting started

## Start the gateway

After installing from source, authenticate Codex and run:

```bash
codex login
codexcrew gateway
```

Open `http://127.0.0.1:5486`.

The Windows desktop installer carries the Python backend, dashboard, and Codex
ACP adapter. Launch Codex Crew from the Start Menu and use the Codex account
control to sign in or switch accounts.

## API-key profiles

Open Settings and add an OpenAI-compatible profile with a name, base URL, model,
and API key. A blank key is rejected. FreeChain-compatible endpoints use this
same profile type.

## Drive Sentinel

Drive Sentinel is available immediately under Apps. It does not scan on startup.
Review scan results before cleanup. Unattended non-dry cleanup is limited to
system-drive targets.
