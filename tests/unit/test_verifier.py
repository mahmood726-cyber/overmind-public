from __future__ import annotations

import sys

from overmind.storage.models import ProjectRecord, TaskRecord
from overmind.verification.verifier import VerificationEngine


def test_verifier_reuses_identical_test_command_for_multiple_checks(tmp_path):
    counter_file = tmp_path / "count.txt"
    script_path = tmp_path / "count_runs.py"
    script_path.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "path = Path(sys.argv[1])\n"
        "count = int(path.read_text() if path.exists() else '0') + 1\n"
        "path.write_text(str(count))\n"
        "print('tests passed')\n",
        encoding="utf-8",
    )

    command = f'"{sys.executable}" "{script_path}" "{counter_file}"'
    project = ProjectRecord(
        project_id="math-project",
        name="Math Project",
        root_path=str(tmp_path),
        project_type="python_tool",
        stack=["python"],
        test_commands=[command],
    )
    task = TaskRecord(
        task_id="task-verify",
        project_id=project.project_id,
        title="Verify math project",
        task_type="verification",
        source="test",
        priority=0.9,
        risk="high",
        expected_runtime_min=5,
        expected_context_cost="medium",
        required_verification=[
            "relevant_tests",
            "numeric_regression",
            "deterministic_fixture_tests",
            "edge_case_tests",
        ],
    )

    result = VerificationEngine(tmp_path / "artifacts").run(task, project)

    assert result.success is True
    assert counter_file.read_text() == "1"
    assert set(result.completed_checks) == {
        "relevant_tests",
        "numeric_regression",
        "deterministic_fixture_tests",
        "edge_case_tests",
    }
    assert any("reused verification evidence" in detail for detail in result.details)


def test_verifier_routes_numeric_checks_to_distinct_validation_command_and_reuses_per_command(tmp_path):
    smoke_counter = tmp_path / "smoke_count.txt"
    broad_counter = tmp_path / "broad_count.txt"
    numeric_counter = tmp_path / "numeric_count.txt"

    tests_dir = tmp_path / "tests"
    scripts_dir = tmp_path / "scripts"
    tests_dir.mkdir()
    scripts_dir.mkdir()

    def write_counter_script(path, label):
        path.write_text(
            "from pathlib import Path\n"
            "import sys\n"
            "counter = Path(sys.argv[1])\n"
            "count = int(counter.read_text() if counter.exists() else '0') + 1\n"
            "counter.write_text(str(count))\n"
            f"print('{label} passed')\n",
            encoding="utf-8",
        )

    smoke_script = tests_dir / "test_smoke.py"
    broad_script = scripts_dir / "module_functional_test.py"
    numeric_script = scripts_dir / "example_r_validation.py"

    write_counter_script(smoke_script, "smoke")
    write_counter_script(broad_script, "broad")
    write_counter_script(numeric_script, "numeric")

    smoke_command = f'"{sys.executable}" "{smoke_script}" "{smoke_counter}"'
    broad_command = f'"{sys.executable}" "{broad_script}" "{broad_counter}"'
    numeric_command = f'"{sys.executable}" "{numeric_script}" "{numeric_counter}"'

    project = ProjectRecord(
        project_id="example-stats-app",
        name="example-stats-app",
        root_path=str(tmp_path),
        project_type="browser_app",
        stack=["html", "javascript"],
        test_commands=[smoke_command, broad_command, numeric_command],
    )
    task = TaskRecord(
        task_id="task-example-verify",
        project_id=project.project_id,
        title="Verify example-stats-app",
        task_type="verification",
        source="test",
        priority=0.9,
        risk="high",
        expected_runtime_min=5,
        expected_context_cost="medium",
        required_verification=[
            "relevant_tests",
            "numeric_regression",
            "regression_checks",
        ],
    )

    result = VerificationEngine(tmp_path / "artifacts").run(task, project)

    assert result.success is True
    assert smoke_counter.read_text() == "1"
    assert broad_counter.read_text() == "1"
    assert numeric_counter.read_text() == "1"
    assert set(result.completed_checks) == {
        "relevant_tests",
        "numeric_regression",
        "regression_checks",
    }
    assert any(
        "reused verification evidence from relevant_tests command=" in detail
        for detail in result.details
    )
    assert any(
        "reused verification evidence from numeric_regression command=" in detail
        for detail in result.details
    )
