from __future__ import annotations

from typing import List

from runner import DiagnosticsReport


def format_report(report: DiagnosticsReport) -> str:
    lines: List[str] = []
    lines.append(f"Status: {report.status}")

    if not report.hosts:
        lines.append("No diagnostic data captured.")
    else:
        for host in report.hosts:
            lines.append("=" * 60)
            lines.append(f"HOST: {host.host}")
            lines.append(
                f"Issues: {len(host.issues)}  Passed: {host.passed}  Failed: {host.failed}  Skipped: {host.skipped}"
            )
            if host.metadata.get("when"):
                lines.append(f"Captured at: {host.metadata['when']}")

            if host.issues:
                lines.append("Top issues:")
                for idx, issue in enumerate(host.issues[:10], start=1):
                    category = issue.category or "general"
                    lines.append(f"  {idx}. [{issue.severity}] {category} :: {issue.name}")
                    lines.append(f"     {issue.message}")
            else:
                lines.append("No failing plugins reported.")

    if report.errors:
        lines.append("=" * 60)
        lines.append("Errors:")
        for error in report.errors:
            lines.append(f"- {error}")

    return "\n".join(lines)
