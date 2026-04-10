from __future__ import annotations

import subprocess
from pathlib import Path


class GitProbe:
    def inspect(self, root: Path) -> tuple[bool, str | None]:
        git_path = root / ".git"
        if not git_path.exists():
            return False, None
        head_path = self._resolve_head_path(git_path)
        if head_path and head_path.exists():
            try:
                head_text = head_path.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                head_text = ""
            if head_text.startswith("ref:"):
                branch = head_text.split("/", 2)[-1].strip()
                return True, branch or None
            if head_text:
                return True, head_text[:12]
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return True, None

        branch = result.stdout.strip() if result.returncode == 0 else None
        return True, branch or None

    def _resolve_head_path(self, git_path: Path) -> Path | None:
        if git_path.is_dir():
            return git_path / "HEAD"
        try:
            text = git_path.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            return None
        prefix = "gitdir:"
        if not text.lower().startswith(prefix):
            return None
        target = text[len(prefix) :].strip()
        git_dir = Path(target)
        if not git_dir.is_absolute():
            git_dir = (git_path.parent / git_dir).resolve()
        return git_dir / "HEAD"
