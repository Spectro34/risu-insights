#!/usr/bin/env python3
"""Smoke tests for key RISU Insights helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import server
from risu_insights.diagnostics import parse_risu_payload
from risu_insights.formatters import format_diagnostics


# Ensure Ansible writes temp files inside the repository sandbox when invoked.
_ansible_tmp = Path("tmp/ansible")
_ansible_tmp.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("ANSIBLE_LOCAL_TEMP", str(_ansible_tmp.resolve()))
os.environ.setdefault("ANSIBLE_REMOTE_TMP", str(_ansible_tmp.resolve()))


# Access the original callables that FastMCP wraps
list_playbooks = server.list_playbooks.fn
get_paths_info = server.get_paths_info.fn
run_playbook = server.run_playbook.fn


def _load_sample_payload() -> dict:
    """Return a minimal RISU payload for parser smoke testing."""
    sample_path = Path("dev/risu-insights/results/ec2-node-2-risu.json")
    if sample_path.exists():
        return json.loads(sample_path.read_text())

    return {
        "metadata": {
            "when": "2025-01-01T00:00:00Z",
            "live": False,
            "source": "risu",
            "time": 1.23,
        },
        "results": {
            "sample-plugin": {
                "plugin": "/path/sample-plugin.sh",
                "backend": "shell",
                "id": "sample-plugin",
                "category": "system",
                "subcategory": "",
                "hash": "deadbeef",
                "name": "sample-plugin",
                "description": "Sample plugin description",
                "result": {
                    "rc": 1,
                    "out": "",
                    "err": "Sample plugin failure",
                },
                "time": 0.1,
            }
        },
    }


def test_paths_info() -> None:
    info = get_paths_info()
    assert "project_root" in info
    assert Path(info["project_root"]).exists()


def test_diagnostics_parser_and_formatter() -> None:
    payload = _load_sample_payload()
    result = parse_risu_payload("sample-host", payload)
    assert result.host == "sample-host"
    assert result.total_checks >= result.issues_found

    formatted = format_diagnostics([result])
    assert "HOST: sample-host" in formatted


def test_playbook_listing() -> None:
    catalog = list_playbooks()
    assert "playbooks" in catalog


def test_run_playbook_failure_returns_output() -> None:
    result = run_playbook(playbook="nonexistent-demo-playbook")
    assert result["status"] == "failed"
    assert result["output"]
    assert "details" in result


if __name__ == "__main__":
    test_paths_info()
    test_diagnostics_parser_and_formatter()
    test_playbook_listing()
    test_run_playbook_failure_returns_output()
    print("\u2713 Smoke tests passed")
