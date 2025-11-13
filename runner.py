from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config import get_settings
from inventory import ResolvedHosts, resolve_hosts, summarise_inventory


@dataclass
class DiagnosticIssue:
    plugin: str
    name: str
    severity: str
    message: str
    rc: Optional[int] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "plugin": self.plugin,
            "name": self.name,
            "severity": self.severity,
            "message": self.message,
        }
        if self.rc is not None:
            data["rc"] = self.rc
        if self.category:
            data["category"] = self.category
        if self.subcategory:
            data["subcategory"] = self.subcategory
        return data


@dataclass
class HostDiagnostics:
    host: str
    total_checks: int
    passed: int
    failed: int
    skipped: int
    issues: List[DiagnosticIssue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "total_checks": self.total_checks,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "issues_found": len(self.issues),
            "issues": [issue.to_dict() for issue in self.issues],
            "metadata": self.metadata,
        }


@dataclass
class DiagnosticsReport:
    status: str
    hosts: List[HostDiagnostics] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "hosts": [host.to_dict() for host in self.hosts],
            "errors": self.errors,
        }


class DiagnosticsRunner:
    def __init__(self):
        self.settings = get_settings()

    def run(self, hosts: str = "localhost", plugin_filter: Optional[str] = None, inventory: Optional[str] = None) -> DiagnosticsReport:
        summary = summarise_inventory(inventory)

        if hosts in ("all", "*"):
            target_hosts = summary.hosts[:]
        else:
            resolved: ResolvedHosts = resolve_hosts(hosts, inventory)
            if not resolved.validated:
                raise RuntimeError(resolved.error or f"No hosts matched selector '{hosts}'")
            target_hosts = resolved.hosts

        results: List[HostDiagnostics] = []
        errors: List[str] = []

        inventory_path = str(summary.inventory_path) if inventory else None
        
        for host in target_hosts:
            try:
                host_vars = summary.get_host_variables(host)
                payload = self._execute_risu(host, host_vars, plugin_filter or "", inventory_path)
                results.append(self._parse_payload(host, payload))
            except Exception as exc:
                errors.append(f"{host}: {exc}")

        status = "completed" if results and not errors else ("partial" if results else "failed")
        return DiagnosticsReport(status=status, hosts=results, errors=errors)

    # --- internals -----------------------------------------------------

    def _execute_risu(self, host: str, host_vars: Dict[str, str], plugin_filter: str, inventory: Optional[str] = None) -> Dict[str, Any]:
        """Execute RISU on a host using Ansible."""
        # Always use Ansible, even for localhost
        return self._run_remote_risu(host, host_vars, plugin_filter, inventory)


    def _run_remote_risu(self, host: str, host_vars: Dict[str, str], plugin_filter: str, inventory: Optional[str] = None) -> Dict[str, Any]:
        """Run RISU on host using Ansible command (works for both localhost and remote hosts)."""
        # Build RISU command
        risu_cmd = ["risu", "-l", "--numproc", "1"]
        if plugin_filter:
            risu_cmd.extend(["-i", plugin_filter])
        
        # Create remote script
        remote_script = (
            'set -euo pipefail; '
            'tmp="$(mktemp /tmp/risu-XXXX.json)"; '
            f"{' '.join(map(shlex.quote, risu_cmd))} --output \"$tmp\" > /tmp/risu-cli.log 2>&1; "
            'cat "$tmp"; '
            'rm -f "$tmp"'
        )
        
        # Build ansible command
        ansible_cmd = ["ansible", host, "-m", "shell", "-a", remote_script, "-o"]
        
        # Add inventory if provided
        if inventory:
            ansible_cmd.extend(["-i", inventory])
        
        # Add connection options from host_vars
        # For localhost, ensure ansible_connection=local is used
        if host in {"127.0.0.1", "localhost"} and "ansible_connection" not in host_vars:
            ansible_cmd.extend(["-c", "local"])
        elif connection := host_vars.get("ansible_connection"):
            ansible_cmd.extend(["-c", connection])
        
        if user := host_vars.get("ansible_user") or host_vars.get("ansible_ssh_user"):
            ansible_cmd.extend(["-u", user])
        
        if port := host_vars.get("ansible_port"):
            ansible_cmd.extend(["--ssh-extra-args", f"-p {port}"])
        
        if identity_file := host_vars.get("ansible_ssh_private_key_file"):
            ansible_cmd.extend(["--private-key", identity_file])
        
        if host_vars.get("ansible_become", "").lower() in {"true", "yes", "1"}:
            ansible_cmd.append("-b")
            if become_method := host_vars.get("ansible_become_method"):
                ansible_cmd.extend(["--become-method", become_method])
            if become_user := host_vars.get("ansible_become_user"):
                ansible_cmd.extend(["--become-user", become_user])
        
        # Execute ansible command
        proc = subprocess.run(ansible_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        
        if proc.returncode != 0:
            error = proc.stderr.strip() or proc.stdout.strip() or "Ansible execution failed"
            raise RuntimeError(f"Ansible failed (exit {proc.returncode}): {error}")
        
        # Parse ansible output (one-line format: hostname | SUCCESS | rc=0 | stdout='...')
        output = proc.stdout.strip()
        if not output:
            raise RuntimeError("Ansible produced empty output")
        
        # Extract JSON from ansible output
        # Format: "hostname | SUCCESS | rc=0 | stdout='{...json...}'"
        if "stdout=" in output:
            # Find the JSON part
            start = output.find("stdout='") + 8
            end = output.rfind("'")
            if start > 7 and end > start:
                json_str = output[start:end].replace("\\n", "\n").replace("\\'", "'")
            else:
                raise RuntimeError("Could not parse JSON from Ansible output")
        else:
            # Try to parse the whole output as JSON (if ansible was configured to output JSON)
            json_str = output
        
        payload = json.loads(json_str)
        payload.setdefault("logs", [])
        if proc.stderr.strip():
            payload["logs"].append(proc.stderr.strip())
        return payload

    def _parse_payload(self, host: str, payload: Dict[str, Any]) -> HostDiagnostics:
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
            message = result.get("err") or result.get("out") or plugin_data.get("description") or ""
            issues.append(
                DiagnosticIssue(
                    plugin=plugin_data.get("plugin") or plugin_id,
                    name=plugin_data.get("name") or plugin_id,
                    severity=_derive_severity(rc),
                    message=_normalise(message),
                    rc=rc,
                    category=plugin_data.get("category"),
                    subcategory=plugin_data.get("subcategory"),
                )
            )

        total_checks = len(results)
        skipped = max(total_checks - passed - failed, 0)
        metadata = dict(payload.get("metadata", {}))
        return HostDiagnostics(
            host=host,
            total_checks=total_checks,
            passed=passed,
            failed=failed,
            skipped=skipped,
            issues=issues,
            metadata=metadata,
        )


def _derive_severity(rc: Optional[int]) -> str:
    if rc is None or rc == 0:
        return "info"
    if rc >= 20:
        return "critical"
    if rc >= 10:
        return "major"
    if rc >= 5:
        return "warning"
    return "minor"


def _normalise(message: str, limit: int = 400) -> str:
    cleaned = message.strip()
    if len(cleaned) > limit:
        return cleaned[: limit - 3] + "..."
    return cleaned
