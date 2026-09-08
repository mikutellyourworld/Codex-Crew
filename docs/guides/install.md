# Install and run Codex Crew

Codex Crew 0.7 supports source installs and packaged desktop builds. Python 3.12
or newer is required for a source install. Node 22 or newer is required only to
build the dashboard and desktop package.

## From source

```bash
git clone https://github.com/mikutellyourworld/Codex-Crew.git
cd Codex-Crew
npm ci --prefix website
npm run build --prefix website
python -m venv .venv
python -m pip install -e ".[voice]"
npm install -g @agentclientprotocol/codex-acp@1.10.0
codex login
codexcrew gateway
```

Open `http://127.0.0.1:5486` after the gateway reports ready.

## Windows source install

```powershell
git clone https://github.com/mikutellyourworld/Codex-Crew.git
Set-Location Codex-Crew
npm ci --prefix website
npm run build --prefix website
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[voice]"
npm install -g @agentclientprotocol/codex-acp@1.10.0
codex login
.\.venv\Scripts\codexcrew.exe gateway
```

The packaged Windows installer carries Python, the dashboard, and the pinned
Codex ACP adapter. See [Windows install](windows-install.md).

## Connect Codex in one click

Open Settings, choose Developer, then select **Agent Backend**. Codex Crew first
looks for a working Codex CLI installation in the normal Windows, macOS, Linux,
npm, Homebrew, and user-bin locations. It validates the executable and connects
the ACP adapter to it automatically; an explicit `CODEX_PATH` remains in control.

If no external CLI is found, choose **Install and connect Codex**. This owner-only
action downloads OpenAI's official installer to a temporary file, runs its
non-interactive mode, verifies the resulting `codex-cli` version, and makes it
available to new Codex sessions without asking an AI to perform the setup. The
adapter's bundled runtime remains available until the external CLI is installed.
Codex sign-in is still completed in Codex's own account flow.

## OpenAI-compatible and FreeChain profiles

Open Settings, choose Providers, and add a profile with:

- a profile name
- an OpenAI-compatible base URL
- a model id
- an API key

The adapter refuses a blank key. Multiple profiles can be stored and switched
without changing the Codex account.

## Isolated data home

Codex Crew uses `~/.codex-crew`. To run an isolated instance, set
`CODEXCREW_HOME` before starting the gateway. Do not place credentials in the
repository or command history.

## Verification

```bash
codexcrew --version
python -m pytest -n 0 test/test_codex_crew_public_contract.py \
  test/test_public_agent_backends.py test/test_codex_tool_gate.py \
  test/test_openai_compatible_adapter.py test/test_drive_sentinel.py
```

## Uninstall

Remove the package or desktop app through the platform's normal package manager.
User data is preserved by default. Remove `~/.codex-crew` only when you intend to
delete sessions, profiles, schedules, and local app state.
