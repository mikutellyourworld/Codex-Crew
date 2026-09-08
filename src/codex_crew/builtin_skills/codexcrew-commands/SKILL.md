---
name: codexcrew-commands
description: Complete CLI reference for Codex Crew commands. Use for help, commands, setup, how to, what can you do, getting started, onboarding.
always: false
triggers: help, commands, setup, gateway, how to, what can you do, getting started, onboard, browse, auth, doctor, cron, artifact, memory, snapshot, eval, security, codexcrew pod, pod up, pod down, pod ls, pod status, pod logs, pod provision, pod install, pod token
inject_on_trigger: false
---
# Codex Crew CLI Reference

## Setup & System

| Command | Description |
|---------|-------------|
| `codexcrew setup` | Interactive wizard — install agent config (messaging channels connect later) |
| `codexcrew setup --slack` | Also run the guided Slack credential setup (opt-in; ignored with `--agent-only`) |
| `codexcrew setup --agent-only` | Only install kiro-cli agent config, skip the other wizard steps |
| `codexcrew setup --clean` | Fresh install — don't merge from existing config |
| `codexcrew doctor` | Verify Codex Crew setup (checks all dependencies) |
| `codexcrew doctor --bundle` | Collect logs + crash reports into a redacted diagnostics zip |
| `codexcrew update` | Update Codex Crew to the latest version |
| `codexcrew update approve` | Approve a pending in-app update armed from the dashboard |
| `codexcrew update --force` | Discard local commits when a git checkout has diverged from upstream (git installs only) |
| `codexcrew --version` | Print installed version |
| `codexcrew sandbox status` | Report whether this launch is covered by the userns AppArmor profile |
| `codexcrew sandbox install-profile` | Attach the profile to this app (sudo; `--path P` for an explicit executable) |
| `codexcrew sandbox remove-profile` | Unload and remove the profile (sudo) |

`update --force` is destructive on a git install: the hard reset discards local
commits, recoverable only from `git reflog`. The `sandbox` verbs matter only on
hosts with `kernel.apparmor_restrict_unprivileged_userns=1` (Ubuntu 23.10+ and
derivatives) and are no-ops everywhere else; `--path` is refused for
world-writable locations and for shared interpreters such as `/usr/bin/python3`,
which would over-grant.

## Gateway (Server)

| Command | Description |
|---------|-------------|
| `codexcrew gateway` | Start dashboard + Slack gateway |
| `codexcrew gateway --slack-only` | Slack only — skip dashboard web server |
| `codexcrew gateway --no-crons` | Skip cron scheduler |
| `codexcrew gateway --port 9999` | Override dashboard port |
| `codexcrew gateway --port auto` | OS-assigned ephemeral port |
| `codexcrew gateway --no-open` | Don't auto-open dashboard URL in browser |
| `codexcrew gateway --approval reads` | Auto-approve read-only tools |
| `codexcrew gateway --approval yolo` | Auto-approve all tools (requires isolated CODEXCREW_HOME) |
| `codexcrew gateway --approval interactive` | Prompt for every tool (default) |
| `codexcrew gateway --seed FIXTURE` | Seed $CODEXCREW_HOME from fixture before starting (dev) |
| `codexcrew gateway --seed-replace` | Wipe a non-empty target home and re-seed it (paired with `--seed`) |
| `codexcrew gateway --no-tunnel` | Never publish a tunnel for this process's whole life, whatever `tunnel.enabled` says. Scoped to TUNNELS: it does not change where the dashboard binds |
| `codexcrew gateway --json-ready` | Print one `CODEXCREW_READY:{...}` line (port, token, pid, CODEXCREW_HOME) once the dashboard is bound |
| `codexcrew gateway --test-mode` | Alias for `--port auto --no-open --json-ready --approval reads` |
| `codexcrew stop` | Stop a running gateway |
| `codexcrew stop --port 9999` | Stop gateway on specific port |
| `codexcrew restart` | Restart gateway (service-aware) |
| `codexcrew status` | Show runtime stats (uptime, sessions, crons, lessons) |

