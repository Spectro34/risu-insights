from __future__ import annotations

import anyio
from pathlib import Path
from typing import Union

from mcp.server.fastmcp import FastMCP

from inventory import summarise_inventory
from runner import DiagnosticsRunner
from summary import format_report

runner = DiagnosticsRunner()


def _normalize_inventory(inventory: Union[str, bool, None]) -> str | None:
    """Normalize inventory parameter to a valid path or None."""
    if inventory is None or isinstance(inventory, bool):
        return None
    if not isinstance(inventory, str):
        return None
    
    inventory_str = inventory.strip()
    if not inventory_str or inventory_str.lower() in ("show inventory", "inventory", "true", "false", "none", "null", ""):
        return None
    
    inv_path = Path(inventory_str)
    if inv_path.exists() or inventory_str.startswith(('/', './', '../')):
        return inventory_str
    return None

mcp = FastMCP(
    name="RISU Diagnostics Server",
    instructions="Run RISU diagnostics on your inventory and receive clean reports. Use show_inventory to view inventory without running diagnostics.",
    streamable_http_path="/mcp",
    sse_path="/sse",
)


@mcp.tool()
async def show_inventory(inventory: Union[str, bool, None] = None) -> dict:
    """Show the inventory file contents without running diagnostics."""
    inventory_path = _normalize_inventory(inventory)
    summary = summarise_inventory(inventory_path)
    
    return {
        "inventory_path": str(summary.inventory_path),
        "total_hosts": len(summary.hosts),
        "hosts": summary.hosts,
        "groups": summary.groups,
        "group_vars": summary.group_vars,
        "host_vars": {host: summary.get_host_variables(host) for host in summary.hosts[:10]},
    }


@mcp.tool()
async def run_diagnostics(
    hosts: str = "localhost", 
    plugin_filter: Union[str, None] = None, 
    inventory: Union[str, bool, None] = None
) -> dict:
    """Execute RISU diagnostics and return structured results."""
    plugin_filter = plugin_filter.strip() if isinstance(plugin_filter, str) else ""
    inventory_path = _normalize_inventory(inventory)
    
    report = await anyio.to_thread.run_sync(runner.run, hosts, plugin_filter, inventory_path)
    summary = format_report(report)
    
    return {
        "status": report.status,
        "hosts": [host.host for host in report.hosts],
        "report": report.to_dict(),
        "summary": summary,
    }
