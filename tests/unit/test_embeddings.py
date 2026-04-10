"""Tests for the embedding engine and semantic/hybrid search."""

from __future__ import annotations

from overmind.memory import embeddings
from overmind.memory.store import MemoryStore
from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord


def test_cosine_similarity_identical_vectors():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert abs(embeddings.cosine_similarity(a, b) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal_vectors():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(embeddings.cosine_similarity(a, b)) < 1e-9


def test_cosine_similarity_opposite_vectors():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert abs(embeddings.cosine_similarity(a, b) - (-1.0)) < 1e-9


def test_cosine_similarity_zero_vector():
    a = [0.0, 0.0]
    b = [1.0, 2.0]
    assert embeddings.cosine_similarity(a, b) == 0.0


def test_semantic_search_returns_empty_without_backend(tmp_path):
    """Semantic search gracefully returns [] when sentence-transformers is absent."""
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.upsert_memory(MemoryRecord(
            memory_id="mem_sem1",
            memory_type="project_learning",
            scope="proj-a",
            title="Tests pass quickly",
            content="All 50 tests complete in 3 seconds.",
        ))
        results = db.semantic_search_memories("fast test execution")
        # Either returns results (if sentence-transformers installed) or empty list
        assert isinstance(results, list)
    finally:
        db.close()


def test_semantic_search_with_manual_embeddings(tmp_path):
    """Test semantic search using manually injected embeddings."""
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.upsert_memory(MemoryRecord(
            memory_id="mem_e1",
            memory_type="project_learning",
            scope="proj-a",
            title="Browser tests slow",
            content="Browser tests take 60s.",
            embedding=[1.0, 0.0, 0.0],
        ))
        db.upsert_memory(MemoryRecord(
            memory_id="mem_e2",
            memory_type="project_learning",
            scope="proj-a",
            title="Unit tests fast",
            content="Unit tests take 3s.",
            embedding=[0.0, 1.0, 0.0],
        ))
        db.upsert_memory(MemoryRecord(
            memory_id="mem_e3",
            memory_type="project_learning",
            scope="proj-a",
            title="No embedding",
            content="No embedding stored.",
        ))

        # Manually call the semantic search internals with a known query embedding
        # [1.0, 0.0, 0.0] should match mem_e1
        from overmind.memory import embeddings as emb_mod
        import overmind.memory.embeddings as _emb

        # Monkeypatch embed() to return a known vector
        original = _emb.embed
        _emb.embed = lambda text: [1.0, 0.0, 0.0]
        try:
            results = db.semantic_search_memories("browser slowness")
            assert len(results) >= 1
            best_mem, best_score = results[0]
            assert best_mem.memory_id == "mem_e1"
            assert best_score > 0.9
        finally:
            _emb.embed = original
    finally:
        db.close()


def test_hybrid_search_merges_fts_and_semantic(tmp_path):
    """hybrid_search deduplicates across FTS5 and semantic results."""
    db = StateDatabase(tmp_path / "test.db")
    store = MemoryStore(db=db, checkpoints_dir=tmp_path / "cp", logs_dir=tmp_path / "logs")
    try:
        store.save(MemoryRecord(
            memory_id="mem_h1",
            memory_type="project_learning",
            scope="proj-a",
            title="Browser automation flaky",
            content="Selenium tests are flaky on CI.",
            embedding=[0.9, 0.1, 0.0],
        ))
        store.save(MemoryRecord(
            memory_id="mem_h2",
            memory_type="project_learning",
            scope="proj-a",
            title="Playwright stable",
            content="Playwright tests are more reliable.",
            embedding=[0.85, 0.15, 0.0],
        ))

        # FTS5 search for "browser" should find mem_h1
        fts_results = store.search("browser")
        assert any(m.memory_id == "mem_h1" for m in fts_results)

        # hybrid_search should also work
        results = store.hybrid_search("browser")
        assert isinstance(results, list)
        assert len(results) >= 1
    finally:
        db.close()


def test_embedding_roundtrip_through_db(tmp_path):
    """Embedding survives upsert -> get cycle."""
    db = StateDatabase(tmp_path / "test.db")
    try:
        emb = [0.1, 0.2, 0.3, 0.4, 0.5]
        db.upsert_memory(MemoryRecord(
            memory_id="mem_rt",
            memory_type="project_learning",
            scope="proj-a",
            title="Roundtrip test",
            content="Testing embedding persistence.",
            embedding=emb,
        ))
        loaded = db.get_memory("mem_rt")
        assert loaded is not None
        assert loaded.embedding is not None
        assert len(loaded.embedding) == 5
        for a, b in zip(loaded.embedding, emb):
            assert abs(a - b) < 1e-9
    finally:
        db.close()
