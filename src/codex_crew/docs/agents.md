# Agents & Configuration

Codex Crew uses agent JSON configurations for LLM interaction. A configuration can define a model, system prompt, tools, permissions, resources, and MCP servers. The default agent is `codexcrew`; custom agents can be added alongside it.

## Default Agent

The generated default configuration is `~/.kiro/agents/codexcrew.json`. Its shipped defaults include:

- Model: `auto`, which leaves model selection to the configured provider.
- Built-in tools: shell, file, code-search, web, introspection, session, reporting, and tool-search tools.
- `allowedTools` grants for selected safe tools and Codex Crew MCP operations.
- MCP servers: `codexcrew-cron` and `codexcrew-core`; `codexcrew-computer` is emitted only when computer use is enabled and supported on the current platform.
- A `postToolUse` audit hook for shell calls.

## Switching Agents

### Globally (All Sessions)

```
!agent code-reviewer     # switch to a custom agent
!agent off               # back to default codexcrew
```

### Per-Thread (Slack)

```
!ta set code-reviewer    # this thread uses code-reviewer
!ta off                  # remove thread override
!ta status               # show current thread agent
```

### Per-Tab (Dashboard)

Use the agent selector dropdown in the chat topbar or welcome screen.

### Per-Cron Job

Cron jobs can specify an agent at creation time.

## Built-in Agent Specs

Codex Crew owns specs named `codexcrew`, `codexcrew-lite`, `codexcrew-conductor`, `codexcrew-pipeline-conductor`, `codexcrew-knowledge`, `codexcrew-research`, and `codexcrew-heartbeat`. The primary and lite specs are required; the others support goal conducting, pipeline fleet supervision, knowledge extraction, research, and heartbeat features.

## Custom Agents

Custom agents are JSON files in `~/.kiro/agents/`. They define their own system prompt, tools, MCP servers, and permissions.

```json
{
  "name": "code-reviewer",
  "description": "Reviews code changes",
  "model": "claude-opus",
  "prompt": "file:///path/to/prompt.md",
  "tools": ["fs_read", "grep", "glob", "@codexcrew-core"],
  "allowedTools": ["fs_read", "grep", "glob"]
}
```

## Managing Agents

**Agent Capabilities → Agent Templates** shows installed agents with their source, tools, and MCP servers. Drop a new JSON file into `~/.kiro/agents/` and it appears automatically; the tab also provides edit and delete controls. `/agents` redirects to Agent Capabilities.

## Mapping Skills to an Agent

Each agent template can be given its own set of [skills](skills.md). Open **Agent Capabilities → Agent Templates**, select an agent, and use the **Skills** section to add or remove them. Every edit saves immediately.

Under the hood a mapped skill is a `skill://` entry in the agent's `resources`, so kiro-cli loads it natively when the agent starts:

```json
{
  "name": "code-reviewer",
  "resources": [
    "file://.kiro/steering/**/*.md",
    "skill://~/.kiro/skills/prepare-pr/SKILL.md"
  ]
}
```

Resolution rules:

| Agent | Mapping | Skills it sees |
|-------|---------|----------------|
| `codexcrew` | none | the whole catalog (default) |
| `codexcrew` | mapped | only the mapped skills |
| custom | none | none — the agent brings its own |
| custom | mapped | only the mapped skills |

`file://` resources (steering globs) are never touched by the editor, and hand-authored `skill://` entries the editor cannot express — wildcards like `skill://~/.kiro/skills/*/SKILL.md`, or paths outside the known skill roots — are listed read-only and preserved across edits.

## Agent Config Files

| File | Purpose |
|------|---------|
| `src/codex_crew/config/defaults.json` | Shipped base configuration. A development project can override it with `agents/defaults.json`. |
| `src/codex_crew/config/prompt.md` | Shipped system prompt. A development project can override it with `agents/prompt.md`. |
| `~/.codex-crew/agent.json` | Optional user overrides merged on top of defaults. |
| `~/.codex-crew/prompt.md` | Optional user prompt override, which takes priority over the shipped prompt. |
| `~/.kiro/agents/codexcrew.json` | Installed generated agent configuration. |

## Reinstalling Agent Config

```bash
codexcrew setup --agent-only
```

This regenerates `codexcrew.json` from the current defaults and user overrides.

## Architecture Note

Each agent session runs through the configured ACP backend and has its own system prompt, tools, and MCP servers.
