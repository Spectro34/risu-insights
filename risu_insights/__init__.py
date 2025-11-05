"""
Core package for the RISU Insights MCP server.

This package provides cohesive modules for inventory inspection, diagnostics
execution, remediation playbook orchestration, and output formatting.  Each
module is designed to be testable and to return structured data so the MCP
layer can focus on marshalling responses.
"""

from .config import get_paths, Paths  # noqa: F401
from .diagnostics import DiagnosticsRun, DiagnosticResult, DiagnosticIssue  # noqa: F401
from .inventory import InventorySummary, ResolvedHosts, GroupHosts  # noqa: F401
from .playbooks import PlaybookCatalog, PlaybookRun  # noqa: F401
