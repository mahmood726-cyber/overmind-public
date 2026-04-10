from __future__ import annotations

import subprocess
from pathlib import Path

from overmind.isolation.worktree_manager import WorktreeManager


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@test.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True, capture_output=True)
    (path / "README.md").write_text("# Test\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"], check=True, capture_output=True)


def test_worktree_create_and_cleanup(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    _init_git_repo(repo)
    base_dir = tmp_path / "worktrees"

    manager = WorktreeManager(base_dir)
    wt_path = manager.create(repo, "task-abc")

    assert wt_path is not None
    assert wt_path.exists()
    assert (wt_path / "README.md").exists()

    manager.cleanup(repo, wt_path, "task-abc")
    assert not wt_path.exists()


def test_worktree_returns_none_for_non_git_dir(tmp_path):
    non_git = tmp_path / "not_a_repo"
    non_git.mkdir()
    base_dir = tmp_path / "worktrees"

    manager = WorktreeManager(base_dir)
    result = manager.create(non_git, "task-xyz")

    assert result is None


def test_needs_isolation_detects_concurrent_sessions(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    _init_git_repo(repo)
    base_dir = tmp_path / "worktrees"

    manager = WorktreeManager(base_dir)

    assert manager.needs_isolation(repo, active_project_roots=set()) is False
    assert manager.needs_isolation(repo, active_project_roots={str(repo)}) is True