The token in a `--json-ready` line grants dashboard access for up to 20 hours, so
captured stdout from a test harness is a credential: keep it out of logs and
transcripts.

## Service Management

| Command | Description |
|---------|-------------|
| `codexcrew service install` | Install and start as system service (sudo on Linux) |
| `codexcrew service uninstall` | Stop and remove system service |
| `codexcrew service status` | Show service status (systemctl/launchctl) |
| `codexcrew logs` | Show gateway logs (last 100 lines) |
| `codexcrew logs -f` | Follow (tail) live log output |
| `codexcrew logs -n 50` | Show last N lines |

## Pods (Isolated Worktree Test Instances)

Ephemeral, full-stack Codex Crew gateways — one per feature worktree — that run on
their own port + isolated `CODEXCREW_HOME` and never touch the live `:5486`
gateway or shared data. Linux `systemd --user` only. `<wt>` is a worktree name
(resolved by directory basename or `feat/<name>` branch convention).

| Command | Description |
|---------|-------------|
| `codexcrew pod install` | Lay down the systemd --user template unit (once per machine) |
| `codexcrew pod provision <wt>` | Build the worktree's venv + SPA dist (the on-ramp) |
| `codexcrew pod up <wt>` | Bring up an isolated pod (auto-builds venv; fails if dist missing) |
| `codexcrew pod up <wt> --provision` | Provision (venv + dist build) then bring up |
| `codexcrew pod up <wt> --json` | Bring up and print `{base_url, token, port}` as JSON |
| `codexcrew pod ls` | List running pods |
| `codexcrew pod status <wt>` | Up/down + health for one pod |
| `codexcrew pod token <wt>` | (Re)mint a dashboard token for a running pod |
| `codexcrew pod url <wt>` | Print the pod's base URL |
| `codexcrew pod logs <wt> -n N` | Tail the pod's journal |
| `codexcrew pod down <wt>` | Evict the pod and delete its isolated HOME |
| `codexcrew pod prune` | Bulk-reclaim orphaned pod HOMEs (`--older-than 3d` by default, `--all`, `--dry-run`, `--json`) |
| `codexcrew pod scenarios` | List the seed scenarios `pod up --seed <scenario>` accepts (`--json`) |
| `codexcrew pod exec <wt> -- <args>` | Run a codexcrew command against a pod, using the pod's own binary and data |
| `codexcrew pod api <wt> <METHOD> <path>` | Call a running pod's HTTP API with its own token; prints `{name, method, path, status, ok, body}` |
| `codexcrew pod api <wt> POST config --data '{…}' --allow-write` | GET and HEAD are permitted by default; every other method needs `--allow-write` |

**Platform:** Linux only. On macOS/Windows every systemd-touching verb refuses
with a one-line message pointing at `./dev-backend.sh` — it does not crash, and
`pod install` writes no unit file. `pod url` works anywhere (pure computation).

Port derivation: `base + (cksum(name) % 199) + 1` (base `7810` → `7811..8009`).
Override with `PORT=` in `~/.codex-crew/pods/<name>.env`.

`codexcrew pod --help` lists every verb and its flags.

## Dashboard Access

| Command | Description |
|---------|-------------|
| `codexcrew token` | Print a dashboard URL with auth token (TTL: 20h) |
| `codexcrew token --ttl 1h` | Token with custom TTL (e.g. 1h, 30m) |
| `codexcrew logout` | Revoke all active dashboard sessions |
| `codexcrew manifest` | Generate Slack app manifest with your alias |
| `codexcrew manifest --url` | Print one-click Slack app creation URL |

## Chat

| Command | Description |
|---------|-------------|
| `codexcrew chat` | Interactive chat (REPL mode) |
| `codexcrew chat -m "message"` | Single message (non-interactive) |
| `codexcrew chat --model auto` | Let the backend choose an available model |

## Browsing (`browser` MCP tool, then `playwright-cli`)

Browsing is not a `codexcrew` subcommand. The primary path is the **`browser` MCP
tool**, which drives the dashboard's built-in Browser panel in-process
(`op=navigate|snapshot|click|type|press_key|hover|select_option|screenshot|wait_for|back|console`).
It refuses a loopback, private, or link-local target, and it needs a native panel
serving the session.

