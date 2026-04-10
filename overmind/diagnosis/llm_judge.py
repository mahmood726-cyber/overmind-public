"""LLM-as-Judge: fallback diagnosis for failures the rule-based Judge can't classify.

Uses the claude CLI (already authenticated) to read failure logs and
produce structured diagnoses. Only invoked for UNKNOWN verdicts.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass

from overmind.diagnosis.judge import Diagnosis
from overmind.subprocess_utils import split_command

CLAUDE_CMD = "claude"

DIAGNOSIS_PROMPT = """You are a CI failure diagnosis agent. Analyze this test failure and classify it.

Project: {project_name}
Witness type: {witness_type}
Exit code: {exit_code}

STDERR (last 500 chars):
{stderr}

STDOUT (last 500 chars):
{stdout}

Classify into exactly ONE of these types:
- DEPENDENCY_ROT: missing module or broken import
- NUMERICAL_DRIFT: output values changed from expected
- FLOAT_PRECISION: NaN, Infinity, or zero-as-falsy bug
- FORMULA_ERROR: wrong formula, sign error, wrong constant
- PLATFORM_COMPAT: Windows encoding, Python version, path issue
- TIMEOUT: process hung or timed out
- SYNTAX_ERROR: Python or JS syntax error
- MISSING_FIXTURE: required file not found
- TEST_FAILURE: assertion failed in test
- CONFIGURATION: wrong config, missing env var, stale path

Respond with ONLY valid JSON (no markdown, no explanation):
{{"failure_type": "...", "confidence": 0.0-1.0, "summary": "one line", "recommended_action": "one line"}}
"""


@dataclass
class LLMDiagnosis:
    failure_type: str
    confidence: float
    summary: str
    recommended_action: str


def llm_diagnose(
    project_name: str,
    witness_type: str,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    timeout: int = 30,
) -> LLMDiagnosis | None:
    """Call Claude CLI to diagnose an UNKNOWN failure.

    Returns LLMDiagnosis or None if the LLM call fails.
    """
    prompt = DIAGNOSIS_PROMPT.format(
        project_name=project_name,
        witness_type=witness_type,
        exit_code=exit_code or "N/A",
        stderr=(stderr or "")[-500:],
        stdout=(stdout or "")[-500:],
    )

    try:
        proc = subprocess.run(
            [CLAUDE_CMD, "--print", "-p", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode != 0:
            return None

        # Parse JSON from response (strip any markdown fencing)
        response = proc.stdout.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(response)
        return LLMDiagnosis(
            failure_type=data.get("failure_type", "UNKNOWN"),
            confidence=min(1.0, float(data.get("confidence", 0.5))),
            summary=data.get("summary", "LLM diagnosis")[:200],
            recommended_action=data.get("recommended_action", "Manual investigation")[:200],
        )
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, KeyError, ValueError):
        return None


def upgrade_unknown_diagnosis(diagnosis: Diagnosis, timeout: int = 30) -> Diagnosis:
    """If the rule-based Judge returned UNKNOWN, try LLM fallback.

    Returns the original diagnosis if LLM fails or isn't confident enough.
    """
    if diagnosis.failure_type != "UNKNOWN":
        return diagnosis

    llm_result = llm_diagnose(
        project_name=diagnosis.project_id,
        witness_type=diagnosis.witness_type,
        exit_code=None,
        stdout="",
        stderr="; ".join(diagnosis.evidence),
        timeout=timeout,
    )

    if llm_result is None or llm_result.confidence < 0.5:
        return diagnosis

    # Upgrade the diagnosis with LLM classification
    return Diagnosis(
        project_id=diagnosis.project_id,
        failure_type=llm_result.failure_type,
        confidence=llm_result.confidence * 0.9,  # Slight discount for LLM vs rule-based
        summary=f"[LLM] {llm_result.summary}",
        evidence=diagnosis.evidence,
        recommended_action=llm_result.recommended_action,
        witness_type=diagnosis.witness_type,
        created_at=diagnosis.created_at,
    )
