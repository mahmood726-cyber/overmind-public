"""Wiki compiler: transforms CertBundles into structured Markdown articles."""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, UTC
from pathlib import Path

from overmind.storage.models import ProjectRecord
from overmind.verification.cert_bundle import CertBundle
from overmind.wiki.templates import render_article, render_index, render_changelog_entry


HISTORY_RE = re.compile(
    r"^\| (\d{4}-\d{2}-\d{2}) \| (\w+) \| ([^|]+)\| ([^|]+)\| ([^|]+)\|",
    re.MULTILINE,
)
MAX_HISTORY = 10
MAX_CHANGELOG = 30


class WikiCompiler:
    def __init__(self, wiki_dir: Path) -> None:
        self.wiki_dir = wiki_dir
        self.wiki_dir.mkdir(parents=True, exist_ok=True)

    def compile(
        self,
        bundles: list[CertBundle],
        projects: list[ProjectRecord],
    ) -> dict:
        """Compile all bundles into wiki articles. Returns summary stats."""
        project_map = {p.project_id: p for p in projects}
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        certified = 0
        rejected = 0
        failed = 0
        index_rows: list[dict] = []
        changes: list[str] = []
        new_projects: list[str] = []

        for bundle in bundles:
            proj = project_map.get(bundle.project_id)
            if not proj:
                continue

            # Count verdicts
            if bundle.verdict == "CERTIFIED":
                certified += 1
            elif bundle.verdict == "REJECT":
                rejected += 1
            elif bundle.verdict == "FAIL":
                failed += 1

            # Build witness rows
            witness_rows = []
            total_elapsed = 0.0
            for w in bundle.witness_results:
                detail = ""
                if w.verdict == "FAIL" and w.stderr:
                    detail = w.stderr.split("\n")[0][:80]
                elif w.verdict == "PASS" and w.stdout:
                    detail = w.stdout[:80]
                elif w.verdict == "SKIP":
                    detail = "skipped"
                witness_rows.append({
                    "type": w.witness_type,
                    "verdict": w.verdict,
                    "elapsed": w.elapsed,
                    "detail": detail,
                })
                total_elapsed += w.elapsed

            # Read existing history
            article_path = self.wiki_dir / f"{bundle.project_id[:40]}.md"
            history_rows = self._read_history(article_path)

            # Detect changes from last entry
            if history_rows:
                last_verdict = history_rows[-1].get("verdict", "")
                if last_verdict != bundle.verdict:
                    changes.append(f"{proj.name}: {last_verdict} -> {bundle.verdict}")
            else:
                new_projects.append(proj.name)

            # Append new history row
            witness_count = len([w for w in bundle.witness_results if w.verdict != "SKIP"])
            total_witnesses = len(bundle.witness_results)
            history_rows.append({
                "date": date_str,
                "verdict": bundle.verdict,
                "witnesses": f"{witness_count}/{total_witnesses}",
                "time": f"{total_elapsed:.1f}s",
                "hash": bundle.bundle_hash,
            })

            # Build notes
            notes = ""
            if bundle.verdict in ("REJECT", "FAIL"):
                note_lines = [bundle.arbitration_reason]
                for w in bundle.witness_results:
                    if w.verdict == "FAIL" and w.stderr:
                        note_lines.append(f"**{w.witness_type}:** {w.stderr[:200]}")
                notes = "\n\n".join(note_lines)

            # Render article
            article = render_article(
                project_name=proj.name,
                project_id=bundle.project_id,
                verdict=bundle.verdict,
                witness_summary=bundle.arbitration_reason,
                bundle_hash=bundle.bundle_hash,
                risk_profile=proj.risk_profile,
                math_score=proj.advanced_math_score,
                root_path=proj.root_path,
                project_type=proj.project_type,
                stack=", ".join(proj.stack) if proj.stack else "unknown",
                test_command=proj.test_commands[0] if proj.test_commands else "none",
                timestamp=timestamp,
                witness_rows=witness_rows,
                history_rows=history_rows,
                notes=notes,
            )
            article_path.write_text(article, encoding="utf-8")

            # Index row
            index_rows.append({
                "name": proj.name,
                "file": f"{bundle.project_id[:40]}.md",
                "verdict": bundle.verdict,
                "risk": proj.risk_profile,
                "math": proj.advanced_math_score,
                "date": date_str,
            })

        # Sort index: REJECT first, then FAIL, CERTIFIED, PASS
        verdict_order = {"REJECT": 0, "FAIL": 1, "CERTIFIED": 2, "PASS": 3, "SKIP": 4}
        index_rows.sort(key=lambda r: verdict_order.get(r["verdict"], 9))

        # Write INDEX.md
        index_content = render_index(
            timestamp=timestamp,
            total=len(bundles),
            certified=certified,
            rejected=rejected,
            failed=failed,
            rows=index_rows,
        )
        (self.wiki_dir / "INDEX.md").write_text(index_content, encoding="utf-8")

        # Write/append CHANGELOG.md
        self._append_changelog(date_str, len(bundles), certified, rejected, failed, changes, new_projects)

        # Git commit (best effort)
        self._git_commit(date_str, certified, rejected, failed)

        return {
            "articles_written": len(bundles),
            "certified": certified,
            "rejected": rejected,
            "failed": failed,
            "changes": len(changes),
            "new_projects": len(new_projects),
        }

    def _read_history(self, article_path: Path) -> list[dict]:
        """Read verification history rows from an existing article."""
        if not article_path.exists():
            return []
        content = article_path.read_text(encoding="utf-8")
        rows = []
        for match in HISTORY_RE.finditer(content):
            rows.append({
                "date": match.group(1).strip(),
                "verdict": match.group(2).strip(),
                "witnesses": match.group(3).strip(),
                "time": match.group(4).strip(),
                "hash": match.group(5).strip(),
            })
        return rows[-MAX_HISTORY:]

    def _append_changelog(self, date_str, total, certified, rejected, failed, changes, new_projects):
        """Append today's entry to CHANGELOG.md."""
        changelog_path = self.wiki_dir / "CHANGELOG.md"
        entry = render_changelog_entry(date_str, total, certified, rejected, failed, changes, new_projects)

        if changelog_path.exists():
            existing = changelog_path.read_text(encoding="utf-8")
            # Prepend new entry after header
            if existing.startswith("# "):
                header_end = existing.index("\n") + 1
                header = existing[:header_end]
                body = existing[header_end:]
                # Count existing entries and cap
                entry_count = body.count("\n## ")
                if entry_count >= MAX_CHANGELOG:
                    # Remove oldest entry
                    parts = body.split("\n## ")
                    body = "\n## ".join(parts[:MAX_CHANGELOG])
                content = header + "\n" + entry + "\n" + body
            else:
                content = "# Overmind Wiki Changelog\n\n" + entry + "\n" + existing
        else:
            content = "# Overmind Wiki Changelog\n\n" + entry

        changelog_path.write_text(content, encoding="utf-8")

    def _git_commit(self, date_str, certified, rejected, failed):
        """Best-effort git commit of wiki changes."""
        try:
            subprocess.run(
                ["git", "add", str(self.wiki_dir)],
                cwd=str(self.wiki_dir.parent),
                capture_output=True, timeout=10,
            )
            msg = f"wiki: nightly {date_str} — {certified} certified, {rejected} reject, {failed} fail"
            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=str(self.wiki_dir.parent),
                capture_output=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass  # Best effort
