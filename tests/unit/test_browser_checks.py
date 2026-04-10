from __future__ import annotations

from overmind.verification.browser_checks import filter_console_logs, parse_pass_rate


def test_parse_pass_rate_handles_visual_summary():
    summary = "Tests Complete: 37/39 passed (95%)"
    assert parse_pass_rate(summary) == 95.0


def test_parse_pass_rate_handles_summary_panel_format():
    summary = "Validation Summary\nTests Passed (91.5%)"
    assert parse_pass_rate(summary) == 91.5


def test_filter_console_logs_ignores_favicon_and_keeps_real_errors():
    logs = [
        {
            "level": "SEVERE",
            "message": "http://127.0.0.1:8765/favicon.ico - Failed to load resource: the server responded with a status of 404 (File not found)",
            "source": "network",
        },
        {
            "level": "WARNING",
            "message": 'http://127.0.0.1:8765/js/visualization.js 11:16 "D3.js not loaded - Visualization module will have limited functionality"',
            "source": "console-api",
        },
        {
            "level": "SEVERE",
            "message": "http://127.0.0.1:8765/js/meta-analysis.js 80:37 Uncaught TypeError: variances.some is not a function",
            "source": "javascript",
        },
    ]

    severe, warning = filter_console_logs(logs, ignore_patterns=[r"favicon\.ico"])

    assert len(severe) == 1
    assert "variances.some is not a function" in severe[0]["message"]
    assert len(warning) == 1
    assert "D3.js not loaded" in warning[0]["message"]
