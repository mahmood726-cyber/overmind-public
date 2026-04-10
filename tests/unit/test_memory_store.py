from __future__ import annotations

from overmind.memory.store import MemoryStore
from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord


def test_db_memory_crud(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        mem = MemoryRecord(
            memory_id="mem_test01",
            memory_type="project_learning",
            scope="proj-1",
            title="Tests take 12 seconds",
            content="ExampleApp full test suite runs in 12s on Windows.",
            tags=["timing", "exampleapp"],
        )
        db.upsert_memory(mem)

        loaded = db.get_memory("mem_test01")
        assert loaded is not None
        assert loaded.title == "Tests take 12 seconds"
        assert loaded.scope == "proj-1"

        all_mems = db.list_memories()
        assert len(all_mems) == 1

        results = db.search_memories("exampleapp")
        assert len(results) >= 1
        assert results[0].memory_id == "mem_test01"

        results_by_scope = db.search_memories("test", scope="proj-1")
        assert len(results_by_scope) >= 1

        results_wrong_scope = db.search_memories("test", scope="proj-999")
        assert len(results_wrong_scope) == 0
    finally:
        db.close()


def test_memory_store_decay_and_archive(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    store = MemoryStore(db=db, checkpoints_dir=tmp_path / "cp", logs_dir=tmp_path / "logs")
    try:
        mem = MemoryRecord(
            memory_id="mem_decay01",
            memory_type="project_learning",
            scope="proj-1",
            title="Fragile bootstrap",
            content="The bootstrap module fails on edge cases.",
            relevance=0.15,
        )
        store.save(mem)

        decayed = store.decay_all(factor=0.5)
        assert decayed >= 1

        archived = store.archive_stale(threshold=0.1)
        assert archived >= 1

        remaining = store.list_all(status="active")
        assert len(remaining) == 0

        archived_list = store.list_all(status="archived")
        assert len(archived_list) == 1
    finally:
        db.close()


def test_memory_store_recall_for_project(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    store = MemoryStore(db=db, checkpoints_dir=tmp_path / "cp", logs_dir=tmp_path / "logs")
    try:
        store.save(MemoryRecord(
            memory_id="mem_r1",
            memory_type="project_learning",
            scope="proj-a",
            title="Tests pass in 5s",
            content="Project A tests complete quickly.",
        ))
        store.save(MemoryRecord(
            memory_id="mem_r2",
            memory_type="project_learning",
            scope="proj-b",
            title="Tests take 60s",
            content="Project B tests are slow.",
        ))

        results = store.recall_for_project("proj-a")
        assert len(results) == 1
        assert results[0].scope == "proj-a"

        global_heuristics = store.recall_heuristics("verification")
        assert len(global_heuristics) == 0
    finally:
        db.close()


def test_memory_store_forget(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    store = MemoryStore(db=db, checkpoints_dir=tmp_path / "cp", logs_dir=tmp_path / "logs")
    try:
        store.save(MemoryRecord(
            memory_id="mem_forget",
            memory_type="decision",
            scope="global",
            title="Paused gemini",
            content="Paused gemini because of hallucination.",
        ))
        assert store.get("mem_forget") is not None
        store.forget("mem_forget")
        assert store.get("mem_forget") is None
    finally:
        db.close()


def test_memory_store_stats(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    store = MemoryStore(db=db, checkpoints_dir=tmp_path / "cp", logs_dir=tmp_path / "logs")
    try:
        store.save(MemoryRecord(
            memory_id="mem_s1", memory_type="project_learning", scope="p1",
            title="A", content="A content",
        ))
        store.save(MemoryRecord(
            memory_id="mem_s2", memory_type="runner_learning", scope="r1",
            title="B", content="B content",
        ))
        stats = store.stats()
        assert stats["total"] == 2
        assert stats.get("project_learning:active", 0) == 1
        assert stats.get("runner_learning:active", 0) == 1
    finally:
        db.close()


def test_memory_store_update_relevance(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    store = MemoryStore(db=db, checkpoints_dir=tmp_path / "cp", logs_dir=tmp_path / "logs")
    try:
        store.save(MemoryRecord(
            memory_id="mem_boost", memory_type="project_learning", scope="p1",
            title="Important", content="Very important finding.", relevance=0.5,
        ))
        store.update_relevance("mem_boost", 0.3)
        boosted = store.get("mem_boost")
        assert boosted is not None
        assert boosted.relevance == 0.8
    finally:
        db.close()