`playwright-cli` is the fallback: no native panel (a remote gateway, or a
plain-browser dashboard), an attached logged-in browser, saved storage state, and
the full operate verb set. It is available when the binary is on `PATH`.
**Settings → Browser** installs it with one click (and holds the optional attach
token); the equivalent by hand is `npm install -g @playwright/cli@latest`
(Node.js 20 or newer).

| Command | Description |
|---------|-------------|
| `playwright-cli open <url>` | Open a page (prints URL, title, and a snapshot path) |
| `playwright-cli snapshot` | Write the accessibility tree to a YAML file, print its path |
| `playwright-cli click <ref>` / `fill <ref> <text>` | Act on an element from a snapshot |
| `playwright-cli screenshot [ref]` | Write a PNG, print its path. `[ref]` is an ELEMENT, not a path; do not pass `--filename` (it resolves against the CWD and is not auto-approved) |
| `playwright-cli state-save` / `state-load <file>` | Save or restore a logged-in session. Bare `state-save` writes into the service's own directory; both a name and `state-load` prompt for approval, because each names a local path |
| `playwright-cli attach --extension` | Drive the user's own running Chrome, with their logins |
| `playwright-cli show --port <n> --host 127.0.0.1` | Serve the CLI's dashboard for the Browser panel |

**Browsing workflow:** load the `web-browse`, `web-verify`, or `browser-auth`
skill for the shape of the task, then:
1. `command -v playwright-cli`. Absent means browsing is unavailable: read the page
   with `web_fetch` and tell the user the install command.
2. `playwright-cli open <url>`. The printed URL and title usually confirm the page
   without reading anything else.
3. Read the snapshot YAML at the printed path only when you need the tree, for
   example before clicking. Refs like `[ref=e5]` belong to that snapshot, so
   re-snapshot after any page change.
4. On a login redirect, the session is absent or expired: `state-load` a saved
   session, or ask the user to sign in in the Browser panel and `state-save` it.

**No npm access (internal registry, air-gapped host):** detection is **PATH-based**
-- `playwright-cli` on `PATH` is all that matters, so ANY install route works and the
Settings button is a convenience, not the only one. In order of likelihood:

1. Most internal registries proxy npmjs, so the plain install already works.
2. Force the public registry for this one package:
   `npm install -g @playwright/cli --registry=https://registry.npmjs.org`.
3. **An internal registry that requires a login the user does not have** (the
   common Amazon-internal / corporate case). Install into a user-owned prefix
   against the public registry, ignoring the corporate `.npmrc` for this one
   command, then put the binary on `PATH`:

   ```bash
   NPM_CONFIG_USERCONFIG=/dev/null \
     npm install --prefix ~/.local/share/playwright-cli \
     --registry=https://registry.npmjs.org @playwright/cli@0.1.18
   mkdir -p ~/.local/bin
   ln -sf ~/.local/share/playwright-cli/node_modules/.bin/playwright-cli \
     ~/.local/bin/playwright-cli
   ```

   Two caveats worth stating to the user rather than burying: `~/.local/bin` has
   to be **on `PATH`** or Codex Crew still reports "not installed" (detection is
   `PATH` + the Node bin dirs, nothing else); and `NPM_CONFIG_USERCONFIG=/dev/null`
   deliberately ignores their employer's registry configuration, which is their
   call to make, not ours to assume.
4. Air-gapped: `npm pack @playwright/cli` on a connected machine, copy the
   `.tgz` over, then `npm install -g ./playwright-cli-<version>.tgz`. Note the
   tarball alone is not runnable -- it needs its `playwright` /
   `playwright-core` dependencies resolved too.

What does **not** substitute for it: `pip install playwright` and
`dotnet tool install Microsoft.Playwright.CLI` install a DIFFERENT tool -- the
`playwright` browser-installer/codegen CLI, not `@playwright/cli` (binary
`playwright-cli`, its own 0.x line, which depends on `playwright@1.63.0-alpha`).
Switching to yarn, pnpm or bun hits the same registry, so it only helps when the
`npm` client itself is missing. And there is **no standalone binary**: the
upstream GitHub release carries no build assets and `playwright-cli.js` starts
with `#!/usr/bin/env node`, so Node.js 18+ is required no matter how it is
fetched.

