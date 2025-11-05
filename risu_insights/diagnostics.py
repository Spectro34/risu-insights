"""
RISU diagnostic execution helpers.

The module translates Ansible runner events into structured diagnostic data that
the MCP layer can relay without exposing the raw log stream.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import tempfile
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ansible_runner import interface

from .config import get_paths
from .inventory import resolve_hosts, summarise_inventory


SENTINEL_START = "RISU_RESULTS_JSON_START:"
SENTINEL_END = ":RISU_RESULTS_JSON_END"
SENTINEL_REGEX = re.compile(rf"{re.escape(SENTINEL_START)}(.*?){re.escape(SENTINEL_END)}", re.DOTALL)
HOST_IN_STDOUT_REGEX = re.compile(r"\[(?P<host>[^\]]+)\]")


class DiagnosticsError(RuntimeError):
    """Raised when diagnostics cannot be executed."""


@dataclass
class DiagnosticIssue:
    """Single failing plugin instance returned by RISU."""

    plugin: str
    name: str
    severity: str
    rc: Optional[int]
    message: str
    category: Optional[str] = None
    subcategory: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "plugin": self.plugin,
            "name": self.name,
            "severity": self.severity,
            "rc": self.rc,
            "message": self.message,
        }
        if self.category:
            data["category"] = self.category
        if self.subcategory:
            data["subcategory"] = self.subcategory
        if self.metadata:
            data["metadata"] = self.metadata
        return data


@dataclass
class DiagnosticResult:
    """Aggregated diagnostics for a single host."""

    host: str
    total_checks: int
    passed: int
    failed: int
    skipped: int
    issues: List[DiagnosticIssue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def issues_found(self) -> int:
        return len(self.issues)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "host": self.host,
            "total_checks": self.total_checks,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "issues_found": self.issues_found,
            "issues": [issue.to_dict() for issue in self.issues],
        }
        if self.metadata:
            data["metadata"] = self.metadata
        return data


@dataclass
class DiagnosticsRun:
    """Result of a diagnostics execution across one or more hosts."""

    status: str
    hosts_targeted: str
    inventory: Optional[str]
    plugin_filter: str
    results: List[DiagnosticResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    runner_status: Optional[str] = None
    runner_code: Optional[int] = None
    host_logs: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "hosts": [result.host for result in self.results],
            "inventory": self.inventory,
            "plugin_filter": self.plugin_filter,
            "results": [result.to_dict() for result in self.results],
            "errors": self.errors,
            "runner": {
                "status": self.runner_status,
                "rc": self.runner_code,
            },
        }


def _derive_severity(rc: Optional[int]) -> str:
    """Map RISU return codes to a severity string."""
    if rc is None or rc == 0:
        return "info"
    if rc >= 20:
        return "critical"
    if rc >= 10:
        return "major"
    if rc >= 5:
        return "warning"
    return "minor"


def _normalise_message(message: str, limit: int = 400) -> str:
    """Normalise plugin output for display."""
    cleaned = message.strip()
    if len(cleaned) > limit:
        return cleaned[: limit - 3] + "..."
    return cleaned


def _extract_payload(candidate: str) -> Optional[Dict[str, Any]]:
    """Extract the embedded JSON payload from a sentinel wrapped string."""
    if SENTINEL_START not in candidate or SENTINEL_END not in candidate:
        return None

    match = SENTINEL_REGEX.search(candidate)
    if not match:
        return None

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _extract_host_from_stdout(stdout: Optional[str]) -> Optional[str]:
    """Best-effort extraction of hostnames from Ansible stdout lines."""
    if not stdout:
        return None
    match = HOST_IN_STDOUT_REGEX.search(stdout)
    if match:
        return match.group("host")
    return None


def _unique_ordered(values: List[str]) -> List[str]:
    seen = set()
    unique: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def parse_risu_payload(host: str, payload: Dict[str, Any]) -> DiagnosticResult:
    """Convert the RISU JSON payload into a :class:`DiagnosticResult`."""
    results = payload.get("results", {})
    issues: List[DiagnosticIssue] = []
    passed = 0
    failed = 0

    for plugin_id, plugin_data in results.items():
        result = plugin_data.get("result", {}) or {}
        rc = result.get("rc")

        if rc in (0, None):
            passed += 1
            continue

        failed += 1
        severity = _derive_severity(rc)
        message = result.get("err") or result.get("out") or plugin_data.get("description") or ""
        message = _normalise_message(message)

        plugin_path = plugin_data.get("plugin") or plugin_data.get("id") or plugin_id
        issues.append(
            DiagnosticIssue(
                plugin=plugin_path,
                name=plugin_data.get("name") or Path(plugin_path).stem,
                category=plugin_data.get("category"),
                subcategory=plugin_data.get("subcategory"),
                severity=severity,
                rc=rc,
                message=message,
                metadata={
                    "backend": plugin_data.get("backend"),
                    "hash": plugin_data.get("hash"),
                },
            )
        )

    total_checks = len(results)
    skipped = max(total_checks - passed - failed, 0)

    metadata = {}
    if payload.get("metadata"):
        metadata = dict(payload["metadata"])

    return DiagnosticResult(
        host=host,
        total_checks=total_checks,
        passed=passed,
        failed=failed,
        skipped=skipped,
        issues=issues,
        metadata=metadata,
    )


def run_diagnostics(
    hosts: str = "localhost",
    plugin_filter: Optional[str] = "",
    inventory: Optional[str] = None,
) -> DiagnosticsRun:
    """
    Execute the worker playbook that runs RISU diagnostics and return structured data.
    """

    plugin_filter = plugin_filter or ""

    paths = get_paths()
    playbook_path = paths.worker_playbooks_dir / "run-diagnostics.yml"
    if not playbook_path.exists():
        raise DiagnosticsError(f"Diagnostics playbook not found: {playbook_path}")

    inventory_path = Path(inventory).expanduser() if inventory else paths.default_inventory
    if not inventory_path.exists():
        raise DiagnosticsError(f"Inventory not found: {inventory_path}")

    summary = summarise_inventory(str(inventory_path))
    if hosts == "all":
        target_hosts = summary.hosts[:]
    else:
        resolved = resolve_hosts(hosts, str(inventory_path))
        if not resolved.validated:
            raise DiagnosticsError(resolved.error or f"No hosts matched selector '{hosts}'")
        target_hosts = resolved.hosts

    run_uuid = uuid.uuid4().hex[:8]
    run_dir = paths.runner_dir / "diagnostics" / run_uuid
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

    host_logs: Dict[str, List[str]] = defaultdict(list)
    host_payloads: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []

    def event_handler(event_data: Dict[str, Any]) -> None:
        """Capture relevant runner events."""
        event_type = event_data.get("event")
        edata = event_data.get("event_data") or {}
        stdout = event_data.get("stdout")

        host = (
            edata.get("host")
            or edata.get("host_name")
            or edata.get("inventory_hostname")
            or edata.get("inventory_hostname_short")
            or _extract_host_from_stdout(stdout)
        )
        host_key = host or "unknown"

        if stdout:
            stripped = stdout.strip()
            if stripped:
                host_logs[host_key].append(stripped)

        res = edata.get("res") or {}

        if event_type == "runner_on_failed":
            failure_msg = (
                res.get("msg")
                or res.get("stderr")
                or stdout
                or "Task failed"
            )
            errors.append(f"{host_key}: {_normalise_message(str(failure_msg))}")

        # Capture the RISU payload emitted by the debug task.
        msg = res.get("msg")
        if isinstance(msg, str):
            payload = _extract_payload(msg)
            if payload:
                host_payloads[host_key] = payload

        ansible_facts = res.get("ansible_facts") or {}
        risu_fact = ansible_facts.get("risu_data_json")
        if isinstance(risu_fact, str):
            try:
                host_payloads[host_key] = json.loads(risu_fact)
            except json.JSONDecodeError:
                pass
        elif isinstance(risu_fact, dict):
            host_payloads[host_key] = risu_fact

        if stdout:
            payload = _extract_payload(stdout)
            if payload:
                host_payloads[host_key] = payload

    envvars = {
        "ANSIBLE_SSH_USE_PTY": "False",
        "ANSIBLE_PIPELINING": "True",
    }

    try:
        runner = interface.run(
            playbook=str(playbook_path),
            inventory=str(inventory_path),
            limit=None if hosts == "all" else hosts,
            extravars={"plugin_filter": plugin_filter} if plugin_filter else {},
            quiet=False,
            json_mode=False,
            suppress_ansible_output=False,
            private_data_dir=str(run_dir),
            project_dir=str(paths.project_root),
            envvars=envvars,
            event_handler=event_handler,
        )
    except Exception as exc:
        cli_run = _run_cli_fallback(target_hosts, plugin_filter, summary, hosts)
        if cli_run.results or cli_run.errors:
            return cli_run
        raise DiagnosticsError(str(exc)) from exc

    for host, logs in host_logs.items():
        if host in host_payloads:
            continue
        for entry in logs:
            payload = _extract_payload(entry)
            if payload:
                host_payloads[host] = payload
                break

    diagnostic_results: List[DiagnosticResult] = []
    for host, payload in host_payloads.items():
        diagnostic_results.append(parse_risu_payload(host, payload))

    diagnostic_results.sort(key=lambda result: result.host)

    status = "completed"
    if runner.status == "failed" or runner.rc not in (0, None):
        status = "failed"
        rc_display = runner.rc if runner.rc is not None else "unknown"
        errors.insert(0, f"Diagnostics playbook exited with code {rc_display} (status={runner.status})")

    if not diagnostic_results:
        cli_run = _run_cli_fallback(target_hosts, plugin_filter, summary, hosts)
        if cli_run.results or cli_run.errors:
            return cli_run
        status = "failed"
        if not errors:
            errors.append("No diagnostic payloads were captured. Check RISU availability.")

    errors = _unique_ordered(errors)

    return DiagnosticsRun(
        status=status,
        hosts_targeted=hosts,
        inventory=str(inventory_path),
        plugin_filter=plugin_filter,
        results=diagnostic_results,
        errors=errors,
        runner_status=runner.status,
        runner_code=runner.rc,
        host_logs={host: logs[:] for host, logs in host_logs.items()},
    )


def _run_cli_fallback(
    hosts: List[str],
    plugin_filter: str,
    summary,
    hosts_targeted: str,
) -> DiagnosticsRun:
    results: List[DiagnosticResult] = []
    errors: List[str] = []
    host_logs: Dict[str, List[str]] = {}

    for host in hosts:
        host_vars = summary.get_host_variables(host)
        try:
            payload = _execute_risu_cli(host, host_vars, plugin_filter)
            result = parse_risu_payload(host, payload)
            result.metadata.setdefault("execution", "cli")
            results.append(result)
            host_logs[host] = []
        except DiagnosticsError as exc:
            errors.append(f"{host}: {exc}")

    status = "completed" if results and not errors else "failed"

    return DiagnosticsRun(
        status=status,
        hosts_targeted=hosts_targeted,
        inventory=str(summary.inventory_path),
        plugin_filter=plugin_filter,
        results=results,
        errors=errors,
        runner_status="cli_fallback",
        runner_code=None,
        host_logs=host_logs,
    )


def _execute_risu_cli(host: str, host_vars: Dict[str, str], plugin_filter: str) -> Dict[str, Any]:
    connection = host_vars.get("ansible_connection", "ssh")
    if host in {"127.0.0.1", "localhost"} or connection == "local":
        return _run_local_risu(plugin_filter, host_vars)
    return _run_remote_risu(host, host_vars, plugin_filter)


def _run_local_risu(plugin_filter: str, host_vars: Dict[str, str]) -> Dict[str, Any]:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        output_path = Path(handle.name)

    cmd = ["risu", "-l", "--numproc", "1", "--output", str(output_path)]
    if plugin_filter:
        cmd.extend(["-i", plugin_filter])

    sudo_required = host_vars.get("ansible_become", "").lower() in {"true", "yes", "1"}
    become_method = host_vars.get("ansible_become_method", "sudo") or "sudo"
    if sudo_required:
        cmd = [become_method, "-n"] + cmd

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as exc:
        output_path.unlink(missing_ok=True)
        raise DiagnosticsError("RISU CLI not found on control node.") from exc

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    if proc.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise DiagnosticsError(stderr or stdout or "RISU CLI failed")

    try:
        payload = json.loads(output_path.read_text())
    finally:
        output_path.unlink(missing_ok=True)

    return payload


def _run_remote_risu(host: str, host_vars: Dict[str, str], plugin_filter: str) -> Dict[str, Any]:
    user = host_vars.get("ansible_user") or host_vars.get("ansible_ssh_user")
    target = f"{user}@{host}" if user else host

    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
    ]

    port = host_vars.get("ansible_port")
    if port:
        ssh_cmd.extend(["-p", str(port)])

    identity_file = host_vars.get("ansible_ssh_private_key_file")
    if identity_file:
        ssh_cmd.extend(["-i", identity_file])

    common_args = host_vars.get("ansible_ssh_common_args")
    if common_args:
        ssh_cmd.extend(shlex.split(common_args))

    risu_cmd = ["risu", "-l", "--numproc", "1"]
    if plugin_filter:
        risu_cmd.extend(["-i", plugin_filter])

    remote_script = (
        'set -euo pipefail; '
        'tmp="$(mktemp /tmp/risu-XXXX.json)"; '
        f'{" ".join(map(shlex.quote, risu_cmd))} --output "$tmp" > /tmp/risu-cli.log 2>&1; '
        'cat "$tmp"; '
        'rm -f "$tmp"'
    )

    sudo_required = host_vars.get("ansible_become", "").lower() in {"true", "yes", "1"}
    become_method = host_vars.get("ansible_become_method", "sudo") or "sudo"
    if sudo_required:
        remote_script = f"{become_method} -n bash -lc {shlex.quote(remote_script)}"
    else:
        remote_script = f"bash -lc {shlex.quote(remote_script)}"

    ssh_cmd.extend([target, remote_script])

    try:
        proc = subprocess.run(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as exc:
        raise DiagnosticsError("SSH client not available on control node.") from exc

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()
        raise DiagnosticsError(stderr or stdout or "SSH command failed")

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DiagnosticsError("Failed to parse RISU JSON from remote host.") from exc
