from __future__ import annotations

from overmind.parsing.terminal_parser import TerminalParser
from overmind.storage.models import SessionObservation


def test_terminal_parser_detects_loops_and_claims_without_proof():
    parser = TerminalParser(summary_trigger_lines=3, idle_timeout_min=10)
    observation = SessionObservation(
        session_id="session-1",
        runner_id="runner-1",
        task_id="task-1",
        lines=[
            "fixed the issue",
            "fixed the issue",
            "fixed the issue",
        ],
        total_line_count=3,
        exit_code=0,
        idle_seconds=0.1,
        runtime_seconds=1.2,
        started_at="2026-04-05T12:00:00+00:00",
        last_output_at="2026-04-05T12:00:01+00:00",
        command="dummy",
    )

    evidence = parser.parse([observation])[0]

    assert evidence.loop_detected is True
    assert evidence.proof_gap is True
    assert evidence.state == "NEEDS_INTERVENTION"
    assert "summary checkpoint" in evidence.required_proof


def test_terminal_parser_ignores_pytest_timeout_plugin_name():
    parser = TerminalParser(summary_trigger_lines=400, idle_timeout_min=10)
    observation = SessionObservation(
        session_id="session-2",
        runner_id="runner-2",
        task_id="task-2",
        lines=[
            "plugins: anyio-3.7.1, timeout-2.4.0, respx-0.22.0",
            "100 passed in 0.90s",
        ],
        total_line_count=2,
        exit_code=0,
        idle_seconds=0.1,
        runtime_seconds=1.0,
        started_at="2026-04-05T12:00:00+00:00",
        last_output_at="2026-04-05T12:00:01+00:00",
        command="dummy",
    )

    evidence = parser.parse([observation])[0]

    assert evidence.state == "VERIFYING"
    assert "terminal-visible failure detected" not in evidence.risks


def test_terminal_parser_allows_successful_exit_with_repeated_summary_lines():
    parser = TerminalParser(summary_trigger_lines=400, idle_timeout_min=10)
    observation = SessionObservation(
        session_id="session-3",
        runner_id="runner-3",
        task_id="task-3",
        lines=[
            "Command run:",
            "`python -m pytest tests/test_proof_carrying_numbers.py`",
            "Evidence:",
            "- `relevant_tests`: `100 passed in 0.96s`",
            "- `numeric_regression`: `100 passed in 0.96s`",
            "Command run:",
            "`python -m pytest tests/test_proof_carrying_numbers.py`",
            "Evidence:",
            "- `relevant_tests`: `100 passed in 0.96s`",
            "- `numeric_regression`: `100 passed in 0.96s`",
            "Command run:",
        ],
        total_line_count=11,
        exit_code=0,
        idle_seconds=0.1,
        runtime_seconds=1.0,
        started_at="2026-04-05T12:00:00+00:00",
        last_output_at="2026-04-05T12:00:01+00:00",
        command="dummy",
    )

    evidence = parser.parse([observation])[0]

    assert evidence.state == "VERIFYING"
    assert "repeated retry loop detected" in evidence.risks


def test_terminal_parser_ignores_pass_fail_instruction_text():
    parser = TerminalParser(summary_trigger_lines=400, idle_timeout_min=10)
    observation = SessionObservation(
        session_id="session-4",
        runner_id="runner-4",
        task_id="task-4",
        lines=[
            "OUTPUT:",
            "- print pass/fail evidence only",
            "- tests passed",
        ],
        total_line_count=3,
        exit_code=0,
        idle_seconds=0.1,
        runtime_seconds=1.0,
        started_at="2026-04-05T12:00:00+00:00",
        last_output_at="2026-04-05T12:00:01+00:00",
        command="dummy",
    )

    evidence = parser.parse([observation])[0]

    assert evidence.state == "VERIFYING"
    assert "terminal-visible failure detected" not in evidence.risks


def test_terminal_parser_ignores_failed_token_inside_passed_pytest_id():
    parser = TerminalParser(summary_trigger_lines=400, idle_timeout_min=10)
    observation = SessionObservation(
        session_id="session-5",
        runner_id="runner-5",
        task_id="task-5",
        lines=[
            "tests/test_proof_carrying_numbers.py::TestCheckRangePlausible::test_parametrized_ranges[HR-0.001-CheckResult.FAILED] PASSED [ 41%]",
            "100 passed in 1.07s",
        ],
        total_line_count=2,
        exit_code=0,
        idle_seconds=0.1,
        runtime_seconds=1.0,
        started_at="2026-04-05T12:00:00+00:00",
        last_output_at="2026-04-05T12:00:01+00:00",
        command="dummy",
    )

    evidence = parser.parse([observation])[0]

    assert evidence.state == "VERIFYING"
    assert "terminal-visible failure detected" not in evidence.risks