**Approval:** page-scoped verbs run without prompting the user, because installing
the CLI is itself the consent. Verbs that reach the local machine still prompt on
purpose -- `eval`, `run-code`, `upload`, `state-load`, a named `state-save`, and the
installers. Let the user approve those rather than rewriting the command to dodge
the prompt.

The full verb list is in the skill `playwright-cli install --skills agents --global`
writes.

## Autonomous Task Runner

| Command | Description |
|---------|-------------|
| `codexcrew run TASK.md` | Run a task spec file (auto-resumes from checkpoint) |
| `codexcrew run TASK.md --fresh` | Start from scratch, ignore checkpoint |
| `codexcrew run TASK.md --no-test` | Skip build/test verification after each step |
| `codexcrew run TASK.md --timeout 3600` | Set global timeout in seconds |
| `codexcrew run TASK.md --name "My Task"` | Override human-readable task name |

## Subagents

| Command | Description |
|---------|-------------|
| `codexcrew spawn run "task"` | Spawn a background subagent (wait for result) |
| `codexcrew spawn run --async "task"` | Fire-and-forget subagent |
| `codexcrew spawn list` | List active subagents |

## Cron Jobs

| Command | Description |
|---------|-------------|
| `codexcrew cron list` | List all cron jobs |
| `codexcrew cron add NAME MESSAGE --every 3600` | Add job with interval (seconds) |
| `codexcrew cron add NAME MESSAGE --cron "0 9 * * MON-FRI"` | Add job with cron expression |
| `codexcrew cron add NAME MESSAGE --agent myagent` | Add job for specific agent |
| `codexcrew cron add NAME MESSAGE --approval-mode auto` | Add job with auto tool approval |
| `codexcrew cron add NAME MESSAGE --channel C123456` | Post results to Slack channel |
| `codexcrew cron update JOB_ID --message "new msg"` | Update job message |
| `codexcrew cron update JOB_ID --agent myagent` | Update job agent |
| `codexcrew cron update JOB_ID --approval-mode auto` | Set auto-approval |
| `codexcrew cron update JOB_ID --approval-mode default` | Reset approval to default |
| `codexcrew cron remove JOB_ID` | Remove a cron job |
| `codexcrew cron pause JOB_ID` | Pause a cron job |
| `codexcrew cron resume JOB_ID` | Resume a paused job |
| `codexcrew cron adopt JOB_ID --session-of SESSION` | Give the job an owning chat session, so that session manages it and receives its results |
| `codexcrew cron adopt JOB_ID --release` | Clear the owning session, returning the job to CLI/dashboard-only management |
| `codexcrew cron trigger JOB_ID` | Trigger a job immediately |
| `codexcrew cron preview SCRIPT` | Run a script cron locally with real MCP tools; notifications are printed, not delivered |
| `codexcrew cron preview SCRIPT -m "msg" -e K=V` | Preview with an input message / extra env vars |

## Learning & Memory

| Command | Description |
|---------|-------------|
| `codexcrew learn list` | List all saved lessons |
| `codexcrew learn add "rule text"` | Save a lesson (category: knowledge) |
| `codexcrew learn add "rule text" --category tool` | Save with category (tool/preference/knowledge) |
| `codexcrew learn add "rule text" --negative "avoid X"` | Save with negative example |
| `codexcrew learn remove "query"` | Remove lessons matching substring |
| `codexcrew memory list` | Show semantic memory entries |
| `codexcrew memory search "query"` | Search episodic memories |
| `codexcrew memory stats` | Show memory statistics |
| `codexcrew memory audit` | Scan memory for suspicious content |
| `codexcrew memory export` | Export all memory to JSON (stdout) |
| `codexcrew memory export -o file.json` | Export to file |
| `codexcrew memory import file.json` | Import memory from JSON |
| `codexcrew memory migrate` | Migrate legacy markdown memory to vector store |
| `codexcrew memory show [preferences\|projects\|history]` | Show the markdown memory layer (default: all three; `--format md\|json`, `--since YYYY-MM-DD` for history) |
| `codexcrew knowledge dedup` | Preview cross-source duplicate knowledge documents (dry-run) |
| `codexcrew knowledge dedup --apply` | Actually collapse the duplicates |
| `codexcrew consolidate` | List sessions with unconsolidated messages |
| `codexcrew consolidate SESSION_KEY` | Force consolidate a session (triggers auto-skill extraction) |
| `codexcrew consolidate --all` | Consolidate all pending sessions |

