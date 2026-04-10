from overmind.storage.models import ProjectRecord
from overmind.tasks.task_models import build_test_first_tasks
from overmind.tasks.task_generator import TaskGenerator


def test_build_test_first_tasks_creates_two_chained_tasks():
    project = ProjectRecord(
        project_id="math-proj",
        name="Math Project",
        root_path="C:\\Models\\math",
        project_type="python_tool",
        stack=["python"],
        has_advanced_math=True,
        advanced_math_score=8,
        test_commands=["python -m pytest -q"],
        recommended_verification=["relevant_tests", "numeric_regression"],
    )

    tasks = build_test_first_tasks(project)

    assert len(tasks) == 2
    test_task, impl_task = tasks
    assert test_task.task_type == "test_writing"
    assert impl_task.task_type == "implementation"
    assert impl_task.blocked_by == [test_task.task_id]
    assert test_task.blocked_by == []


def test_generator_uses_test_first_for_advanced_math():
    project = ProjectRecord(
        project_id="adv-math",
        name="Advanced Math",
        root_path="C:\\Models\\adv",
        project_type="python_tool",
        stack=["python"],
        has_advanced_math=True,
        advanced_math_score=10,
        test_commands=["python -m pytest -q"],
    )

    tasks = TaskGenerator().generate([project], [])
    assert len(tasks) == 2
    assert tasks[0].task_type == "test_writing"
    assert tasks[1].task_type == "implementation"


def test_generator_uses_baseline_for_non_math():
    project = ProjectRecord(
        project_id="simple-app",
        name="Simple App",
        root_path="C:\\Projects\\simple",
        project_type="browser_app",
        stack=["html", "javascript"],
        has_advanced_math=False,
        test_commands=["npm test"],
    )

    tasks = TaskGenerator().generate([project], [])
    assert len(tasks) == 1
    assert tasks[0].task_type == "verification"
