from __future__ import annotations

import anyio
from pathlib import Path
from typing import Union

from mcp.server.fastmcp import FastMCP

from inventory import summarise_inventory
from runner import DiagnosticsRunner
from summary import format_report

runner = DiagnosticsRunner()


def _normalize_inventory(inventory: Union[str, bool, None, dict, list]) -> str | None:
    """Normalize inventory parameter to a valid path or None."""
    # Handle empty dict/array from OpenWebUI/mcpo
    if inventory is None or isinstance(inventory, bool) or inventory == {} or inventory == []:
        return None
    if not isinstance(inventory, str):
        return None
    
    inventory_str = inventory.strip()
    if not inventory_str or inventory_str.lower() in ("show inventory", "inventory", "true", "false", "none", "null", ""):
        return None
    
    inv_path = Path(inventory_str)
    # Resolve path to prevent path traversal attacks
    try:
        resolved = inv_path.resolve()
        # Only allow paths that exist and are within reasonable bounds
        if inv_path.exists() and not str(resolved).startswith('..'):
            return str(resolved)
    except (OSError, ValueError):
        pass
    return None


def _normalize_plugin_filter(plugin_filter: Union[str, None, dict, list]) -> str:
    """Normalize plugin_filter parameter to a valid string or empty string."""
    # Handle empty dict/array from OpenWebUI/mcpo
    if plugin_filter is None or plugin_filter == {} or plugin_filter == []:
        return ""
    if not isinstance(plugin_filter, str):
        return ""
    
    plugin_filter_str = plugin_filter.strip()
    if not plugin_filter_str or plugin_filter_str.lower() in ("none", "null", ""):
        return ""
    return plugin_filter_str

mcp = FastMCP(
    name="RISU Diagnostics Server",
    instructions="Run RISU diagnostics on your inventory and receive clean reports. Use show_inventory to view inventory without running diagnostics.",
    streamable_http_path="/mcp",
    sse_path="/sse",
)


@mcp.tool()
async def show_inventory(inventory: Union[str, bool, None, dict, list] = None) -> dict:
    """Show the inventory file contents without running diagnostics."""
    inventory_path = _normalize_inventory(inventory)
    summary = summarise_inventory(inventory_path)
    
    # Filter out sensitive data from host_vars
    def sanitize_host_vars(vars_dict: dict) -> dict:
        """Remove sensitive keys from host variables."""
        sensitive_keys = {
            "ansible_ssh_private_key_file", "ansible_ssh_pass", "ansible_password",
            "ansible_become_password", "ansible_vault_password", "ansible_ssh_common_args"
        }
        return {k: v for k, v in vars_dict.items() if k not in sensitive_keys}
    
    return {
        "inventory_path": str(summary.inventory_path),
        "total_hosts": len(summary.hosts),
        "hosts": summary.hosts,
        "groups": summary.groups,
        "group_vars": {k: sanitize_host_vars(v) for k, v in summary.group_vars.items()},
        "host_vars": {host: sanitize_host_vars(summary.get_host_variables(host)) for host in summary.hosts[:10]},
    }


@mcp.tool()
async def run_diagnostics(
    hosts: str = "localhost", 
    plugin_filter: Union[str, None, dict, list] = None, 
    inventory: Union[str, bool, None, dict, list] = None
) -> dict:
    """Execute RISU diagnostics and return structured results."""
    plugin_filter_str = _normalize_plugin_filter(plugin_filter)
    inventory_path = _normalize_inventory(inventory)
    
    report = await anyio.to_thread.run_sync(runner.run, hosts, plugin_filter_str, inventory_path)
    summary = format_report(report)
    
    return {
        "status": report.status,
        "hosts": [host.host for host in report.hosts],
        "report": report.to_dict(),
        "summary": summary,
    }