## Artifacts

LLM-generated UI components (widgets, HTML, markdown, SVG, JSON, text).

| Command | Description |
|---------|-------------|
| `codexcrew artifact list` | List all artifacts |
| `codexcrew artifact list --tag ops --kind widget` | Filter by tag and kind |
| `codexcrew artifact list -q "CR"` | Substring filter on name |
| `codexcrew artifact show SLUG` | Print artifact content |
| `codexcrew artifact show SLUG --version 2` | Show specific version |
| `codexcrew artifact show SLUG --meta` | Show metadata as JSON |
| `codexcrew artifact save --name "My Widget" --content-file widget.html` | Save new artifact |
| `codexcrew artifact save --name "X" --content "..." --tags ops,cr` | Save with inline content |
| `codexcrew artifact update SLUG --content-file widget.html` | Update artifact content |
| `codexcrew artifact update SLUG --name "New Name" --tags ops` | Rename/retag |
| `codexcrew artifact versions SLUG` | List version numbers |
| `codexcrew artifact delete SLUG` | Delete artifact and all versions |

## Agents & Workspaces

| Command | Description |
|---------|-------------|
| `codexcrew agent list` | List Codex Crew agents |
| `codexcrew agent create --name NAME` | Create a new agent |
| `codexcrew agent create --name NAME --kiro-agent codexcrew --workspace default` | Full options |
| `codexcrew agent update NAME --kiro-agent new-agent` | Update agent settings |
| `codexcrew agent delete NAME` | Delete an agent |
| `codexcrew agent reset-model [--agent codexcrew]` | Clear a pinned model so the agent tracks the shipped default |
| `codexcrew workspace list` | List workspaces |
| `codexcrew workspace create --name NAME --dir DIRNAME` | Create workspace (`--dir` is a **name under the data home**, not an absolute path) |
| `codexcrew workspace create --name NAME --copy-from existing` | Copy from existing |
| `codexcrew workspace update NAME --dir DIRNAME` | Update workspace dir (same containment rule) |
| `codexcrew workspace delete NAME` | Delete workspace |

**On the CLI**, `--dir` must resolve to a **strict descendant** of
`$CODEXCREW_HOME` (default `~/.codex-crew`): anything landing outside — `/tmp/x`,
`../x`, `~/x` — is refused with a SEL `denied` audit event, and so is the data
home **root itself** (in any spelling: absolute, `~/.codex-crew`, `.`, or empty),
since a workspace there would put agent-writable memory on top of `config.json`
and `.env`. The test is containment, not "is it absolute": an absolute path
landing *under* the home is accepted, since it resolves where the relative form
would. Pass `workspace-myproject`, not `/path/to/dir`.

Note the surface difference: the **dashboard** `POST /api/workspaces` DOES accept
an absolute `dir` (screened by `is_sensitive_path`, so `~/.ssh` / `~/.aws` /
keystone paths are still refused). The CLI is the stricter of the two.

## Apps

| Command | Description |
|---------|-------------|
| `codexcrew app list` | List installed apps |
| `codexcrew app install /path/to/app-dir` | Install app from local directory (needs app.json) |
| `codexcrew app enable NAME` | Enable an installed app |
| `codexcrew app disable NAME` | Disable an installed app |
| `codexcrew app uninstall NAME` | Uninstall an app and preserve its data directory |
| `codexcrew app uninstall NAME --purge-data` | Uninstall and explicitly delete the app data directory |
| `codexcrew app info NAME` | Show app details |
| `codexcrew app init NAME` | Scaffold a new app (kebab-case name) |
| `codexcrew app init NAME --backend --ui --cron` | Scaffold with backend, UI, and sample cron |
| `codexcrew app dev NAME` | Toggle an app into dev mode (no-store UI serving + live reload on file change) |
| `codexcrew app dev NAME --off` | Leave dev mode |
| `codexcrew app mcp NAME` | Run an app's MCP server on stdio (spawned by kiro-cli, not for humans) |

