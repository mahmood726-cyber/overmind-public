from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(slots=True)
class ReviewFinding:
    persona: str
    severity: str  # P0, P1, P2
    description: str
    file_location: str | None = None


@dataclass(slots=True)
class PersonaReviewResult:
    persona: str
    verdict: str  # PASS, CONCERNS, BLOCK
    findings: list[ReviewFinding] = field(default_factory=list)
    raw_output: str = ""


@dataclass(slots=True)
class ConsensusResult:
    overall_verdict: str  # PASS, CONCERNS, BLOCK
    persona_results: list[PersonaReviewResult] = field(default_factory=list)
    consensus_findings: list[dict[str, object]] = field(default_factory=list)
    p0_count: int = 0
    p1_count: int = 0
    p2_count: int = 0


FINDING_PATTERN = re.compile(
    r"-\s*\[(P[012])\]\s*(.+?)(?:\s*\(([^)]+)\))?\s*$",
    re.MULTILINE,
)
VERDICT_PATTERN = re.compile(r"VERDICT:\s*(PASS|CONCERNS|BLOCK)", re.IGNORECASE)


def parse_review_output(persona_name: str, raw_output: str) -> PersonaReviewResult:
    """Parse a persona's raw output into structured findings."""
    findings: list[ReviewFinding] = []
    for match in FINDING_PATTERN.finditer(raw_output):
        severity = match.group(1).upper()
        description = match.group(2).strip()
        file_location = match.group(3)
        findings.append(ReviewFinding(
            persona=persona_name,
            severity=severity,
            description=description,
            file_location=file_location,
        ))

    verdict_match = VERDICT_PATTERN.search(raw_output)
    verdict = verdict_match.group(1).upper() if verdict_match else "CONCERNS"

    return PersonaReviewResult(
        persona=persona_name,
        verdict=verdict,
        findings=findings,
        raw_output=raw_output,
    )


def compute_consensus(results: list[PersonaReviewResult]) -> ConsensusResult:
    """Aggregate persona results into a consensus with severity scoring."""
    all_findings: list[ReviewFinding] = []
    for result in results:
        all_findings.extend(result.findings)

    # Group similar findings by description similarity
    consensus_findings: list[dict[str, object]] = []
    seen_descriptions: list[str] = []
    for finding in all_findings:
        normalized = finding.description.lower().strip()
        matched = False
        for i, seen in enumerate(seen_descriptions):
            if _similar(normalized, seen):
                consensus_findings[i]["agreed_by"] += 1
                consensus_findings[i]["personas"].append(finding.persona)
                matched = True
                break
        if not matched:
            seen_descriptions.append(normalized)
            consensus_findings.append({
                "severity": finding.severity,
                "description": finding.description,
                "file_location": finding.file_location,
                "personas": [finding.persona],
                "agreed_by": 1,
            })

    # Boost severity for findings agreed by multiple personas
    for finding in consensus_findings:
        if finding["agreed_by"] >= 2 and finding["severity"] == "P1":
            finding["severity"] = "P0"

    # Sort by severity then agreement count
    severity_order = {"P0": 0, "P1": 1, "P2": 2}
    consensus_findings.sort(
        key=lambda f: (severity_order.get(f["severity"], 9), -f["agreed_by"])
    )

    p0 = sum(1 for f in consensus_findings if f["severity"] == "P0")
    p1 = sum(1 for f in consensus_findings if f["severity"] == "P1")
    p2 = sum(1 for f in consensus_findings if f["severity"] == "P2")

    # Overall verdict
    if any(r.verdict == "BLOCK" for r in results) or p0 > 0:
        overall = "BLOCK"
    elif any(r.verdict == "CONCERNS" for r in results) or p1 > 0:
        overall = "CONCERNS"
    else:
        overall = "PASS"

    return ConsensusResult(
        overall_verdict=overall,
        persona_results=results,
        consensus_findings=consensus_findings,
        p0_count=p0,
        p1_count=p1,
        p2_count=p2,
    )


def _similar(a: str, b: str) -> bool:
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return False
    overlap = len(words_a & words_b)
    return overlap / len(words_a | words_b) >= 0.5
