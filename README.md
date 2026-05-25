# Overmind

[![ci](https://github.com/mahmood726-cyber/overmind-public/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/mahmood726-cyber/overmind-public/actions/workflows/ci.yml) [![codeql](https://github.com/mahmood726-cyber/overmind-public/actions/workflows/codeql.yml/badge.svg?branch=master)](https://github.com/mahmood726-cyber/overmind-public/actions/workflows/codeql.yml) [![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

**Local, evidence-first orchestration for terminal coding agents.**

Overmind supervises multiple terminal-based AI coding agents (Claude, Codex, Gemini) running in parallel against your projects. It makes evidence-first decisions: parsing terminal output, gating completion on independent verification, learning across sessions through persistent typed memory, and routing tasks intelligently using Q-learning.

This is not a chat agent. It is a *supervisor* — a long-running local process that scans your projects, generates verification tasks, dispatches them to heterogeneous AI runners, observes the terminal output, and decides what is actually done.

---

## What it does

```
            ┌─────────────────────────────────────┐
            │           Orchestrator               │
            │  scan → generate → schedule →        │
            │  dispatch → observe → verify → learn │
            └────┬───────┬───────┬───────┬────────┘
                 │       │       │       │
       ┌─────────┤   ┌───┤   ┌───┤   ┌───┤
       ▼         ▼   ▼   ▼   ▼   ▼   ▼   ▼
  Discovery  Runners  Sessions  Verification  Memory
```

- **Discovery & Indexing** — scans configured roots, reads manifests and guidance files (CLAUDE.md, AGENTS.md), classifies projects by stack and risk
- **Heterogeneous runners** — drives `claude`, `codex`, and `gemini` CLIs via three protocols (interactive, one-shot, pipe), with Q-learning routing based on observed `(runner, task)` success
- **Session observation** — captures terminal transcripts, detects loops via fingerprinting, identifies proof-gaps ("agent claims done without terminal evidence")
- **Multi-stage verification** — `TrajectoryScorer` (skip/verify/retry gate) → `PolicyGuard` (real-time guardrails) → `VerificationEngine` (test commands) → `LLMJudge` / `CompoundJudge` (semantic requirements check)
- **Persistent memory** — SQLite-backed typed memory (`project_learning`, `runner_learning`, `task_pattern`, `regression`, `heuristic`, `audit_snapshot`) with FTS5 + optional semantic embeddings, validity windows for superseding outdated facts, and a "dream cycle" that consolidates duplicates and extracts heuristics from recurring patterns

## Highlights

- **2 runtime dependencies** (`psutil`, `PyYAML`) — no PyTorch, no LangChain, no vector database
- **253 tests passing**
- **Multi-agent orchestrator**, not a single chatbot
- **First-class proof-gap and loop detection** — built-in evidence verification
- **Validity windows on memories** — supersede stale facts (e.g., "project switched from pytest to vitest at tick 450")
- **Q-learning routing** — adapts which runner gets which task type based on observed success
- **Multi-step LLM judge pipeline** — composable verification with veto power and weighted majority vote
- **Local-first** — runs on your machine, your data stays local. Optional Gemini API for the LLM judge.

## Status

This is research-grade orchestration software. It is intentionally conservative — it favors observable behavior over deep automation. Bring your own runners, your own projects, your own verification commands.

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/mahmood726-cyber/overmind-public.git
cd overmind-public
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1
# Unix
source .venv/bin/activate

pip install -e .[dev]

# 2. Configure your project roots
cp .env.example .env
# Edit config/roots.yaml to point to your project directories
# Edit config/runners.yaml to match your installed CLI tools

# 3. Run
overmind scan
overmind run-once
```

## Optional features

```bash
# Semantic memory search via sentence-transformers
pip install -e .[embeddings]

# LLM judge via Google Gemini API (free tier available)
export GEMINI_API_KEY="your-key-here"
# Or add to .env file (gitignored)
```

## Useful commands

```bash
overmind scan                                   # discover projects
overmind run-once                               # one orchestration tick (dry-run with --dry-run)
overmind run-loop --iterations 10 --sleep 5     # continuous mode
overmind portfolio-audit                        # generate workflow report
overmind memories --type heuristic              # inspect learned patterns
overmind dream                                  # manually trigger memory consolidation
overmind audit-history --project-id <id>       # per-project verification trends
overmind sessions                               # list active runner sessions
```

## Architecture

| Module | Purpose |
|---|---|
| `core/orchestrator.py` | Main `run_once` loop |
| `discovery/` | Project scanner, manifest parser, guidance reader, activity analyzer |
| `runners/` | Claude / Codex / Gemini adapters, Q-router, runner registry |
| `sessions/` | Terminal session manager, output stream, transcript store |
| `parsing/` | Evidence extractor, loop detector, failure classifier, terminal parser |
| `verification/` | `VerificationEngine`, `LLMJudge`, `CompoundJudge`, `PolicyGuard`, `TrajectoryScorer`, `TruthCertEngine` |
| `memory/` | `MemoryStore`, `MemoryExtractor`, `DreamEngine`, `HeuristicEngine`, `AuditLoop`, `embeddings` |
| `tasks/` | Task generator, prioritizer, queue |
| `storage/` | SQLite state database with FTS5 + migrations |
| `intelligence/` | Batch verification, daily reports |

## Configuration

All config lives in `config/`:
- `roots.yaml` — directories to scan
- `runners.yaml` — which CLI tools count as runners
- `policies.yaml` — concurrency limits, routing strengths, isolation mode
- `verification_profiles.yaml` — which checks are required for which project types
- `projects_ignore.yaml` — directories to skip during scan

## Contributing

Issues and PRs welcome. The test suite must stay green:

```bash
pytest tests/ -v
```

## License

MIT — see [LICENSE](LICENSE).
