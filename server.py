#!/usr/bin/env python3
"""
RISU Insights MCP Server (FastMCP)
Clean, simple implementation for RISU diagnostics via Model Context Protocol
"""

import os
import subprocess
import json
from pathlib import Path
from typing import Optional
from fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("RISU Insights")

# Project paths - configure via environment variables or defaults
PROJECT_ROOT = Path(os.getenv("RISU_INSIGHTS_ROOT", Path(__file__).parent))
WORKER_PLAYBOOKS_DIR = PROJECT_ROOT / "worker_playbooks"
REMEDIATION_PLAYBOOKS_DIR = PROJECT_ROOT / "remediation_playbooks"

# Note: Ansible module 'risu' should be installed system-wide at:
# ~/.ansible/plugins/modules/risu.py or /usr/share/ansible/plugins/modules/risu.py


# ============================================================================
# DIAGNOSTICS
# ============================================================================

@mcp.tool()
def run_diagnostics(
    target: str = "localhost",
    plugin_filter: str = "",
    inventory: Optional[str] = None
) -> dict:
    """
    Run RISU diagnostics on target host(s)
    
    Args:
        target: Hostname, IP, or 'localhost'
        plugin_filter: Filter plugins (e.g., 'sles', 'system', 'security')
        inventory: Path to Ansible inventory file
    
    Returns:
        Diagnostic results with issues found
    """
    if target == "localhost":
        # Use Ansible ad-hoc on localhost
        cmd = ["ansible", "localhost", "-c", "local", "-m", "risu"]
        args = f"state=run filter={plugin_filter} output=/tmp/risu-local.json"
    else:
        # Use playbook for remote execution
        cmd = ["ansible-playbook", str(WORKER_PLAYBOOKS_DIR / "run-diagnostics.yml")]
        if inventory:
            cmd.extend(["-i", inventory])
        cmd.extend(["--limit", target])
        if plugin_filter:
            cmd.extend(["-e", f"plugin_filter={plugin_filter}"])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    
    if result.returncode != 0:
        return {"error": "Diagnostic failed", "details": result.stderr}
    
    return {"status": "completed", "output": result.stdout}


# ============================================================================
# INSTALLATION
# ============================================================================

@mcp.tool()
def install_risu(
    hosts: str = "all",
    inventory: Optional[str] = None
) -> dict:
    """
    Install RISU package on managed nodes via zypper
    
    Args:
        hosts: Host pattern or group
        inventory: Ansible inventory file
    
    Returns:
        Installation results
    """
    cmd = ["ansible-playbook", str(WORKER_PLAYBOOKS_DIR / "install-risu-package.yml")]
    
    if inventory:
        cmd.extend(["-i", inventory])
    if hosts != "all":
        cmd.extend(["--limit", hosts])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    
    return {
        "status": "completed" if result.returncode == 0 else "failed",
        "output": result.stdout,
        "errors": result.stderr if result.returncode != 0 else None
    }


@mcp.tool()
def validate_installation(
    target: str = "localhost",
    inventory: Optional[str] = None
) -> dict:
    """
    Validate RISU is installed and working
    
    Args:
        target: Hostname or 'localhost'
        inventory: Ansible inventory file
    
    Returns:
        Installation status and version info
    """
    cmd = ["ansible", target, "-m", "risu", "-a", "state=validate"]
    
    if target == "localhost":
        cmd.extend(["-c", "local"])
    elif inventory:
        cmd.extend(["-i", inventory])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    return {
        "installed": result.returncode == 0,
        "output": result.stdout,
        "error": result.stderr if result.returncode != 0 else None
    }


# ============================================================================
# REMEDIATION
# ============================================================================

