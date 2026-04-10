from __future__ import annotations

from overmind.runners.q_router import QRouter
from overmind.storage.db import StateDatabase


def test_get_routing_score_default(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        score = db.get_routing_score("claude", "verification")
        assert score == 0.5
    finally:
        db.close()


def test_update_routing_score_single_win(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.update_routing_score("claude", "verification", success=True)
        row = db.connection.execute(
            "SELECT wins, losses, q_value FROM routing_scores WHERE runner_type = ? AND task_type = ?",
            ("claude", "verification"),
        ).fetchone()
        assert row["wins"] == 1
        assert row["losses"] == 0
        # q_value = (1 + 1) / (1 + 0 + 2) = 2/3
        assert abs(row["q_value"] - 2 / 3) < 1e-9
    finally:
        db.close()


def test_update_routing_score_single_loss(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.update_routing_score("gemini", "refactor", success=False)
        row = db.connection.execute(
            "SELECT wins, losses, q_value FROM routing_scores WHERE runner_type = ? AND task_type = ?",
            ("gemini", "refactor"),
        ).fetchone()
        assert row["wins"] == 0
        assert row["losses"] == 1
        # q_value = (0 + 1) / (0 + 1 + 2) = 1/3
        assert abs(row["q_value"] - 1 / 3) < 1e-9
    finally:
        db.close()


def test_update_routing_score_incremental(tmp_path):
    """After 3 wins and 1 loss, q = (3+1)/(3+1+2) = 4/6 = 0.6667."""
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.update_routing_score("claude", "verification", success=True)
        db.update_routing_score("claude", "verification", success=True)
        db.update_routing_score("claude", "verification", success=True)
        db.update_routing_score("claude", "verification", success=False)

        row = db.connection.execute(
            "SELECT wins, losses, q_value FROM routing_scores WHERE runner_type = ? AND task_type = ?",
            ("claude", "verification"),
        ).fetchone()
        assert row["wins"] == 3
        assert row["losses"] == 1
        expected_q = (3 + 1) / (3 + 1 + 2)  # 4/6 = 0.6667
        assert abs(row["q_value"] - expected_q) < 1e-9
    finally:
        db.close()


def test_get_routing_score_after_updates(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.update_routing_score("codex", "architecture", success=True)
        db.update_routing_score("codex", "architecture", success=True)
        score = db.get_routing_score("codex", "architecture")
        # After 2 wins 0 losses: q = (2+1)/(2+0+2) = 3/4 = 0.75
        assert abs(score - 0.75) < 1e-9
    finally:
        db.close()


def test_list_routing_scores(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.update_routing_score("claude", "verification", success=True)
        db.update_routing_score("codex", "refactor", success=False)
        db.update_routing_score("gemini", "architecture", success=True)

        rows = db.list_routing_scores()
        assert len(rows) == 3
        # Sorted by q_value DESC; claude and gemini both have 1 win so q=2/3, codex has 1 loss so q=1/3
        runner_types = [r["runner_type"] for r in rows]
        assert "claude" in runner_types
        assert "codex" in runner_types
        assert "gemini" in runner_types
        # Codex (lowest q) should be last
        assert rows[-1]["runner_type"] == "codex"
        # Each row has expected keys
        for row in rows:
            assert "runner_type" in row
            assert "task_type" in row
            assert "wins" in row
            assert "losses" in row
            assert "q_value" in row
            assert "updated_at" in row
    finally:
        db.close()


def test_qrouter_score(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        router = QRouter(db)
        # Default score for unknown pair
        assert router.score("claude", "unknown_task") == 0.5
        # After recording
        router.record("claude", "verification", success=True)
        score = router.score("claude", "verification")
        assert abs(score - 2 / 3) < 1e-9
    finally:
        db.close()


def test_qrouter_record(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        router = QRouter(db)
        router.record("gemini", "performance_optimization", success=True)
        router.record("gemini", "performance_optimization", success=True)
        router.record("gemini", "performance_optimization", success=False)
        # 2 wins, 1 loss: q = (2+1)/(2+1+2) = 3/5 = 0.6
        score = router.score("gemini", "performance_optimization")
        assert abs(score - 0.6) < 1e-9
    finally:
        db.close()


def test_qrouter_scores_table(tmp_path):
    db = StateDatabase(tmp_path / "test.db")
    try:
        router = QRouter(db)
        router.record("claude", "verification", success=True)
        router.record("codex", "refactor", success=False)

        table = router.scores_table()
        assert len(table) == 2
        assert isinstance(table, list)
        assert all(isinstance(row, dict) for row in table)
    finally:
        db.close()


def test_multiple_runner_task_combinations(tmp_path):
    """Different runner-task pairs tracked independently."""
    db = StateDatabase(tmp_path / "test.db")
    try:
        db.update_routing_score("claude", "verification", success=True)
        db.update_routing_score("claude", "refactor", success=False)
        db.update_routing_score("codex", "verification", success=False)

        q_claude_verif = db.get_routing_score("claude", "verification")
        q_claude_refactor = db.get_routing_score("claude", "refactor")
        q_codex_verif = db.get_routing_score("codex", "verification")

        # claude/verification: 1 win -> q = 2/3
        assert abs(q_claude_verif - 2 / 3) < 1e-9
        # claude/refactor: 1 loss -> q = 1/3
        assert abs(q_claude_refactor - 1 / 3) < 1e-9
        # codex/verification: 1 loss -> q = 1/3
        assert abs(q_codex_verif - 1 / 3) < 1e-9
    finally:
        db.close()
