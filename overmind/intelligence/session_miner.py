"""Mine Claude Code session transcripts for patterns, failures, and learnings.

Reads .jsonl session files from ~/.claude/projects/ and extracts:
- Common failure patterns
- Successful strategies
- Frequently-used commands
- Time-per-task estimates
- Model usage patterns
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord, utc_now

SESSIONS_DIR = Path.home() / ".claude" / "projects" / "C--Users-user"

FAILURE_PATTERNS = re.compile(
    r"(FAIL|ERROR|error|failed|traceback|exception|ModuleNotFoundError|ImportError|SyntaxError|TypeError|ValueError|KeyError|AssertionError)",
    re.IGNORECASE,
)
SUCCESS_PATTERNS = re.compile(
    r"(\d+\s+passed|tests?\s+passed|PASS|build\s+success|all\s+tests|100%\s+pass)",
    re.IGNORECASE,
)
COMMAND_PATTERNS = re.compile(r"python\s+-m\s+pytest|npm\s+(?:run\s+)?test|Rscript|node\s+-c|git\s+")


class SessionMiner:
    def __init__(self, db: StateDatabase, sessions_dir: Path | None = None) -> None:
        self.db = db
        self.sessions_dir = sessions_dir or SESSIONS_DIR

    def mine_all(self, max_sessions: int = 50) -> dict[str, object]:
        """Mine recent session transcripts for patterns."""
        jsonl_files = sorted(
            self.sessions_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:max_sessions]

        stats = {
            "sessions_analyzed": 0,
            "total_messages": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "tool_uses": 0,
            "failure_lines": 0,
            "success_lines": 0,
            "commands_seen": Counter(),
            "errors_seen": Counter(),
            "projects_worked_on": Counter(),
            "models_used": Counter(),
        }

        for jsonl_path in jsonl_files:
            self._mine_session(jsonl_path, stats)

        # Extract insights
        insights = self._generate_insights(stats)

        return {
            "sessions_analyzed": stats["sessions_analyzed"],
            "total_messages": stats["total_messages"],
            "user_messages": stats["user_messages"],
            "assistant_messages": stats["assistant_messages"],
            "tool_uses": stats["tool_uses"],
            "failure_lines": stats["failure_lines"],
            "success_lines": stats["success_lines"],
            "top_commands": dict(stats["commands_seen"].most_common(10)),
            "top_errors": dict(stats["errors_seen"].most_common(10)),
            "top_projects": dict(stats["projects_worked_on"].most_common(15)),
            "models_used": dict(stats["models_used"].most_common(5)),
            "insights": insights,
        }

    def mine_and_store(self, max_sessions: int = 50) -> dict[str, object]:
        """Mine sessions and store insights as Overmind memories."""
        results = self.mine_all(max_sessions)

        for insight in results["insights"]:
            existing = self.db.list_memories(
                memory_type="heuristic",
                scope="global",
                limit=50,
            )
            # Check for duplicates
            is_dup = any(
                insight["title"].lower() in m.title.lower() or m.title.lower() in insight["title"].lower()
                for m in existing
            )
            if not is_dup:
                self.db.upsert_memory(MemoryRecord(
                    memory_id=f"mined_{hash(insight['title']) & 0xFFFFFFFF:08x}",
                    memory_type="heuristic",
                    scope="global",
                    title=insight["title"],
                    content=insight["content"],
                    tags=insight.get("tags", []),
                    confidence=insight.get("confidence", 0.7),
                ))

        return results

    def _mine_session(self, jsonl_path: Path, stats: dict) -> None:
        try:
            text = jsonl_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return

        stats["sessions_analyzed"] += 1

        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = entry.get("type", "")
            message = entry.get("message", {})

            if msg_type == "user":
                stats["user_messages"] += 1
                stats["total_messages"] += 1
                content = message.get("content", "")
                if isinstance(content, str):
                    # Extract project references
                    for match in re.finditer(r"C:\\[\w\\-]+", content):
                        project_name = match.group().split("\\")[-1]
                        stats["projects_worked_on"][project_name] += 1

            elif msg_type == "assistant" or message.get("role") == "assistant":
                stats["assistant_messages"] += 1
                stats["total_messages"] += 1
                model = message.get("model", entry.get("model", ""))
                if model:
                    stats["models_used"][model] += 1

            # Check content for patterns
            content_str = json.dumps(message.get("content", ""))
            if FAILURE_PATTERNS.search(content_str):
                stats["failure_lines"] += 1
                for match in re.finditer(r"(ModuleNotFoundError|ImportError|SyntaxError|TypeError|ValueError|KeyError|AssertionError)", content_str):
                    stats["errors_seen"][match.group()] += 1

            if SUCCESS_PATTERNS.search(content_str):
                stats["success_lines"] += 1

            for match in COMMAND_PATTERNS.finditer(content_str):
                stats["commands_seen"][match.group().strip()] += 1

            # Count tool uses
            if isinstance(message.get("content"), list):
                for block in message["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        stats["tool_uses"] += 1

    def _generate_insights(self, stats: dict) -> list[dict[str, object]]:
        insights = []

        # Failure rate insight
        total = stats["success_lines"] + stats["failure_lines"]
        if total > 10:
            failure_rate = stats["failure_lines"] / total
            insights.append({
                "title": f"Session failure rate: {failure_rate:.0%}",
                "content": f"Across {stats['sessions_analyzed']} sessions: {stats['failure_lines']} failure signals, "
                           f"{stats['success_lines']} success signals. Failure rate: {failure_rate:.0%}.",
                "tags": ["mined", "failure_rate"],
                "confidence": 0.8,
            })

        # Top error types
        if stats["errors_seen"]:
            top_error = stats["errors_seen"].most_common(1)[0]
            insights.append({
                "title": f"Most common error: {top_error[0]} ({top_error[1]}x)",
                "content": f"Across {stats['sessions_analyzed']} sessions, {top_error[0]} appeared {top_error[1]} times. "
                           f"Top 3 errors: {', '.join(f'{e}({c}x)' for e, c in stats['errors_seen'].most_common(3))}.",
                "tags": ["mined", "error_pattern", top_error[0].lower()],
                "confidence": 0.85,
            })

        # Most-worked-on projects
        if stats["projects_worked_on"]:
            top_projects = stats["projects_worked_on"].most_common(5)
            insights.append({
                "title": f"Most active projects: {', '.join(p for p, _ in top_projects[:3])}",
                "content": f"Top projects by session mentions: {', '.join(f'{p}({c}x)' for p, c in top_projects)}.",
                "tags": ["mined", "project_activity"],
                "confidence": 0.9,
            })

        return insights