## Configuration

| Command | Description |
|---------|-------------|
| `codexcrew config get` | Show all config |
| `codexcrew config get agent.provider` | Get specific value (dot-separated key) |
| `codexcrew config set dashboard.url http://localhost:5486` | Set a config value (port is the CODEXCREW_PORT env var, not a config key) |
| `codexcrew config set --file config.json` | Load full config from JSON file |
| `codexcrew config edit` | Open config in $EDITOR |
| `codexcrew config defaults [KEYS…]` | Review stored values that still hold a superseded default |
| `codexcrew config defaults [KEYS…] --adopt` | Remove those stored keys so the current defaults apply |
| `codexcrew config defaults [KEYS…] --keep` | Record the stored values as intentional and stop reporting them |

## Profiling (debug-only)

Off unless `CODEXCREW_DEBUG=1` is set; the CLI is the only entry point. Emits folded
stacks (open in speedscope / flamegraph.pl). See `docs/architecture/design-notes/profiling.md`.

| Command | Description |
|---------|-------------|
| `CODEXCREW_DEBUG=1 codexcrew perf sample --call mod:fn` | Profile that callable in-process (no extra dependency) |
| `CODEXCREW_DEBUG=1 codexcrew perf sample` | Attach to the running gateway (needs `pip install "codexcrew[perf]"`) |
| `CODEXCREW_DEBUG=1 codexcrew perf sample --pid 1234 --seconds 30` | Attach to a specific PID for N seconds (1-300) |
| `... --interval 0.002` | Seconds between samples (0.001-1.0, default 0.005) |
| `... --output /tmp/p.folded` | Where to write the profile (default `./codexcrew-profile.folded`) |
| `CODEXCREW_DEBUG=1 codexcrew desktop metrics` | Per-process CPU/memory of the **Electron** app (`--json`, `--top N`, `--path`) |

On macOS the attach path additionally needs elevated privileges (the OS denies
`task_for_pid`), so it may require sudo; `--call` needs neither py-spy nor sudo.

`desktop metrics` reads a recording rather than querying the app: `getAppMetrics()`
is Electron-main-only, so the app samples itself into an artifact when **started**
with `CODEXCREW_DEBUG` set. Setting the variable only for the CLI does not make an
already-running app record -- restart it.

## Security & Eval

| Command | Description |
|---------|-------------|
| `codexcrew secrets import` | Dry-run the migration of plaintext `.env` credentials into the encrypted vault |
| `codexcrew secrets import --apply` | Store the secrets and rewrite `.env` to `secret://` refs |
| `codexcrew telemetry status` | Show exactly what the anonymous beacon sends, and whether it will |
| `codexcrew telemetry disable` | Turn the anonymous beacon off permanently |
| `codexcrew telemetry enable` | Turn the anonymous beacon back on |
| `codexcrew security audit` | Scan conversation history for suspicious tool usage |
| `codexcrew security deny-list` | Show active deny patterns |
| `codexcrew security events` | Show recent security event log entries (last 20) |
| `codexcrew security events -n 50` | Show N entries |
| `codexcrew security verify` | Verify security event log HMAC integrity |
| `codexcrew eval` | Run smoke test evaluation (~30s) |
| `codexcrew eval memory_recall_basic` | Run specific scenario by name |
| `codexcrew eval --all` | Run all scenarios (slow) |
| `codexcrew eval --judge` | Enable LLM judge scoring |
| `codexcrew bench list` | Show the available corpora and what is cached |
| `codexcrew bench fetch CORPUS` | Download a corpus into the local cache and verify its checksum |
| `codexcrew bench retrieval` | Measure retrieval recall/nDCG against a corpus (deterministic) |
| `codexcrew bench kb-retrieval` | Measure Knowledge Library recall/MRR/nDCG against a golden set (deterministic) |
| `codexcrew bench compare A B` | Diff two saved JSON reports; refuses to attribute a delta when the runs disagree on corpus |

