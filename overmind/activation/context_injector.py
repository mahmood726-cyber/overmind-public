from __future__ import annotations

from overmind.memory.store import MemoryStore
from overmind.memory.audit_loop import AuditLoop
from overmind.runners.q_router import QRouter
from overmind.storage.db import StateDatabase
from overmind.storage.models import ProjectRecord


class ContextInjector:
    """Builds context to inject into new CLI sessions via hooks or wrapper."""

    def __init__(self, db: StateDatabase) -> None:
        self.db = db
        self.memory_store = MemoryStore(
            db=db,
            checkpoints_dir=db.db_path.parent.parent / "checkpoints",
            logs_dir=db.db_path.parent.parent / "logs",
        )
        self.q_router = QRouter(db)

    def build_context(self, project_path: str | None = None, runner_type: str = "claude") -> str:
        """Build context string to inject at session start."""
        sections: list[str] = []

        # Header
        sections.append("# OVERMIND CONTEXT (auto-injected)")
        sections.append("")

        # Project memories
        if project_path:
            project = self._find_project(project_path)
            if project:
                project_memories = self.memory_store.recall_for_project(project.project_id, limit=5)
                if project_memories:
                    sections.append("## Prior Learnings for This Project")
                    for mem in project_memories:
                        sections.append(f"- [{mem.memory_type}] {mem.title}: {mem.content[:150]}")
                    sections.append("")

                # Audit history
                audit_snapshots = self.db.list_memories(
                    scope=project.project_id,
                    memory_type="audit_snapshot",
                    limit=3,
                )
                if audit_snapshots:
                    sections.append("## Recent Verification History")
                    for snap in audit_snapshots:
                        sections.append(f"- {snap.title} (tick {snap.source_tick})")
                    sections.append("")

                # Review findings
                reviews = self.db.list_memories(
                    scope=project.project_id,
                    memory_type="decision",
                    limit=2,
                )
                if reviews:
                    sections.append("## Recent Review Findings")
                    for rev in reviews:
                        sections.append(f"- {rev.title}: {rev.content[:120]}")
                    sections.append("")

        # Heuristics (global)
        heuristics = self.memory_store.list_all(status="active")
        heuristic_mems = [m for m in heuristics if m.memory_type == "heuristic"][:3]
        if heuristic_mems:
            sections.append("## Learned Heuristics")
            for h in heuristic_mems:
                sections.append(f"- {h.title}: {h.content[:120]}")
            sections.append("")

        # Runner performance
        scores = self.q_router.scores_table()
        if scores:
            runner_scores = [s for s in scores if s["runner_type"] == runner_type][:3]
            if runner_scores:
                sections.append(f"## {runner_type} Performance")
                for s in runner_scores:
                    sections.append(
                        f"- {s['task_type']}: q={s['q_value']:.2f} (W:{s['wins']} L:{s['losses']})"
                    )
                sections.append("")

        # Active sessions (cross-window awareness)
        from overmind.activation.session_tracker import SessionTracker
        tracker = SessionTracker(self.db)
        active = tracker.active_sessions()
        other_sessions = [s for s in active if s.get("project_path") != project_path]
        if other_sessions:
            sections.append("## Other Active Overmind Sessions")
            for s in other_sessions:
                sections.append(f"- {s['runner_type']} on {s.get('project_path', 'unknown')}")
            sections.append("")

        if len(sections) <= 2:
            return ""  # nothing to inject

        sections.append("---")
        return "\n".join(sections)

    def _find_project(self, project_path: str) -> ProjectRecord | None:
        for project in self.db.list_projects():
            if project.root_path.lower().rstrip("\\/") == project_path.lower().rstrip("\\/"):
                return project
        return None
