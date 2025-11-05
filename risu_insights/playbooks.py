"""
Playbook listing and execution helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ansible_runner import interface

from .config import get_paths
from .inventory import resolve_hosts


class PlaybookError(RuntimeError):
    """Raised when remediation playbooks cannot be executed."""


@dataclass
class PlaybookCatalog:
    """Available remediation playbooks."""

    directory: Path
    playbooks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "directory": str(self.directory),
            "count": len(self.playbooks),
            "playbooks": sorted(self.playbooks),
        }


@dataclass
class PlaybookRun:
    """Structured outcome of a playbook execution."""

    status: str
    playbook: str
    hosts: str
    inventory: Optional[str]
    check_mode: bool
    stats: Dict[str, int] = field(default_factory=dict)
    per_host: Dict[str, Dict[str, int]] = field(default_factory=dict)
    stdout_excerpt: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    runner_status: Optional[str] = None
    runner_code: Optional[int] = None

    def to_dict(self) -> Dict[str, object]:
        from .formatters import format_playbook_summary  # Local import to avoid circular

        return {
            "status": self.status,
            "playbook": self.playbook,
            "hosts": self.hosts,
            "inventory": self.inventory,
            "check_mode": self.check_mode,
            "stats": self.stats,
            "per_host": self.per_host,
            "errors": self.errors,
            "runner": {
                "status": self.runner_status,
                "rc": self.runner_code,
            },
            "summary": format_playbook_summary(self),
            "stdout_excerpt": self.stdout_excerpt,
        }


def list_playbooks() -> PlaybookCatalog:
    """Discover available remediation playbooks."""
    paths = get_paths()
    directory = paths.remediation_playbooks_dir
    playbooks = {
        p.name for p in directory.glob("*.yml")
    } | {
        p.name for p in directory.glob("*.yaml")
    }
    playbooks = sorted(playbooks)
    return PlaybookCatalog(directory=directory, playbooks=playbooks)


def _normalise_playbook_name(playbook: str, directory: Path) -> Path:
    """
    Resolve the playbook name to an existing file, accepting names without an extension.
    """

    candidate = Path(playbook)
    if candidate.is_absolute():
        return candidate

    search_order: List[str] = []
    if candidate.suffix:
        search_order.append(candidate.name)
    else:
        search_order.extend(
            [
                candidate.name,
                f"{candidate.name}.yml",
                f"{candidate.name}.yaml",
            ]
        )

    for name in search_order:
        resolved = directory / name
        if resolved.exists():
            return resolved

    return directory / search_order[0]


def _collapse_repeated_lines(lines: Sequence[str], max_lines: int = 40) -> List[str]:
    """Collapse consecutive repeated lines while preserving ordering."""
    collapsed: List[str] = []
    if not lines:
        return collapsed

    prev = lines[0]
    count = 1

    def flush(value: str, repeat_count: int) -> None:
        if repeat_count == 1:
            collapsed.append(value)
        else:
            collapsed.append(f"{value} (repeated {repeat_count} times)")

    for line in lines[1:]:
        if line == prev:
            count += 1
        else:
            flush(prev, count)
            prev = line
            count = 1
    flush(prev, count)

    return collapsed[-max_lines:]


def _unique_ordered(values: Sequence[str]) -> List[str]:
    """Return values with duplicates removed while retaining the original order."""
    seen = set()
    unique = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def run_playbook(
    playbook: str,
    hosts: str = "all",
    inventory: Optional[str] = None,
    check_mode: bool = False,
    extravars: Optional[Dict[str, object]] = None,
) -> PlaybookRun:
    """Execute a remediation playbook using ansible-runner."""
    paths = get_paths()
    playbook_path = _normalise_playbook_name(playbook, paths.remediation_playbooks_dir)
    if not playbook_path.exists():
        catalog = list_playbooks()
        suggestions = ", ".join(catalog.playbooks[:10]) or "No playbooks available"
        raise PlaybookError(f"Playbook not found: {playbook}. Try one of: {suggestions}")

    inventory_path = Path(inventory).expanduser() if inventory else paths.default_inventory
    if not inventory_path.exists():
        raise PlaybookError(f"Inventory not found: {inventory_path}")

    if hosts != "all":
        resolved = resolve_hosts(hosts, str(inventory_path))
        if not resolved.validated:
            error = resolved.error or f"No hosts matched selector '{hosts}'"
            raise PlaybookError(error)

    playbook_runner_dir = paths.runner_dir / "playbooks"
    playbook_runner_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

    stdout_lines: List[str] = []
    errors: List[str] = []

    def event_handler(event_data: Dict[str, object]) -> None:
        event = event_data.get("event")
        stdout = event_data.get("stdout")
        edata = event_data.get("event_data") or {}
        res = edata.get("res") or {}

        host = (
            edata.get("host")
            or edata.get("host_name")
            or edata.get("inventory_hostname")
            or edata.get("inventory_hostname_short")
        )
        host_key = host or "unknown"

        stripped = str(stdout).strip() if stdout else ""
        if stripped:
            stdout_lines.append(stripped)

        if event == "runner_on_failed":
            failure_msg = res.get("msg") or res.get("stderr") or stripped or "Task failed"
            errors.append(f"{host_key}: {failure_msg}")

    run = interface.run(
        playbook=str(playbook_path),
        inventory=str(inventory_path),
        limit=None if hosts == "all" else hosts,
        extravars={
            **(extravars or {}),
            **({"ansible_check_mode": True} if check_mode else {}),
        },
        quiet=False,
        json_mode=False,
        suppress_ansible_output=False,
        private_data_dir=str(playbook_runner_dir),
        project_dir=str(paths.project_root),
        event_handler=event_handler,
    )

    stats: Dict[str, int] = {
        "ok": 0,
        "changed": 0,
        "failed": 0,
        "skipped": 0,
    }
    per_host: Dict[str, Dict[str, int]] = {}

    if run.stats:
        for host, host_stats in run.stats.items():
            if not isinstance(host_stats, dict):
                continue
            per_host[host] = dict(host_stats)
            stats["ok"] += host_stats.get("ok", 0)
            stats["changed"] += host_stats.get("changed", 0)
            stats["failed"] += host_stats.get("failures", 0)
            stats["skipped"] += host_stats.get("skipped", 0)

    status = "completed"
    if run.status == "failed" or run.rc not in (0, None):
        status = "failed"

    # Keep the most recent entries to avoid flooding responses.
    if len(stdout_lines) > 400:
        stdout_lines = stdout_lines[-400:]

    excerpt = _collapse_repeated_lines(stdout_lines)
    errors = _unique_ordered(errors)

    return PlaybookRun(
        status=status,
        playbook=playbook_path.name if playbook_path.exists() else playbook,
        hosts=hosts,
        inventory=str(inventory_path),
        check_mode=check_mode,
        stats=stats,
        per_host=per_host,
        stdout_excerpt=excerpt,
        errors=errors,
        runner_status=run.status,
        runner_code=run.rc,
    )
