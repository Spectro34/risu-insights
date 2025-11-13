"""
CLI Entrypoints for MCP Server

Supports all three transport methods:
- STDIO (for mcphost, etc.)
- Streamable HTTP (direct HTTP support)
- SSE (Server-Sent Events for retrocompatibility)
"""

from __future__ import annotations

import anyio
import typer
import uvicorn

from config import configure_settings
from mcp_app import mcp


def stdio_main() -> None:
    """Entrypoint for STDIO mode."""
    typer.run(_stdio_command)


def http_main() -> None:
    """Entrypoint for HTTP mode (streamable-http and SSE)."""
    typer.run(_http_command)


def _stdio_command(
    inventory: str = typer.Option(None, help="Path to the inventory file"),
    runner_dir: str = typer.Option(None, help="Directory for runner artifacts"),
    project_root: str = typer.Option(None, help="Project root"),
) -> None:
    """Run the MCP server in STDIO mode."""
    configure_settings(project_root=project_root, inventory=inventory, runner_dir=runner_dir)
    anyio.run(mcp.run_stdio_async)


def _http_command(
    inventory: str = typer.Option(None, help="Path to the inventory file"),
    runner_dir: str = typer.Option(None, help="Directory for runner artifacts"),
    project_root: str = typer.Option(None, help="Project root"),
    host: str = typer.Option("0.0.0.0", help="HTTP host"),
    port: int = typer.Option(8080, help="HTTP port"),
) -> None:
    """Run the MCP server in HTTP mode (streamable-http and SSE endpoints)."""
    from http_app import app
    configure_settings(project_root=project_root, inventory=inventory, runner_dir=runner_dir)
    uvicorn.run(app, host=host, port=port, log_level="info")
