"""Shared TYPE_CHECKING imports for dashboard modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codex_crew.context import ContextBuilder
    from codex_crew.cron import CronService
    from codex_crew.history import ConversationLog, HistoryConsolidator
    from codex_crew.learn import LessonStore
    from codex_crew.session import SessionManager
    from codex_crew.subagent import SubagentManager
    from codex_crew.taskrunner import TaskRunner

__all__ = [
    "ContextBuilder",
    "CronService",
    "ConversationLog",
    "HistoryConsolidator",
    "LessonStore",
    "SessionManager",
    "SubagentManager",
    "TaskRunner",
]
