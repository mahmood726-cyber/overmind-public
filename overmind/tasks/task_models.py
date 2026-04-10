from __future__ import annotations

import uuid

from overmind.discovery.analysis_signals import recommended_analysis_checks
from overmind.storage.models import ProjectRecord, TaskRecord


def build_baseline_task(project: ProjectRecord) -> TaskRecord:
    required_verification = list(project.recommended_verification)
    if not required_verification:
        required_verification = ["build"]
        if project.test_commands:
            required_verification.append("relevant_tests")
        if project.browser_test_commands:
            required_verification.append("targeted_browser_test")
        if project.has_numeric_logic or project.has_validation_history:
            required_verification.append("numeric_regression")
        if project.has_advanced_math and project.test_commands:
            required_verification.extend(["deterministic_fixture_tests", "edge_case_tests", "output_comparison"])
        if project.has_advanced_math and project.advanced_math_score >= 6 and project.test_commands:
            required_verification.extend(["sensitivity_checks", "stochastic_stability"])
        if project.has_advanced_math and project.test_commands:
            required_verification.extend(
                recommended_analysis_checks(
                    project.advanced_math_signals,
                    score=project.advanced_math_score,
                    has_validation_history=project.has_validation_history,
                    has_oracle_benchmarks=project.has_oracle_benchmarks,
                    has_drift_history=project.has_drift_history,
                )
            )
        if project.has_advanced_math or project.has_oracle_benchmarks or project.has_drift_history:
            required_verification.append("regression_checks")
        if project.perf_commands and (project.has_oracle_benchmarks or project.has_drift_history):
            required_verification.append("before_after_benchmark")

    verify_cmd = project.test_commands[0] if project.test_commands else None

    return TaskRecord(
        task_id=f"baseline_{uuid.uuid4().hex[:8]}",
        project_id=project.project_id,
        title=f"Baseline verification for {project.name}",
        task_type="verification",
        source="project_index",
        priority=0.6,
        risk=project.risk_profile if project.risk_profile != "medium" else ("medium" if not project.has_numeric_logic else "medium_high"),
        expected_runtime_min=10 + min(project.advanced_math_score, 10),
        expected_context_cost="medium" if project.advanced_math_score >= 6 else "low",
        required_verification=list(dict.fromkeys(required_verification)),
        verify_command=verify_cmd,
    )


def build_test_first_tasks(project: ProjectRecord) -> list[TaskRecord]:
    """Generate 2 chained tasks: write tests first, then implement."""
    test_task_id = f"tests_{uuid.uuid4().hex[:8]}"
    impl_task_id = f"impl_{uuid.uuid4().hex[:8]}"

    test_task = TaskRecord(
        task_id=test_task_id,
        project_id=project.project_id,
        title=f"Write acceptance tests for {project.name}",
        task_type="test_writing",
        source="project_index",
        priority=0.65,
        risk=project.risk_profile,
        expected_runtime_min=5,
        expected_context_cost="low",
        required_verification=["relevant_tests"],
    )

    verify_cmd = project.test_commands[0] if project.test_commands else None

    impl_task = TaskRecord(
        task_id=impl_task_id,
        project_id=project.project_id,
        title=f"Implement to pass tests for {project.name}",
        task_type="implementation",
        source="project_index",
        priority=0.6,
        risk=project.risk_profile,
        expected_runtime_min=10 + min(project.advanced_math_score, 10),
        expected_context_cost="medium" if project.advanced_math_score >= 6 else "low",
        required_verification=list(project.recommended_verification) or ["relevant_tests"],
        blocked_by=[test_task_id],
        verify_command=verify_cmd,
    )

    return [test_task, impl_task]
