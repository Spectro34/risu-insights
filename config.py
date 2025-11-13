from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Centralised filesystem settings for the RISU diagnostics MCP server."""

    project_root: Path
    inventory_path: Path
    runner_dir: Path

    @classmethod
    def load(
        cls,
        project_root: str | Path | None = None,
        inventory: str | Path | None = None,
        runner_dir: str | Path | None = None,
    ) -> "Settings":
        root_env = os.getenv("RISU_DIAG_ROOT")
        project_root_path = Path(project_root or root_env or Path.cwd()).resolve()

        inventory_env = os.getenv("RISU_DIAG_INVENTORY")
        inventory_path = Path(inventory or inventory_env or project_root_path / "inventory" / "hosts").expanduser().resolve()

        runner_env = os.getenv("RISU_DIAG_RUNNER_DIR")
        runner_path = Path(runner_dir or runner_env or project_root_path / ".ansible-runner").expanduser().resolve()
        runner_path.mkdir(parents=True, exist_ok=True, mode=0o755)

        return cls(project_root=project_root_path, inventory_path=inventory_path, runner_dir=runner_path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()


def configure_settings(project_root: str | Path | None = None, inventory: str | Path | None = None, runner_dir: str | Path | None = None) -> Settings:
    if project_root is not None:
        os.environ["RISU_DIAG_ROOT"] = str(project_root)
    if inventory is not None:
        os.environ["RISU_DIAG_INVENTORY"] = str(inventory)
    if runner_dir is not None:
        os.environ["RISU_DIAG_RUNNER_DIR"] = str(runner_dir)
    get_settings.cache_clear()
    return get_settings()