## Governance Policy

Inspects the two-level security model (`effective = POLICY ∩ PROFILE`,
tightest-wins). Six verbs: five are read-only, and `fetch` writes — it applies the
central policy when the download is usable. The enterprise ceiling is never
hand-edited through the CLI (its files are keystone-fenced so the agent cannot read
or write them).

| Command | Description |
|---------|-------------|
| `codexcrew policy show` | Show the effective enterprise security policy |
| `codexcrew policy show --ids` | List each denied-command category's rule ids (default: counts only) |
| `codexcrew policy validate` | Load-check the policy + all profiles |
| `codexcrew policy explain SCOPE ITEM` | Explain one tool/scope decision for a surface |
| `codexcrew policy explain SCOPE ITEM --session-key K --agent A --app APP` | Scope the explanation to a surface |
| `codexcrew policy profile NAME` | Show a profile by name |
| `codexcrew policy source` | Show whether this host fetches its policy from a central source |
| `codexcrew policy fetch` | Fetch the central policy now and apply it if usable (`--force` re-downloads, ignoring cached validators) |

## Cloud (Bring-Your-Own AWS)

Runs Codex Crew on an EC2 instance in **your own** AWS account; credentials are
resolved by the `aws` CLI and never stored by Codex Crew. All verbs accept
`--profile` / `--region`; the single-instance verbs also accept `--tag`
(defaults to the last launched instance).

| Command | Description |
|---------|-------------|
| `codexcrew cloud doctor` | Check cloud prerequisites + AWS reachability |
| `codexcrew cloud launch` | Provision + configure an instance (interactive) |
| `codexcrew cloud launch --size TIER -y` | Non-interactive launch at a size tier |
| `codexcrew cloud launch --new` | Create a separate new instance instead of resuming the saved one |
| `codexcrew cloud launch --keep-on-failure` | On bootstrap failure keep the instance for inspection |
| `codexcrew cloud list` | List your Codex Crew cloud instances |
| `codexcrew cloud status` | Show one instance's state |
| `codexcrew cloud connect` | Open the dashboard over an SSM tunnel |
| `codexcrew cloud tunnel` | Open the dashboard SSM tunnel (standalone alias of connect) |
| `codexcrew cloud connect --local-port N --no-browser` | Forward to a specific local port, no browser |
| `codexcrew cloud login` | Sign kiro-cli in on the instance (fixes "not logged in" chat errors) |
| `codexcrew cloud logout` | Sign kiro-cli out on the instance, to switch Kiro account |
| `codexcrew cloud stop` | Stop the instance (pause billing) |
| `codexcrew cloud start` | Start a stopped instance |
| `codexcrew cloud destroy` | Remove the instance and ALL its AWS resources |
| `codexcrew cloud destroy --dry-run` | Show the delete command without running it |
| `codexcrew cloud iam-policy` | Print the least-privilege IAM policy to apply |
| `codexcrew cloud iam-boundary` | Pre-create the immutable permissions boundary (admin, one-time) |

## Tailnet (Tailscale)

Publishes this dashboard on your tailnet and trusts its origin, so a device on the
tailnet reaches it without a public tunnel.

| Command | Description |
|---------|-------------|
| `codexcrew tailnet status` | Show whether the dashboard is published and trusted on your tailnet |
| `codexcrew tailnet up` | Publish the dashboard on your tailnet and trust its origin |
| `codexcrew tailnet down` | Stop publishing the dashboard on your tailnet |
| `... --port N` | Name the dashboard port; `up` needs it whenever discovery has no verified port |

`up` publishes only a port it has evidence for: an explicit `--port`, `CODEXCREW_PORT`,
or the running gateway's run marker. With none of those — the gateway is down, the
marker is unreadable, or several gateways are up, where the marker deliberately
refuses — `up` refuses rather than falling back to the configured `dashboard.url`
port, because nothing is verified to answer there and `tailscale serve` would expose
whatever does. Start the gateway and re-run, or name the port yourself. `status` and
`down` do accept the configured port: one only reports, and the other checks mount
ownership before removing anything.

