from __future__ import annotations

from overmind.parsing.evidence_extractor import EvidenceExtractor
from overmind.parsing.failure_classifier import FailureClassifier
from overmind.parsing.loop_detector import LoopDetector
from overmind.storage.models import SessionEvidence, SessionObservation


class TerminalParser:
    def __init__(self, summary_trigger_lines: int = 400, idle_timeout_min: int = 10) -> None:
        self.summary_trigger_lines = summary_trigger_lines
        self.idle_timeout_seconds = idle_timeout_min * 60
        self.extractor = EvidenceExtractor()
        self.loop_detector = LoopDetector()
        self.classifier = FailureClassifier()

    def parse(self, observations: list[SessionObservation]) -> list[SessionEvidence]:
        evidence_items: list[SessionEvidence] = []
        for observation in observations:
            events, commands, unsupported_claim = self.extractor.extract(observation.lines)
            loop_detected = self.loop_detector.detect(observation.lines)
            proof_exists = any(event.kind.endswith("passed") for event in events)
            proof_gap = unsupported_claim and not proof_exists
            state, risks, next_action = self.classifier.classify(
                events=events,
                loop_detected=loop_detected,
                proof_gap=proof_gap,
                exit_code=observation.exit_code,
                idle_seconds=observation.idle_seconds,
                idle_timeout_seconds=self.idle_timeout_seconds,
            )
            required_proof = []
            if proof_gap:
                required_proof.append("terminal-visible verification")
            if observation.total_line_count >= self.summary_trigger_lines:
                required_proof.append("summary checkpoint")

            evidence_items.append(
                SessionEvidence(
                    task_id=observation.task_id,
                    runner_id=observation.runner_id,
                    state=state,
                    risks=risks,
                    next_action=next_action,
                    required_proof=required_proof,
                    events=events,
                    last_commands=commands[-5:],
                    output_excerpt=observation.lines[-8:],
                    loop_detected=loop_detected,
                    proof_gap=proof_gap,
                    exited=observation.exit_code is not None,
                    exit_code=observation.exit_code,
                )
            )
        return evidence_items