@mcp.tool()
def run_remediation(
    playbook: str,
    hosts: str = "all",
    inventory: Optional[str] = None,
    check_mode: bool = False
) -> dict:
    """
    Execute remediation playbook
    
    Args:
        playbook: Playbook filename (e.g., 'log-cleanup.yml')
        hosts: Host pattern
        inventory: Ansible inventory file
        check_mode: Dry-run mode
    
    Returns:
        Remediation execution results
    """
    playbook_path = REMEDIATION_PLAYBOOKS_DIR / playbook
    
    if not playbook_path.exists():
        return {"error": f"Playbook not found: {playbook}"}
    
    cmd = ["ansible-playbook", str(playbook_path)]
    
    if inventory:
        cmd.extend(["-i", inventory])
    if hosts != "all":
        cmd.extend(["--limit", hosts])
    if check_mode:
        cmd.append("--check")
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    
    return {
        "status": "completed" if result.returncode == 0 else "failed",
        "playbook": playbook,
        "output": result.stdout,
        "errors": result.stderr if result.returncode != 0 else None
    }


@mcp.tool()
def list_remediations() -> dict:
    """
    List available remediation playbooks
    
    Returns:
        List of available remediation playbooks
    """
    playbooks = []
    
    if REMEDIATION_PLAYBOOKS_DIR.exists():
        for file in REMEDIATION_PLAYBOOKS_DIR.glob("*.yml"):
            playbooks.append({
                "name": file.name,
                "path": str(file)
            })
    
    return {
        "count": len(playbooks),
        "playbooks": playbooks,
        "remediation_playbooks_dir": str(REMEDIATION_PLAYBOOKS_DIR)
    }


# ============================================================================
# ORCHESTRATION
# ============================================================================

@mcp.tool()
def self_heal(
    target: str,
    plugin_filter: str = "",
    inventory: Optional[str] = None,
    auto_remediate: bool = True
) -> dict:
    """
    Complete self-healing workflow: diagnose → remediate → verify
    
    Args:
        target: Target host
        plugin_filter: Plugin filter
        inventory: Ansible inventory
        auto_remediate: Automatically fix issues
    
    Returns:
        Complete workflow results
    """
    # Step 1: Diagnose
    diag_result = run_diagnostics(target, plugin_filter, inventory)
    
    if "error" in diag_result:
        return {"status": "failed", "step": "diagnostics", "details": diag_result}
    
    # Step 2: Remediate (if auto_remediate)
    if auto_remediate:
        # TODO: Parse diagnostic output for remediation hints
        # For now, return diagnostic results
        return {
            "status": "diagnosed",
            "diagnostics": diag_result,
            "message": "Diagnostics completed. Remediation mapping needed."
        }
    
    return {"status": "diagnosed", "diagnostics": diag_result}


# ============================================================================
# INFORMATION
# ============================================================================

@mcp.tool()
def list_inventory(inventory: str) -> dict:
    """
    List hosts and groups from Ansible inventory
    
    Args:
        inventory: Path to inventory file or directory
    
    Returns:
        Inventory structure with hosts and groups
    """
    cmd = ["ansible-inventory", "--list", "-i", inventory]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    if result.returncode != 0:
        return {"error": "Failed to parse inventory", "details": result.stderr}
    
    try:
        data = json.loads(result.stdout)
        hosts = list(data.get("_meta", {}).get("hostvars", {}).keys())
        
        return {
            "total_hosts": len(hosts),
            "hosts": hosts,
            "inventory": inventory
        }
    except json.JSONDecodeError:
        return {"error": "Invalid inventory format"}


@mcp.tool()
def resolve_hosts(
    selector: str,
    inventory: Optional[str] = None
) -> dict:
    """
    Resolve host pattern to concrete hostnames
    
    Args:
        selector: Host pattern (e.g., 'all', 'group:web', 'web*')
        inventory: Ansible inventory file
    
    Returns:
        List of matching hosts
    """
    cmd = ["ansible", selector, "--list-hosts"]
    
    if inventory:
        cmd.extend(["-i", inventory])
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    
    if result.returncode != 0:
        return {"error": "Failed to resolve hosts", "details": result.stderr}
    
    hosts = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and not line.startswith("hosts ("):
            hosts.append(line)
    
    return {
        "selector": selector,
        "count": len(hosts),
        "hosts": hosts
    }


# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    # Run with stdio transport (default for MCP)
    mcp.run()

