from __future__ import annotations

import subprocess
from pathlib import Path


class WorktreeManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create(self, project_root: Path, task_id: str) -> Path | None:
        if not (project_root / ".git").exists():
            return None

        worktree_path = self.base_dir / task_id
        branch_name = f"overmind/{task_id}"

        try:
            subprocess.run(
                ["git", "-C", str(project_root), "worktree", "add", str(worktree_path), "-b", branch_name],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return None

        return worktree_path

    def cleanup(self, project_root: Path, worktree_path: Path, task_id: str) -> None:
        branch_name = f"overmind/{task_id}"

        try:
            subprocess.run(
                ["git", "-C", str(project_root), "worktree", "remove", str(worktree_path), "--force"],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass

        try:
            subprocess.run(
                ["git", "-C", str(project_root), "branch", "-D", branch_name],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass

    def needs_isolation(self, project_root: Path, active_project_roots: set[str]) -> bool:
        return str(project_root) in active_project_roots
