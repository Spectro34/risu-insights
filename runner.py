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

        resolved: ResolvedHosts | None = None
        if hosts in ("all", "*"):
            target_hosts = summary.hosts[:]
        else:
            resolved = resolve_hosts(hosts, inventory)
            if not resolved.validated:
                raise RuntimeError(resolved.error or f"No hosts matched selector '{hosts}'")
            target_hosts = resolved.hosts

        results: List[HostDiagnostics] = []
        errors: List[str] = []
        
        # Log warning if some selectors didn't match but we have hosts
        if resolved and resolved.error and resolved.error.startswith("Some selectors"):
            errors.append(f"Warning: {resolved.error}")

        # Always use the inventory path that was used to resolve hosts
        inventory_path = str(summary.inventory_path)
        
        for host in target_hosts:
            try:
                payload = self._execute_risu(host, plugin_filter or "", inventory_path)
                results.append(self._parse_payload(host, payload))
            except Exception as exc:
                errors.append(f"{host}: {exc}")

        status = "completed" if results and not errors else ("partial" if results else "failed")
        return DiagnosticsReport(status=status, hosts=results, errors=errors)

    # --- internals -----------------------------------------------------

    def _execute_risu(self, host: str, plugin_filter: str, inventory: Optional[str] = None) -> Dict[str, Any]:
        """Execute RISU on a host. Uses direct execution for localhost, Ansible for remote hosts."""
        return self._run_remote_risu(host, plugin_filter, inventory)


    def _run_remote_risu(self, host: str, plugin_filter: str, inventory: Optional[str] = None) -> Dict[str, Any]:
        """Run RISU on host. For localhost, runs directly. For remote hosts, uses Ansible."""
        import os
        
        # Build RISU command
        risu_cmd = ["risu", "-l", "--numproc", "1"]
        if plugin_filter:
            risu_cmd.extend(["-i", plugin_filter])
        
        # Use a fixed temp file path
        remote_json_path = f"/tmp/risu-output-{os.getpid()}.json"
        is_localhost = host in {"127.0.0.1", "localhost"}
        
        # For localhost, run RISU directly without Ansible
        if is_localhost:
            risu_cmd.extend(["--output", remote_json_path])
            proc = subprocess.run(risu_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            
            # Read the JSON file
            try:
                with open(remote_json_path, 'r', encoding='utf-8') as f:
                    json_str = f.read()
            except FileNotFoundError:
                error = proc.stderr.strip() or proc.stdout.strip() or "RISU execution failed"
                raise RuntimeError(f"RISU output file not found: {remote_json_path}. RISU stderr: {error}")
            except Exception as e:
                raise RuntimeError(f"Failed to read RISU output file: {e}")
            finally:
                # Clean up
                try:
                    os.remove(remote_json_path)
                except:
                    pass
            
            # Store stderr in logs for diagnostics
            stderr_log = proc.stderr.strip() if proc.stderr.strip() else None
        else:
            # For remote hosts, use Ansible
            # Create remote script that writes JSON to a file
            remote_script = (
                'set -euo pipefail; '
                f'tmp="{remote_json_path}"; '
                f"if {' '.join(map(shlex.quote, risu_cmd))} --output \"$tmp\" 2>&1; then "
                '  if [ -f "$tmp" ] && [ -s "$tmp" ]; then '
                '    echo "SUCCESS: JSON written to $tmp"; '
                '  else '
                '    echo "ERROR: RISU output file is missing or empty" >&2; '
                '    exit 1; '
                '  fi '
                'else '
                '  rc=$?; '
                '  echo "ERROR: RISU command failed with exit code $rc" >&2; '
                '  exit $rc; '
                'fi'
            )
            
            # Build ansible command - let Ansible handle all connection management
            # Always provide inventory so Ansible can find the host
            ansible_cmd = ["ansible", host, "-m", "shell", "-a", remote_script]
            if inventory:
                ansible_cmd.extend(["-i", inventory])
            
            # Execute ansible command to run RISU
            proc = subprocess.run(ansible_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            
            # Check for errors
            if proc.returncode != 0:
                error = proc.stderr.strip() or proc.stdout.strip() or "Ansible execution failed"
                raise RuntimeError(f"Ansible failed (exit {proc.returncode}): {error}")
            
            # Check if RISU execution succeeded
            if "SUCCESS: JSON written" not in proc.stdout:
                error_msg = proc.stdout.strip() or proc.stderr.strip() or "RISU execution failed"
                raise RuntimeError(f"RISU execution failed: {error_msg}")
            
            # Use Ansible's slurp module for remote hosts
            # Always provide inventory so Ansible can find the host
            slurp_cmd = ["ansible", host, "-m", "slurp", "-a", f"src={remote_json_path}"]
            if inventory:
                slurp_cmd.extend(["-i", inventory])
            
            # Fetch the JSON file
            slurp_proc = subprocess.run(slurp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            
            if slurp_proc.returncode != 0:
                raise RuntimeError(f"Failed to read RISU output file: {slurp_proc.stderr.strip() or slurp_proc.stdout.strip()}")
            
            # Parse slurp output - Ansible returns JSON in various formats
            slurp_output_raw = slurp_proc.stdout.strip()
            slurp_output = None
            
            # Try to find JSON in the output - could be in different formats
            # Format 1: Direct JSON object
            if slurp_output_raw.startswith("{"):
                try:
                    slurp_output = json.loads(slurp_output_raw)
                except json.JSONDecodeError:
                    pass
            
            # Format 2: "hostname | SUCCESS => { ... }" format (most common)
            if not slurp_output and "=>" in slurp_output_raw:
                # Find the JSON object after "=>"
                json_start = slurp_output_raw.find("=>")
                if json_start >= 0:
                    # Skip "=> " and find the opening brace
                    json_start = slurp_output_raw.find("{", json_start)
                    if json_start >= 0:
                        # Find matching closing brace
                        brace_count = 0
                        json_end = json_start
                        for i in range(json_start, len(slurp_output_raw)):
                            if slurp_output_raw[i] == "{":
                                brace_count += 1
                            elif slurp_output_raw[i] == "}":
                                brace_count -= 1
                                if brace_count == 0:
                                    json_end = i + 1
                                    break
                        if json_end > json_start:
                            try:
                                slurp_output = json.loads(slurp_output_raw[json_start:json_end])
                            except json.JSONDecodeError:
                                pass
            
            # Format 3: stdout='...' format (one-line output)
            if not slurp_output and "stdout='" in slurp_output_raw:
                start = slurp_output_raw.find("stdout='") + 8
                if start > 7:
                    # Find matching closing quote (handle escaped quotes)
                    end = start
                    while end < len(slurp_output_raw):
                        if slurp_output_raw[end] == "'" and (end == start or slurp_output_raw[end-1] != "\\"):
                            break
                        end += 1
                    if end > start:
                        slurp_json_str = slurp_output_raw[start:end].replace("\\n", "\n").replace("\\'", "'").replace("\\\\", "\\")
                        try:
                            slurp_output = json.loads(slurp_json_str)
                        except json.JSONDecodeError:
                            pass
            
            # Format 4: Multi-line JSON (look for JSON object anywhere in output)
            if not slurp_output:
                # Try to find JSON object boundaries
                json_start = slurp_output_raw.find('{"')
                if json_start >= 0:
                    # Find matching closing brace
                    brace_count = 0
                    json_end = json_start
                    for i in range(json_start, len(slurp_output_raw)):
                        if slurp_output_raw[i] == "{":
                            brace_count += 1
                        elif slurp_output_raw[i] == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                json_end = i + 1
                                break
                    if json_end > json_start:
                        try:
                            slurp_output = json.loads(slurp_output_raw[json_start:json_end])
                        except json.JSONDecodeError:
                            pass
            
            if not slurp_output:
                raise RuntimeError(f"Could not extract JSON from slurp output. Raw output (first 1000 chars): {slurp_output_raw[:1000]}")
            
            # Extract content from slurp response
            if "content" not in slurp_output:
                raise RuntimeError(f"Unexpected slurp output format. Expected 'content' field. Got keys: {list(slurp_output.keys())}. Output: {slurp_output_raw[:500]}")
            
            # Decode base64 content
            import base64
            try:
                json_bytes = base64.b64decode(slurp_output["content"])
                json_str = json_bytes.decode("utf-8")
            except (ValueError, UnicodeDecodeError) as e:
                raise RuntimeError(f"Failed to decode base64 content from slurp: {e}. Content preview: {str(slurp_output.get('content', ''))[:100]}")
            
            # Clean up remote file
            # Always provide inventory so Ansible can find the host
            cleanup_cmd = ["ansible", host, "-m", "file", "-a", f"path={remote_json_path} state=absent"]
            if inventory:
                cleanup_cmd.extend(["-i", inventory])
            subprocess.run(cleanup_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            
            stderr_log = proc.stderr.strip() if proc.stderr.strip() else None
        
        # Parse the RISU JSON payload
        # The actual RISU payload structure parsing is handled by _parse_payload()
        try:
            payload = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse RISU JSON output: {e}. JSON preview: {json_str[:500]}")
        
        payload.setdefault("logs", [])
        if stderr_log:
            payload["logs"].append(stderr_log)
        
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
