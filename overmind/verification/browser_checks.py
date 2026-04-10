from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import re
import socketserver
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PASS_RATE_PATTERNS = (
    re.compile(r"Pass Rate:\s*([0-9]+(?:\.[0-9]+)?)%", re.IGNORECASE),
    re.compile(r"Tests Passed\s*\(([0-9]+(?:\.[0-9]+)?)%\)", re.IGNORECASE),
    re.compile(r"passed\s*\(([0-9]+(?:\.[0-9]+)?)%\)", re.IGNORECASE),
)
DEFAULT_IGNORED_CONSOLE_PATTERNS = (
    r"favicon\.ico",
)


@dataclass(slots=True)
class BrowserCheckResult:
    passed: bool
    page: str
    summary_text: str
    pass_rate: float | None
    severe_logs: list[dict[str, str]]
    warning_logs: list[dict[str, str]]
    message: str


class QuietRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


@contextlib.contextmanager
def serve_directory(root: Path):
    handler = functools.partial(QuietRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def parse_pass_rate(summary_text: str) -> float | None:
    for pattern in PASS_RATE_PATTERNS:
        match = pattern.search(summary_text)
        if match:
            return float(match.group(1))
    return None


def filter_console_logs(
    logs: list[dict[str, object]],
    ignore_patterns: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    ignored = [re.compile(pattern, re.IGNORECASE) for pattern in ignore_patterns]
    severe_logs: list[dict[str, str]] = []
    warning_logs: list[dict[str, str]] = []

    for raw_log in logs:
        message = str(raw_log.get("message", ""))
        if any(pattern.search(message) for pattern in ignored):
            continue

        entry = {
            "level": str(raw_log.get("level", "")),
            "message": message,
            "source": str(raw_log.get("source", "")),
        }
        level = entry["level"].upper()
        if level == "SEVERE":
            severe_logs.append(entry)
        elif level == "WARNING":
            warning_logs.append(entry)
    return severe_logs, warning_logs


def run_browser_check(
    *,
    project_root: Path,
    page: str,
    summary_selector: str,
    ready_text: str | None,
    wait_seconds: float,
    min_pass_rate: float | None,
    ignore_console_patterns: list[str],
) -> BrowserCheckResult:
    project_root = project_root.resolve()
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

    with serve_directory(project_root) as port:
        url = f"http://127.0.0.1:{port}/{page.replace('\\', '/')}"
        driver = webdriver.Edge(options=options)
        try:
            driver.get(url)
            wait = WebDriverWait(driver, wait_seconds)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, summary_selector)))
            if ready_text:
                wait.until(
                    lambda browser: ready_text.lower()
                    in browser.find_element(By.CSS_SELECTOR, summary_selector).text.lower()
                )
            summary_text = driver.find_element(By.CSS_SELECTOR, summary_selector).text.strip()
            pass_rate = parse_pass_rate(summary_text)
            severe_logs, warning_logs = filter_console_logs(
                driver.get_log("browser"),
                ignore_patterns=ignore_console_patterns,
            )
        except TimeoutException as exc:
            return BrowserCheckResult(
                passed=False,
                page=page,
                summary_text="",
                pass_rate=None,
                severe_logs=[],
                warning_logs=[],
                message=f"timed out waiting for browser summary: {exc.msg}",
            )
        finally:
            driver.quit()

    if not summary_text:
        return BrowserCheckResult(
            passed=False,
            page=page,
            summary_text="",
            pass_rate=None,
            severe_logs=severe_logs,
            warning_logs=warning_logs,
            message="browser summary was empty",
        )

    if min_pass_rate is not None and pass_rate is None:
        return BrowserCheckResult(
            passed=False,
            page=page,
            summary_text=summary_text,
            pass_rate=None,
            severe_logs=severe_logs,
            warning_logs=warning_logs,
            message="pass rate was not found in browser summary",
        )

    if min_pass_rate is not None and pass_rate is not None and pass_rate < min_pass_rate:
        return BrowserCheckResult(
            passed=False,
            page=page,
            summary_text=summary_text,
            pass_rate=pass_rate,
            severe_logs=severe_logs,
            warning_logs=warning_logs,
            message=f"browser pass rate {pass_rate:.1f}% is below required {min_pass_rate:.1f}%",
        )

    if severe_logs:
        return BrowserCheckResult(
            passed=False,
            page=page,
            summary_text=summary_text,
            pass_rate=pass_rate,
            severe_logs=severe_logs,
            warning_logs=warning_logs,
            message=f"browser emitted {len(severe_logs)} severe console error(s)",
        )

    return BrowserCheckResult(
        passed=True,
        page=page,
        summary_text=summary_text,
        pass_rate=pass_rate,
        severe_logs=severe_logs,
        warning_logs=warning_logs,
        message="browser validation passed",
    )


def _print_result(result: BrowserCheckResult) -> None:
    print(f"PAGE: {result.page}")
    print("SUMMARY:")
    for line in result.summary_text.splitlines():
        print(f"- {line}")
    if result.pass_rate is not None:
        print(f"PASS_RATE: {result.pass_rate:.1f}%")
    if result.warning_logs:
        print(f"BROWSER_WARNINGS: {len(result.warning_logs)}")
        for entry in result.warning_logs[:5]:
            print(f"- warning: {entry['message']}")
    if result.severe_logs:
        print(f"BROWSER_ERRORS: {len(result.severe_logs)}")
        for entry in result.severe_logs[:5]:
            print(f"- error: {entry['message']}")
    print(result.message)
    print("browser passed" if result.passed else "browser failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a real-browser validation check against a local project page.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--summary-selector", default=".summary")
    parser.add_argument("--ready-text")
    parser.add_argument("--wait-seconds", type=float, default=15.0)
    parser.add_argument("--min-pass-rate", type=float)
    parser.add_argument(
        "--ignore-console-pattern",
        action="append",
        default=[],
        help="Regex pattern for console messages that should not fail the check.",
    )
    args = parser.parse_args(argv)

    result = run_browser_check(
        project_root=Path(args.project_root),
        page=args.page,
        summary_selector=args.summary_selector,
        ready_text=args.ready_text,
        wait_seconds=args.wait_seconds,
        min_pass_rate=args.min_pass_rate,
        ignore_console_patterns=[*DEFAULT_IGNORED_CONSOLE_PATTERNS, *args.ignore_console_pattern],
    )
    _print_result(result)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
