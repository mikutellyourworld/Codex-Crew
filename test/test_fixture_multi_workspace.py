"""Consumer coverage for the shipped multi-workspace seed fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

from codex_crew.config.loader import CodexCrewConfig, workspace_dir_for
from codex_crew.history import ConversationLog
from codex_crew.memory import MemoryStore

pytest_plugins = ["codex_crew.testing.fixtures"]


@pytest.mark.parametrize("seeded_home_fixture", ["multi-workspace"], indirect=True)
def test_multi_workspace_fixture_routes_sessions_and_memory(
    seeded_home_fixture: Path,
) -> None:
    config = CodexCrewConfig.load()
    assert config.default_workspace == "default"
    assert set(config.workspaces) == {"default", "review", "research"}

    seeded_root = seeded_home_fixture.resolve()
    expected = {
        "default": seeded_root / "workspace",
        "review": seeded_root / "workspace-review",
        "research": seeded_root / "workspace-research",
    }
    resolved = {name: workspace_dir_for(name) for name in expected}
    assert resolved == expected
    assert len(set(resolved.values())) == 3
    assert workspace_dir_for() == expected["default"]

    memories: dict[str, str] = {}
    for name, workspace in resolved.items():
        store = MemoryStore(workspace=workspace)
        store.init()
        memories[name] = store.read_preferences()

    assert len(set(memories.values())) == 3
    assert "default-memory-sentinel" in memories["default"]
    assert "review-memory-sentinel" in memories["review"]
    assert "research-memory-sentinel" in memories["research"]
    assert "default-memory-sentinel" not in memories["review"]

    log = ConversationLog(base_dir=seeded_root / "sessions")
    metadata = [log.get_metadata(row["key"]) for row in log.list_sessions()]
    assert len(metadata) == 3
    assert {(item["workspace"], item["agent"]) for item in metadata} == {
        ("default", "default"),
        ("review", "codexcrew"),
        ("research", "orchestrator"),
    }
