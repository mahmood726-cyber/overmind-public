from __future__ import annotations

from overmind.storage.models import ProjectRecord
from overmind.tasks.task_generator import TaskGenerator


def test_task_generator_includes_hybrid_browser_analytics_projects():
    project = ProjectRecord(
        project_id="hybrid-project",
        name="Hybrid Project",
        root_path="C:\\Projects\\hybrid-project",
        project_type="hybrid_browser_analytics_app",
        stack=["html", "javascript", "python"],
        has_numeric_logic=True,
        test_commands=["python -m pytest tests/test_smoke.py -q"],
    )

    tasks = TaskGenerator().generate([project], [])

    assert len(tasks) == 1
    assert tasks[0].project_id == project.project_id
