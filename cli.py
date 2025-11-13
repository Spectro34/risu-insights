from __future__ import annotations

import anyio
import typer
import uvicorn

from config import configure_settings
from http_app import app
from mcp_app import mcp


def http_main() -> None:
    typer.run(_http_command)


def stdio_main() -> None:
    typer.run(_stdio_command)


def _http_command(
    inventory: str = typer.Option(None, help="Path to the inventory file"),
    runner_dir: str = typer.Option(None, help="Directory for runner artifacts"),
    project_root: str = typer.Option(None, help="Project root"),
    host: str = typer.Option("0.0.0.0", help="HTTP host"),
    port: int = typer.Option(8080, help="HTTP port"),
) -> None:
    configure_settings(project_root=project_root, inventory=inventory, runner_dir=runner_dir)
    uvicorn.run(app, host=host, port=port, log_level="info")


def _stdio_command(
    inventory: str = typer.Option(None, help="Path to the inventory file"),
    runner_dir: str = typer.Option(None, help="Directory for runner artifacts"),
    project_root: str = typer.Option(None, help="Project root"),
) -> None:
    configure_settings(project_root=project_root, inventory=inventory, runner_dir=runner_dir)
    anyio.run(mcp.run_stdio_async)