def test_terminal_parser_detects_rate_limit_and_requests_pause():
    parser = TerminalParser(summary_trigger_lines=400, idle_timeout_min=10)
    observation = SessionObservation(
        session_id="session-6",
        runner_id="runner-6",
        task_id="task-6",
        lines=[
            "ERROR: You've hit your usage limit. To get more access now, send a request to your admin or try again at 11:52 PM.",
        ],
        total_line_count=1,
        exit_code=1,
        idle_seconds=0.1,
        runtime_seconds=1.0,
        started_at="2026-04-05T12:00:00+00:00",
        last_output_at="2026-04-05T12:00:01+00:00",
        command="dummy",
    )

    evidence = parser.parse([observation])[0]

    assert evidence.state == "NEEDS_INTERVENTION"
    assert "provider quota/rate limit detected" in evidence.risks
    assert evidence.next_action == "pause runner until quota resets"


def test_terminal_parser_accepts_tests_passed_and_ignores_failed_zero_summary():
    parser = TerminalParser(summary_trigger_lines=400, idle_timeout_min=10)
    observation = SessionObservation(
        session_id="session-7",
        runner_id="runner-7",
        task_id="task-7",
        lines=[
            "FAILED: 0",
            "Test complete. Browser closed.",
            "tests passed",
        ],
        total_line_count=3,
        exit_code=0,
        idle_seconds=0.1,
        runtime_seconds=1.0,
        started_at="2026-04-05T12:00:00+00:00",
        last_output_at="2026-04-05T12:00:01+00:00",
        command="dummy",
    )

    evidence = parser.parse([observation])[0]

    assert evidence.state == "VERIFYING"
    assert evidence.proof_gap is False
    assert "terminal-visible failure detected" not in evidence.risks


def test_terminal_parser_ignores_repeated_divider_lines_in_successful_long_output():
    parser = TerminalParser(summary_trigger_lines=400, idle_timeout_min=10)
    observation = SessionObservation(
        session_id="session-8",
        runner_id="runner-8",
        task_id="task-8",
        lines=[
            "======================================================================",
            "FINAL TEST RESULTS",
            "======================================================================",
            "PASSED: 16",
            "FAILED: 0",
            "======================================================================",
            "OVERALL: 100.0% pass rate (16/16) - EXCELLENT",
            "======================================================================",
            "Browser open for 15 seconds for visual inspection...",
            "Test complete. Browser closed.",
            "tests passed",
        ],
        total_line_count=11,
        exit_code=0,
        idle_seconds=0.1,
        runtime_seconds=1.0,
        started_at="2026-04-05T12:00:00+00:00",
        last_output_at="2026-04-05T12:00:01+00:00",
        command="dummy",
    )

    evidence = parser.parse([observation])[0]

    assert evidence.state == "VERIFYING"
    assert evidence.loop_detected is False
    assert "repeated retry loop detected" not in evidence.risks


def test_terminal_parser_ignores_pass_rate_flags_in_echoed_browser_commands():
    parser = TerminalParser(summary_trigger_lines=400, idle_timeout_min=10)
    observation = SessionObservation(
        session_id="session-9",
        runner_id="runner-9",
        task_id="task-9",
        lines=[
            '- "python" "overmind/verification/browser_checks.py" --project-root "C:\\Projects\\example-stats-app" --page "tests/automated_test_suite.html" --summary-selector ".summary" --ready-text "Test Summary" --wait-seconds 20 --min-pass-rate 95 --ignore-console-pattern "favicon\\.ico"',
            "deprecated: `[features].enable_experimental_windows_sandbox` is deprecated.",
        ],
        total_line_count=2,
        exit_code=None,
        idle_seconds=0.1,
        runtime_seconds=1.0,
        started_at="2026-04-07T07:34:45+00:00",
        last_output_at="2026-04-07T07:34:46+00:00",
        command="codex --dangerously-bypass-approvals-and-sandbox exec --skip-git-repo-check -",
    )

    evidence = parser.parse([observation])[0]

    assert evidence.state == "RUNNING"
    assert evidence.proof_gap is False
    assert not any(event.kind.endswith("passed") for event in evidence.events)
