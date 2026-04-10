"""Markdown templates for wiki articles."""
from __future__ import annotations


def render_article(
    project_name: str,
    project_id: str,
    verdict: str,
    witness_summary: str,
    bundle_hash: str,
    risk_profile: str,
    math_score: int,
    root_path: str,
    project_type: str,
    stack: str,
    test_command: str,
    timestamp: str,
    witness_rows: list[dict],
    history_rows: list[dict],
    notes: str,
) -> str:
    """Render a complete project wiki article."""
    lines = [
        f"# {project_name}",
        "",
        f"**Last verified:** {timestamp} | **Verdict:** {verdict} ({witness_summary})",
        f"**Bundle hash:** {bundle_hash} | **Risk:** {risk_profile} | **Math:** {math_score}",
        "",
        "## Health",
        "",
        "| Witness | Verdict | Time | Detail |",
        "|---------|---------|------|--------|",
    ]
    for w in witness_rows:
        detail = w.get("detail", "")[:80]
        lines.append(f"| {w['type']} | {w['verdict']} | {w['elapsed']:.1f}s | {detail} |")

    lines.extend([
        "",
        "## Project",
        "",
        f"- **Path:** {root_path}",
        f"- **Type:** {project_type}",
        f"- **Stack:** {stack}",
        f"- **Test command:** `{test_command}`",
        "",
        "## Verification History",
        "",
        "| Date | Verdict | Witnesses | Time | Hash |",
        "|------|---------|-----------|------|------|",
    ])
    for h in history_rows[-10:]:
        lines.append(f"| {h['date']} | {h['verdict']} | {h['witnesses']} | {h['time']} | {h['hash']} |")

    if notes:
        lines.extend(["", "## Notes", "", notes])

    lines.append("")
    return "\n".join(lines)


def render_index(
    timestamp: str,
    total: int,
    certified: int,
    rejected: int,
    failed: int,
    rows: list[dict],
) -> str:
    """Render the wiki INDEX.md."""
    lines = [
        "# Overmind Wiki Index",
        "",
        f"**Last compiled:** {timestamp} | **Projects:** {total} | **Certified:** {certified} | **Rejected:** {rejected} | **Failed:** {failed}",
        "",
        "| Project | Verdict | Risk | Math | Last Verified |",
        "|---------|---------|------|------|---------------|",
    ]
    for r in rows:
        lines.append(f"| [{r['name']}]({r['file']}) | {r['verdict']} | {r['risk']} | {r['math']} | {r['date']} |")
    lines.append("")
    return "\n".join(lines)


def render_changelog_entry(
    date: str,
    total: int,
    certified: int,
    rejected: int,
    failed: int,
    changes: list[str],
    new_projects: list[str],
) -> str:
    """Render a single changelog entry."""
    lines = [
        f"## {date}",
        "",
        f"**Verified:** {total} | **Certified:** {certified} | **Rejected:** {rejected} | **Failed:** {failed}",
    ]
    if changes:
        lines.extend(["", "### Changes from last night"])
        for c in changes:
            lines.append(f"- {c}")
    if new_projects:
        lines.extend(["", "### New projects verified"])
        for p in new_projects:
            lines.append(f"- {p}")
    lines.append("")
    return "\n".join(lines)
