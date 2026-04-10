from __future__ import annotations

from overmind.discovery.portfolio_audit import PortfolioAuditor
from overmind.storage.models import ProjectRecord


def test_portfolio_audit_detects_secret_exposure(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("HOME", str(fake_home))
    (fake_home / ".aider.input.history").write_text(
        '$env:GEMINI_API_KEY = "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE0"\n',
        encoding="utf-8",
    )

    auditor = PortfolioAuditor(tmp_path / "artifacts")
    report = auditor.build_report(
        [
            ProjectRecord(
                project_id="proj-1",
                name="ExampleStatsApp",
                root_path="C:\\ExampleStatsApp",
                project_type="hybrid_browser_analytics_app",
                stack=["html", "javascript", "r"],
                has_numeric_logic=True,
                has_advanced_math=True,
                advanced_math_signals=["meta_analysis", "survival_analysis"],
                advanced_math_score=9,
                advanced_math_rigor="high",
                analysis_focus_areas=["evidence synthesis", "survival and censored outcomes"],
                analysis_risk_factors=["heterogeneity and effect-size specification", "censoring and proportional-hazards assumptions"],
                recommended_verification=["relevant_tests", "numeric_regression", "censoring_checks"],
                guidance_files=["CLAUDE.md"],
                has_validation_history=True,
                has_oracle_benchmarks=True,
                risk_profile="high",
            )
        ]
    )
    paths = auditor.write_report(report)

    assert report["projects_with_oracle_benchmarks"] == 1
    assert report["projects_with_advanced_math"] == 1
    assert report["advanced_math_signals"]["meta_analysis"] == 1
    assert report["advanced_math_rigor"]["high"] == 1
    assert report["analysis_focus_areas"]["evidence synthesis"] == 1
    assert report["analysis_risk_factors"]["censoring and proportional-hazards assumptions"] == 1
    assert report["verification_pressure"]["censoring_checks"] == 1
    assert report["user_history_findings"][0]["has_secret_exposure"] is True
    assert "google_api_key" in report["user_history_findings"][0]["secret_kinds"]
    assert paths["json"].endswith("portfolio_audit.json")
