from __future__ import annotations

import uuid

from overmind.storage.models import InsightRecord, SessionEvidence, VerificationResult


class InsightEngine:
    def extract(
        self,
        evidence_items: list[SessionEvidence],
        verification_results: list[VerificationResult],
    ) -> list[InsightRecord]:
        insights: list[InsightRecord] = []
        for evidence in evidence_items:
            if evidence.loop_detected:
                insights.append(
                    InsightRecord(
                        insight_id=f"ins_{uuid.uuid4().hex[:8]}",
                        scope="orchestration",
                        pattern="repeated terminal output loop detected",
                        recommendation="switch to isolate-first prompt after repeated retries",
                        confidence=0.75,
                    )
                )
            if evidence.proof_gap:
                insights.append(
                    InsightRecord(
                        insight_id=f"ins_{uuid.uuid4().hex[:8]}",
                        scope="verification",
                        pattern="worker claim lacked visible proof",
                        recommendation="require minimum meaningful verification before completion",
                        confidence=0.82,
                    )
                )
        for result in verification_results:
            if not result.success:
                insights.append(
                    InsightRecord(
                        insight_id=f"ins_{uuid.uuid4().hex[:8]}",
                        scope="verification",
                        pattern="verification failure after runner completion",
                        recommendation="increase verification burden for similar tasks",
                        confidence=0.78,
                    )
                )
        return insights