## Computer Use (Desktop Automation)

Default-OFF behind a keystone enable (`~/.codex-crew/computer_use.json`, **not**
`config.json`). macOS and Windows carry the full tool set; Linux answers a typed
unsupported refusal. On Windows there is no per-process input, so a keystroke takes
the user's keyboard focus and a coordinate click moves their real cursor — say so
rather than reporting a silent success. These are human debug/diagnostic twins of the
`computer_*` MCP tools — the agent uses the MCP tools, not these.

| Command | Description |
|---------|-------------|
| `codexcrew computer doctor` | Report platform support, keystone enable state, and the advisory Accessibility / Screen Recording probe |
| `codexcrew computer doctor --json` | Same as JSON |
| `codexcrew computer apps` | List on-screen applications the accessibility layer can address |
| `codexcrew computer call TOOL k=v …` | Run ONE computer-use tool through the same gated chokepoint the agent uses |
| `codexcrew computer call --calls '[…]'` | Run a JSON array of calls in a SINGLE process, so `element_index` values stay resolvable |

## Snapshot & Restore

| Command | Description |
|---------|-------------|
| `codexcrew snapshot` | Create a portable backup of Codex Crew state |
| `codexcrew snapshot /path/to/dir` | Snapshot to specific output directory |
| `codexcrew snapshot --keep 7` | Keep N most recent snapshots (default: 7) |
| `codexcrew snapshot --list` | List existing snapshots |
| `codexcrew restore` | Restore from most recent snapshot |
| `codexcrew restore /path/to/snap.tar.gz` | Restore from specific snapshot |
| `codexcrew restore --mode replace` | Replace mode (default) |
| `codexcrew restore --mode merge` | Merge mode |
| `codexcrew restore --dry-run` | Preview without applying |
| `codexcrew restore --components memory,crons` | Restore specific components only |
| `codexcrew restore --list-components` | List restorable components |
| `codexcrew restore --force` | Restore even if gateway is running |

## Slack Commands

### All Allowed Users
| Command | Description |
|---------|-------------|
| `!dashboard` | Get a presigned dashboard link (DM'd to you). Link expires in 5 min; session lasts 1h |
| `!dashboard 2h` | Dashboard link with custom duration (accepts `<N>h` or `<N>m`, max 6h) |
| `/codexcrew dashboard` | Same via slash command |
| `/codexcrew help` | List available slash sub-commands |
| `!stop` | Force-halt the current agent turn (bypasses semaphore, cancels active task) |
| `status` | Show runtime stats |
| `ping` | Auto-reply `pong` |
| `cron list` | List cron jobs |
| `run <path>` | Run an autonomous task from a spec file |

### Owner-Only Slash Commands
| Command | Description |
|---------|-------------|
| `/codexcrew yolo` | Toggle YOLO mode (auto-approve all tool calls) |
| `/codexcrew agent` | Show agent selector dropdown |
| `/codexcrew agent <name>` | Switch to named agent |
| `/codexcrew voice` | Open TTS voice settings modal |
| `/codexcrew config` | Open config modal |
| `/codexcrew users` | Open allowed users management modal |
| `/codexcrew channels` | Open tracked channels modal |
| `/codexcrew sessions` | List recent sessions with resume/end buttons |

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `CODEXCREW_HOME` | Override config/data directory | `~/.codex-crew` |
| `CODEXCREW_PORT` | Override dashboard port | `5486` |
| `CODEXCREW_PROJECT_DIR` | Override agent config/skills directory | Auto-detected |
| `CODEXCREW_POD_REPO` | Repo to resolve worktree names from | invoking cwd |
| `CODEXCREW_POD_ROOT` | Isolated pod HOMEs (nuked on stop) | `~/.codexcrew-pods` |
| `CODEXCREW_POD_BASE_PORT` | Port derivation base | `7810` |
| `CODEXCREW_POD_LIVE_PORT` | Port a pod must never bind | `5486` |
