"""Failure type taxonomy for the Judge agent."""
from __future__ import annotations

FAILURE_TYPES = {
    "DEPENDENCY_ROT": {
        "description": "Missing or broken module import",
        "patterns_stderr": [r"ImportError", r"ModuleNotFoundError", r"No module named"],
        "action_template": "Check if {module} is installed: pip install {module}",
    },
    "NUMERICAL_DRIFT": {
        "description": "Output values drifted from baseline",
        "patterns_stderr": [r"drift", r"delta=", r"tolerance"],
        "action_template": "Update baseline if intentional change, investigate if not",
    },
    "TIMEOUT": {
        "description": "Process timed out",
        "patterns_stderr": [r"[Tt]imed? out", r"TimeoutExpired"],
        "action_template": "Check for WMI deadlock (Python 3.13), infinite loop, or slow test",
    },
    "SYNTAX_ERROR": {
        "description": "Python or JS syntax error",
        "patterns_stderr": [r"SyntaxError", r"IndentationError"],
        "action_template": "Fix the syntax error in the reported file",
    },
    "MISSING_FIXTURE": {
        "description": "Required file or fixture not found",
        "patterns_stderr": [r"FileNotFoundError", r"No such file", r"ENOENT"],
        "action_template": "Restore or regenerate the missing file: {path}",
    },
    "TEST_FAILURE": {
        "description": "One or more tests failed",
        "patterns_stdout": [r"\d+ failed", r"FAILED"],
        "action_template": "Read test output and fix failing tests",
    },
    "FLOAT_PRECISION": {
        "description": "Floating-point precision or zero-as-falsy bug",
        "patterns_stderr": [r"NaN", r"Infinity", r"-Infinity"],
        "patterns_stdout": [r"\bNaN\b", r"\bInfinity\b", r"null where .+ expected"],
        "action_template": "Check for || vs ?? (drops zero), float === comparison, or parseFloat||null pattern",
    },
    "FORMULA_ERROR": {
        "description": "Incorrect formula or sign error in computation",
        "patterns_stderr": [r"AssertionError.*expected", r"assert.*!="],
        "patterns_stdout": [r"expected .+ but got", r"sign.*flip", r"direction.*wrong"],
        "action_template": "Verify formula against reference (R package or spec). Check for sign flips, wrong constants.",
    },
    "PLATFORM_COMPAT": {
        "description": "Platform-specific failure (Windows, Python version, encoding)",
        "patterns_stderr": [
            r"UnicodeEncodeError", r"UnicodeDecodeError", r"cp1252",
            r"WMI", r"platform\._wmi_query", r"python3.*not found",
            r"\\r\\n",
        ],
        "action_template": "Apply platform fix: use UTF-8 encoding, python not python3, check WMI deadlock patch",
    },
    "UNKNOWN": {
        "description": "No recognized pattern",
        "patterns_stderr": [],
        "action_template": "Manual investigation needed",
    },
}
