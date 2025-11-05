"""
Configuration helpers for the RISU Insights MCP server.

All filesystem paths are centralised here to avoid ad-hoc environment lookups.
Use :func:`get_paths` to obtain a cached :class:`Paths` object that exposes the
normalised project directories.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    """Container for all key filesystem paths used by the server."""

    project_root: Path
    default_inventory: Path
    remediation_playbooks_dir: Path
    worker_playbooks_dir: Path
    runner_dir: Path


def _resolve_project_root() -> Path:
    """Determine the project root taking environment overrides into account."""
    configured_root = os.getenv("RISU_INSIGHTS_ROOT")
    if configured_root:
        return Path(configured_root).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def get_paths() -> Paths:
    """
    Resolve and cache the commonly used project paths.

    The function also ensures all writable directories exist so callers can rely
    on their presence without additional checks.
    """

    project_root = _resolve_project_root()

    default_inventory_env = os.getenv("RISU_INSIGHTS_INVENTORY")
    if default_inventory_env:
        default_inventory = Path(default_inventory_env).expanduser().resolve()
    else:
        default_inventory = project_root / "inventory" / "hosts"

    remediation_playbooks_dir = project_root / "remediation_playbooks"
    worker_playbooks_dir = project_root / "worker_playbooks"
    runner_dir = project_root / ".ansible-runner"

    for path in (remediation_playbooks_dir, worker_playbooks_dir, runner_dir):
        path.mkdir(parents=True, exist_ok=True, mode=0o755)

    return Paths(
        project_root=project_root,
        default_inventory=default_inventory,
        remediation_playbooks_dir=remediation_playbooks_dir,
        worker_playbooks_dir=worker_playbooks_dir,
        runner_dir=runner_dir,
    )
