from __future__ import annotations

import os

from overmind.activation.context_injector import ContextInjector
from overmind.activation.session_tracker import SessionTracker
from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord, ProjectRecord


def test_session_tracker_register_and_list(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    tracker = SessionTracker(db)
    try:
        sid = tracker.register("claude", "C:\\Models\\BayesianMA")
        assert sid.startswith("sess_")

        active = tracker.active_sessions()
        assert len(active) == 1
        assert active[0]["runner_type"] == "claude"
        assert active[0]["project_path"] == "C:\\Models\\BayesianMA"
    finally:
        db.close()


def test_session_tracker_close_and_cleanup(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    tracker = SessionTracker(db)
    try:
        sid = tracker.register("codex", "C:\\Projects\\test")
        tracker.close_session(sid)

        active = tracker.active_sessions()
        assert len(active) == 0
    finally:
        db.close()


def test_session_tracker_active_project_paths(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    tracker = SessionTracker(db)
    try:
        tracker.register("claude", "C:\\Models\\A")
        tracker.register("codex", "C:\\Models\\B")

        paths = tracker.active_project_paths()
        assert "C:\\Models\\A" in paths
        assert "C:\\Models\\B" in paths
    finally:
        db.close()


def test_context_injector_returns_empty_for_unknown_project(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        injector = ContextInjector(db)
        context = injector.build_context("C:\\nonexistent\\project")
        # No project in DB, no memories — should return empty
        assert context == ""
    finally:
        db.close()


def test_context_injector_includes_project_memories(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        # Add a project and memory
        project = ProjectRecord(
            project_id="test-proj",
            name="Test Project",
            root_path="C:\\test",
            project_type="python_tool",
            stack=["python"],
        )
        db.upsert_project(project)
        db.upsert_memory(MemoryRecord(
            memory_id="mem_ctx1",
            memory_type="project_learning",
            scope="test-proj",
            title="Tests pass in 5s",
            content="All 25 tests pass in 5 seconds.",
        ))

        injector = ContextInjector(db)
        context = injector.build_context("C:\\test")
        assert "OVERMIND CONTEXT" in context
        assert "Tests pass in 5s" in context
    finally:
        db.close()


def test_context_injector_shows_other_active_sessions(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        tracker = SessionTracker(db)
        tracker.register("codex", "C:\\other\\project")

        project = ProjectRecord(
            project_id="my-proj",
            name="My Project",
            root_path="C:\\my\\project",
            project_type="python_tool",
            stack=["python"],
        )
        db.upsert_project(project)
        db.upsert_memory(MemoryRecord(
            memory_id="mem_ctx2",
            memory_type="project_learning",
            scope="my-proj",
            title="Some learning",
            content="Something useful.",
        ))

        injector = ContextInjector(db)
        context = injector.build_context("C:\\my\\project")
        assert "Other Active Overmind Sessions" in context
        assert "codex" in context
    finally:
        db.close()
