"""
Formatting helpers for human readable summaries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, List, Optional

from .diagnostics import DiagnosticResult

if TYPE_CHECKING:  # pragma: no cover
    from .playbooks import PlaybookRun


def format_diagnostics(results: Iterable[DiagnosticResult], errors: Optional[List[str]] = None) -> str:
    """Render diagnostics into a multi-host report."""
    lines: List[str] = []
    results = list(results)

    if not results and not errors:
        return "No diagnostics data available."

    for result in results:
        lines.append("=" * 80)
        lines.append(f"HOST: {result.host}")
        lines.append("=" * 80)
        lines.append(
            f"Issues: {result.issues_found}  "
            f"Passed: {result.passed}  Failed: {result.failed}  Skipped: {result.skipped}"
        )

        if result.metadata.get("when"):
            lines.append(f"Captured at: {result.metadata['when']}")

        if result.issues:
            lines.append("")
            lines.append("Top issues:")
            for idx, issue in enumerate(result.issues[:20], start=1):
                category = issue.category or "unknown"
                lines.append(f"  {idx}. [{issue.severity.upper()}] {category} :: {issue.name}")
                lines.append(f"     {issue.message}")
        else:
            lines.append("")
            lines.append("No failing plugins reported.")

        lines.append("")

    if errors:
        lines.append("=" * 80)
        lines.append("Errors")
        lines.append("=" * 80)
        for err in errors:
            lines.append(f"- {err}")
        lines.append("")

    return "\n".join(lines).strip()


def format_playbook_summary(run: "PlaybookRun") -> str:
    """Render a concise summary for a playbook execution."""
    lines: List[str] = []
    lines.append("=" * 80)
    lines.append(f"PLAYBOOK: {run.playbook}")
    lines.append("=" * 80)
    lines.append(
        f"Status: {run.status}  Changed: {run.stats.get('changed', 0)}  "
        f"Failed: {run.stats.get('failed', 0)}  Ok: {run.stats.get('ok', 0)}  "
        f"Skipped: {run.stats.get('skipped', 0)}"
    )

    if run.check_mode:
        lines.append("Mode: check (dry-run)")

    if run.per_host:
        lines.append("")
        lines.append("Per-host summary:")
        for host, stats in sorted(run.per_host.items()):
            lines.append(
                f"  - {host}: ok={stats.get('ok', 0)} changed={stats.get('changed', 0)} "
                f"failed={stats.get('failures', 0)} skipped={stats.get('skipped', 0)}"
            )

    if run.errors:
        lines.append("")
        lines.append("Errors:")
        for err in run.errors:
            lines.append(f"  - {err}")

    return "\n".join(lines)
