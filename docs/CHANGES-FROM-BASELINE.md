# Codex Crew 0.7 public fork

This file records the approved public-fork scope and the implementation checks
that must remain true at release time. It replaces the workstation-specific
baseline notes inherited from the development branch.

## Product contract

- Product name: **Codex Crew**
- Release: **0.7.0**
- Python package and executable: `codex_crew` and `codexcrew`
- Data home: `~/.codex-crew`, independently overrideable with
  `CODEXCREW_HOME`
- Desktop identity: a distinct application id, protocol, executable, installer,
  and default port so Codex Crew can run beside the upstream application
- Public repository: `mikutellyourworld/Codex-Crew`

Codex Crew is a personal agent dashboard and unattended task runner centered on
the Codex CLI. It keeps the existing chat, scheduling, memory, tools, messaging,
app, governance, and Windows packaging capabilities while replacing the public
runtime selection surface.

## Provider contract

The only selectable backends are:

1. **Codex**, using the installed Codex CLI and its normal account session.
2. **OpenAI-compatible**, using an explicit API key or access key. The bundled
   FreeChain profile is the first ready-made endpoint, and operators may add
   multiple custom profiles.

Kiro CLI, KAS, Claude, Kimi, and other harnesses are not selectable, installed,
probed, or offered as fallbacks. Model defaults stay `auto`; a user-selected
model is never silently replaced.

Codex tool calls continue through Codex Crew's own governance gate. Provider
usage and context counters flow through the normal session-history and dashboard
paths. A missing usage bucket renders as zero instead of breaking a fresh
dashboard.

## Visual direction

The retained dashboard is rebranded, not structurally redesigned. The mark is a
small terminal window with a prompt cursor, crisp enough for installer, desktop,
favicon, sidebar, and package use. Product-owned copy uses Codex Crew naming.
Existing accessibility, localization, component, and theme contracts stay in
force.

## Bundled app: Drive Sentinel

Drive Sentinel is the public, default-enabled disk safety app derived from the
portable parts of DiskWarden. It is a distinct product surface with:

- app id `drive-sentinel`
- its own icon, state names, schedule names, routes, and loopback port
- a terminal-green and amber operational presentation
- measure-first drive inspection
- explicit rescans before cleanup becomes available
- cleanup locked until the selected drive and indexed root agree
- unattended cleanup limited to the system drive
- cloud-backed folders treated as measure-only

The private DiskWarden repository, machine inventory, local paths, deployment
records, and private documentation are not copied into this repository.

## Preserved fixes

- Windows desktop packaging and launcher reliability
- Kiro-era session startup hardening that still applies to the ACP lifecycle
- Python formatting and Windows script encoding gates
- OpenAI-compatible model consultation through an encrypted provider record
- document-level Enter-to-send behavior while dictating
- Codex and OpenAI-compatible backend profiles, governance, runtime switching,
  usage accounting, and truthful status reporting
- empty-session usage normalization for new installs and alternate backends

## Implementation plan

- [x] Add a failing public-product contract test for identity, providers, data
      isolation, and the bundled app.
- [x] Rename the package, CLI, desktop identity, protocol, data home, port, copy,
      and first-party assets.
- [x] Reduce the runtime registry and UI to Codex plus authenticated
      OpenAI-compatible profiles.
- [x] Package Drive Sentinel as a default-enabled first-party app with an
      isolated runtime and distinct presentation.
- [x] Replace product icon assets with the terminal mark and verify the rendered
      desktop and web surfaces.
- [ ] Run focused tests, full backend and frontend gates, security and privacy
      scans, packaging, installation, and live provider checks.
- [ ] Export a clean one-commit public history, create the public repository,
      push `main`, and verify its signed-out surface.

## Attribution

Codex Crew is derived from the Apache-2.0-licensed Kiro Crew project. Legal
notices and the upstream license remain in the public release. Product branding,
runtime defaults, bundled apps, and repository identity belong to this fork.
