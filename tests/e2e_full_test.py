"""Comprehensive E2E test of every Overmind subsystem against real projects."""
from __future__ import annotations

from pathlib import Path
from overmind.config import AppConfig
from overmind.core.orchestrator import Orchestrator
from overmind.activation.context_injector import ContextInjector
from overmind.activation.session_tracker import SessionTracker
from overmind.review.multi_persona import MultiPersonaReviewer
from overmind.review.finding import parse_review_output, compute_consensus
from overmind.intelligence.session_miner import SessionMiner
from overmind.intelligence.daily_report import DailyReport
from overmind.memory.dream_engine import DreamEngine
from overmind.runners.protocols import INTERACTIVE, ONE_SHOT, PIPE
from overmind.parsing.loop_detector import LoopDetector
from overmind.isolation.worktree_manager import WorktreeManager
from overmind.tasks.task_queue import TaskQueue
from overmind.storage.models import TaskRecord

passed = 0
failed = 0
errors = []


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  [FAIL] {name} -- {detail}")


config = AppConfig.from_directory()
orch = Orchestrator(config)
injector = ContextInjector(orch.db)
tracker = SessionTracker(orch.db)
reviewer = MultiPersonaReviewer(orch.db)

try:
    print("=" * 60)
    print("OVERMIND COMPREHENSIVE E2E TEST")
    print("=" * 60)

    # 1. SCAN
    print("\n1. PROJECT SCANNING")
    projects = orch.db.list_projects()
    check("Scan found projects", len(projects) > 300, f"found {len(projects)}")
    high_risk = [p for p in projects if p.risk_profile == "high"]
    check("High-risk detected", len(high_risk) > 50, f"{len(high_risk)}")
    math_projects = [p for p in projects if p.has_advanced_math]
    check("Math projects detected", len(math_projects) > 100, f"{len(math_projects)}")

    # 2. SESSION TRACKER
    print("\n2. SESSION TRACKING")
    tracker.cleanup_stale()
    s1 = tracker.register("claude", "C:\\Models\\BayesianMA")
    s2 = tracker.register("codex", "C:\\Models\\MetaGuard")
    check("Sessions registered", len(tracker.active_sessions()) >= 2)
    check("Project paths tracked", len(tracker.active_project_paths()) >= 2)
    tracker.close_session(s1)
    tracker.close_session(s2)
    check("Sessions closed", all(
        s["session_id"] not in (s1, s2)
        for s in tracker.active_sessions()
    ))

    # 3. CONTEXT INJECTION
    print("\n3. CONTEXT INJECTION")
    ctx = injector.build_context("C:\\Models\\BayesianMA", "claude")
    check("BayesianMA context non-empty", len(ctx) > 50, f"{len(ctx)} chars")
    check("Contains OVERMIND header", "OVERMIND CONTEXT" in ctx)
    unknown_ctx = injector.build_context("C:\\nonexistent\\truly\\nothing", "claude")
    check("Unknown project has no project learnings",
          "Prior Learnings for This Project" not in unknown_ctx,
          f"got {len(unknown_ctx)} chars")

    # 4. VERIFICATION ENGINE
    print("\n4. VERIFICATION ENGINE")
    bayesian = orch.db.get_project("bayesianma-240f4a74")
    if bayesian:
        task = TaskRecord(
            task_id="e2e-v-ba", project_id=bayesian.project_id,
            title="E2E verify", task_type="verification", source="e2e",
            priority=1.0, risk="high", expected_runtime_min=5,
            expected_context_cost="medium",
            required_verification=["relevant_tests"],
            verify_command=bayesian.test_commands[0] if bayesian.test_commands else None,
        )
        result = orch.verifier.run(task, bayesian)
        check("BayesianMA verification passes", result.success)
        check("Details populated", len(result.details) > 0)
        if task.verify_command:
            vc = orch._run_verify_command(task, bayesian)
            check("verify_command passes", vc)
    else:
        check("BayesianMA found", False, "not in DB")

    # 5. MEMORY EXTRACTION
    print("\n5. MEMORY EXTRACTION")
    if bayesian and result:
        mems = orch.memory_extractor.extract(
            evidence_items=[], verification_results=[result],
            project_ids={task.task_id: bayesian.project_id},
            runner_ids={}, tick=600,
        )
        check("Memories extracted", len(mems) >= 1)

    # 6. AUDIT LOOP
    print("\n6. AUDIT LOOP")
    if bayesian and result:
        assessment = orch.audit_loop.evaluate(bayesian.project_id, result, tick=600)
        check("Has pass_rate", "current_pass_rate" in assessment)
        check("Has trend", assessment.get("trend") in ("baseline", "stable", "improving", "degrading"))

    # 7. Q-ROUTER
    print("\n7. Q-LEARNING ROUTER")
    orch.q_router.record("test_runner", "test_task", True)
    orch.q_router.record("test_runner", "test_task", True)
    orch.q_router.record("test_runner", "test_task", False)
    q = orch.q_router.score("test_runner", "test_task")
    check("Q-value computed", 0.4 < q < 0.9, f"q={q:.3f}")
    check("Default is 0.5", orch.q_router.score("x", "y") == 0.5)

    # 8. LOOP DETECTION
    print("\n8. LOOP DETECTION")
    det = LoopDetector()
    check("Exact repeat", det.detect(["same", "same", "same"]))
    check("Fingerprint loop", det.detect([
        "Error at 10:30:01 code 42",
        "Error at 10:30:05 code 43",
        "Error at 10:30:09 code 44",
    ]))
    check("Different not flagged", not det.detect([
        "Build A", "Test A", "Build B", "Test B",
    ]))

    # 9. DAG DEPENDENCIES
    print("\n9. DAG DEPENDENCIES")
    tq = TaskQueue(orch.db)
    build_t = TaskRecord(
        task_id="dag-b2", project_id="test", title="Build",
        task_type="verification", source="test", priority=0.9,
        risk="medium", expected_runtime_min=1, expected_context_cost="low",
        required_verification=["build"], status="QUEUED",
    )
    test_t = TaskRecord(
        task_id="dag-t2", project_id="test", title="Test",
        task_type="verification", source="test", priority=0.8,
        risk="medium", expected_runtime_min=1, expected_context_cost="low",
        required_verification=["test"], status="QUEUED",
        blocked_by=["dag-b2"],
    )
    tq.upsert([build_t, test_t])
    queued_ids = {t.task_id for t in tq.queued()}
    check("Build is queued", "dag-b2" in queued_ids)
    check("Test is blocked", "dag-t2" not in queued_ids)

    # 10. DRY RUN
    print("\n10. DRY RUN")
    dry = orch.run_once(dry_run=True)
    check("Returns dry_run flag", dry.get("dry_run") is True)
    check("Has would_dispatch", "would_dispatch" in dry)

    # 11. PROTOCOLS
    print("\n11. RUNNER PROTOCOLS")
    check("INTERACTIVE stdin open", not INTERACTIVE.close_stdin_after_prompt)
    check("ONE_SHOT closes stdin", ONE_SHOT.close_stdin_after_prompt)
    check("PIPE filters decorative", PIPE.filter_output("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500") is None)
    check("PIPE keeps content", PIPE.filter_output("tests passed") == "tests passed")
    check("PIPE wraps prompt", "concise" in PIPE.wrap_prompt("test").lower())
    check("PIPE capacity patterns", len(PIPE.capacity_error_patterns) >= 4)

    # 12. MULTI-PERSONA REVIEW
    print("\n12. MULTI-PERSONA REVIEW")
    if bayesian:
        personas = reviewer.select_personas(bayesian)
        check("5 personas for high-risk math", len(personas) == 5)
        runner = reviewer.preferred_runner_for(personas[0], "claude")
        check("Cross-model dispatch", runner != "claude")

    r1 = parse_review_output("correctness", "- [P1] Missing check\nVERDICT: CONCERNS")
    r2 = parse_review_output("robustness", "- [P1] Missing check on input\nVERDICT: CONCERNS")
    consensus = compute_consensus([r1, r2])
    check("Consensus computed", consensus.overall_verdict in ("PASS", "CONCERNS", "BLOCK"))

    # 13. DREAMING
    print("\n13. DREAMING")
    dream = orch.dream_engine.dream()
    check("Dream has summary", "memories_before" in dream)
    check("Dream has merges", "merges" in dream)

    # 14. SESSION MINING
    print("\n14. SESSION MINING")
    miner = SessionMiner(orch.db)
    mine = miner.mine_all(max_sessions=5)
    check("Miner runs", mine["sessions_analyzed"] > 0)
    check("Finds messages", mine["total_messages"] > 0)

    # 15. DAILY REPORT
    print("\n15. DAILY REPORT")
    reporter = DailyReport(orch.db, config.data_dir / "artifacts")
    report = reporter.generate()
    check("Has portfolio", "portfolio" in report)
    check("Has benchmark", "benchmark" in report)
    check("Has session mining", "session_mining" in report)
    check("Has priority queue", len(report.get("priority_queue", [])) > 0)
    paths = reporter.write(report)
    check("Written to disk", Path(paths["markdown"]).exists())

    # 16. MEMORY HEALTH
    print("\n16. MEMORY HEALTH")
    stats = orch.memory_store.stats()
    check("Memories > 20", stats.get("total", 0) > 20, f"total={stats.get('total', 0)}")
    search = orch.memory_store.search("verification")
    check("FTS5 search works", len(search) > 0)

    # 17. WORKTREE
    print("\n17. WORKTREE ISOLATION")
    wt = WorktreeManager(config.data_dir / "worktrees")
    check("Non-git returns None", wt.create(Path("C:/Windows"), "test") is None)
    check("Detects concurrent", wt.needs_isolation(Path("C:/X"), {"C:\\X"}))

    # 18. PROMPTS
    print("\n18. PROMPTS")
    if bayesian:
        t1 = TaskRecord(
            task_id="pt1", project_id=bayesian.project_id, title="Test",
            task_type="verification", source="test", priority=0.9, risk="high",
            expected_runtime_min=5, expected_context_cost="medium",
            required_verification=["relevant_tests"],
        )
        p1 = orch._build_worker_prompt(bayesian, t1)
        check("Verification has PHASE 1", "PHASE 1" in p1)
        check("Verification has REFLECT", "REFLECT" in p1)

        t2 = TaskRecord(
            task_id="pt2", project_id=bayesian.project_id, title="Fix bug",
            task_type="focused_fix", source="test", priority=0.9, risk="high",
            expected_runtime_min=5, expected_context_cost="medium",
            required_verification=["relevant_tests"],
        )
        p2 = orch._build_worker_prompt(bayesian, t2)
        check("Worker has RESEARCH", "RESEARCH" in p2)
        check("Worker has PRIOR LEARNINGS", "PRIOR LEARNINGS" in p2)

    # SUMMARY
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} PASSED, {failed} FAILED out of {passed + failed}")
    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(f"  - {e}")
    print("=" * 60)

finally:
    orch.close()
