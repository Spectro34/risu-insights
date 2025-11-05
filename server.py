#!/usr/bin/env python3
"""
RISU Insights MCP server entrypoint.

This module wires the domain-specific helpers into FastMCP tools.  Each tool
returns structured dictionaries so the MCP client can present concise,
actionable information instead of raw log streams.
"""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from risu_insights.config import get_paths
from risu_insights.diagnostics import DiagnosticsError, run_diagnostics as execute_diagnostics
from risu_insights.formatters import format_diagnostics
from risu_insights.inventory import (
    GroupHosts,
    InventoryError,
    ResolvedHosts,
    summarise_inventory as summarise_inventory_data,
    resolve_hosts as resolve_inventory_selector,
    get_group_hosts as inventory_group_hosts,
)
from risu_insights.playbooks import (
    PlaybookError,
    list_playbooks as discover_playbooks,
    run_playbook as execute_playbook,
)


mcp = FastMCP("RISU Insights")


@mcp.tool()
def get_paths_info() -> dict:
    """Expose the resolved project paths for debugging."""
    paths = get_paths()
    return {
        "project_root": str(paths.project_root),
        "default_inventory": str(paths.default_inventory),
        "remediation_playbooks_dir": str(paths.remediation_playbooks_dir),
        "worker_playbooks_dir": str(paths.worker_playbooks_dir),
        "runner_dir": str(paths.runner_dir),
    }


@mcp.tool()
def list_inventory(inventory: Optional[str] = None) -> dict:
    """List all hosts and groups from the Ansible inventory."""
    try:
        summary = summarise_inventory_data(inventory)
        return summary.to_dict()
    except InventoryError as exc:
        return {"error": str(exc)}


@mcp.tool()
def resolve_hosts(selector: str, inventory: Optional[str] = None) -> dict:
    """Resolve host patterns to explicit hostnames."""
    resolved: ResolvedHosts = resolve_inventory_selector(selector, inventory)
    return resolved.to_dict()


@mcp.tool()
def get_group_hosts(group: str, inventory: Optional[str] = None) -> dict:
    """Get all hosts for a specific inventory group."""
    try:
        group_hosts: GroupHosts = inventory_group_hosts(group, inventory)
        return group_hosts.to_dict()
    except InventoryError as exc:
        return {"error": str(exc), "group": group}


@mcp.tool()
def run_diagnostics(
    hosts: str = "localhost",
    plugin_filter: Optional[str] = "",
    inventory: Optional[str] = None,
) -> dict:
    """
    Execute RISU diagnostics on the requested hosts and return structured results.
    """
    plugin_filter = plugin_filter or ""
    try:
        run = execute_diagnostics(hosts=hosts, plugin_filter=plugin_filter, inventory=inventory)
    except DiagnosticsError as exc:
        return {
            "status": "failed",
            "error": str(exc),
            "details": {"error": str(exc)},
            "output": str(exc),
        }

    details = run.to_dict()
    output = format_diagnostics(run.results, run.errors)
    return {
        "status": details.get("status"),
        "hosts": details.get("hosts"),
        "errors": details.get("errors"),
        "output": output,
        "details": details,
    }


@mcp.tool()
def list_playbooks() -> dict:
    """List all available remediation playbooks."""
    catalog = discover_playbooks()
    return catalog.to_dict()


@mcp.tool()
def run_playbook(
    playbook: str,
    hosts: str = "all",
    inventory: Optional[str] = None,
    check_mode: bool = False,
) -> dict:
    """
    Execute a remediation playbook, returning structured stats rather than raw logs.
    """
    try:
        run = execute_playbook(
            playbook=playbook,
            hosts=hosts,
            inventory=inventory,
            check_mode=check_mode,
        )
    except PlaybookError as exc:
        return {
            "status": "failed",
            "error": str(exc),
            "playbook": playbook,
            "details": {"error": str(exc)},
            "output": str(exc),
        }

    details = run.to_dict()
    summary = details.get("summary", "")
    return {
        "status": details.get("status"),
        "playbook": details.get("playbook"),
        "errors": details.get("errors"),
        "output": summary,
        "details": details,
    }


if __name__ == "__main__":
    mcp.run()
