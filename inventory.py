from __future__ import annotations

import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Optional

from config import Settings, get_settings


class InventoryError(RuntimeError):
    pass


SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")


@dataclass
class InventorySummary:
    inventory_path: Path
    hosts: List[str] = field(default_factory=list)
    groups: Dict[str, List[str]] = field(default_factory=dict)
    group_vars: Dict[str, Dict[str, str]] = field(default_factory=dict)
    host_vars: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "inventory": str(self.inventory_path),
            "total_hosts": len(self.hosts),
            "groups": self.groups,
        }

    def get_host_variables(self, host: str) -> Dict[str, str]:
        combined: Dict[str, str] = {}
        combined.update(self.group_vars.get("all", {}))
        for group, members in self.groups.items():
            if group == "all":
                continue
            if host in members:
                combined.update(self.group_vars.get(group, {}))
        combined.update(self.host_vars.get(host, {}))
        return combined


@dataclass
class ResolvedHosts:
    selector: str
    hosts: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def validated(self) -> bool:
        return bool(self.hosts) and self.error is None

    def to_dict(self) -> Dict[str, object]:
        data = {"selector": self.selector, "hosts": self.hosts, "count": len(self.hosts), "validated": self.validated}
        if self.error:
            data["error"] = self.error
        return data


def _load_inventory(settings: Settings, override: str | Path | None = None) -> Path:
    inventory_path = Path(override).expanduser() if override else settings.inventory_path
    if not inventory_path.exists():
        raise InventoryError(f"Inventory not found: {inventory_path}")
    return inventory_path


def parse_inventory(inventory_path: Path) -> InventorySummary:
    groups: Dict[str, List[str]] = {}
    children: Dict[str, List[str]] = {}
    hosts: List[str] = []
    group_vars: Dict[str, Dict[str, str]] = {}
    host_vars: Dict[str, Dict[str, str]] = {}

    current_group: str | None = None
    current_children: str | None = None
    current_vars_group: str | None = None

    with inventory_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            match = SECTION_RE.match(line)
            if match:
                section = match.group(1)
                current_group = None
                current_children = None
                current_vars_group = None

                if section.endswith(":children"):
                    parent = section.split(":")[0]
                    current_children = parent
                    children.setdefault(parent, [])
                    continue

                if section.endswith(":vars"):
                    current_vars_group = section.split(":")[0]
                    group_vars.setdefault(current_vars_group, {})
                    continue

                current_group = section
                groups.setdefault(current_group, [])
                continue

            if current_children:
                children[current_children].append(line.split()[0])
                continue

            if current_vars_group:
                if "=" in line:
                    key, value = line.split("=", 1)
                    group_vars.setdefault(current_vars_group, {})[key.strip()] = value.strip()
                continue

            parts = line.split()
            host = parts[0]
            hosts.append(host)
            target_group = current_group or "ungrouped"
            groups.setdefault(target_group, []).append(host)

            assignments = {}
            for assignment in parts[1:]:
                if "=" not in assignment:
                    continue
                key, value = assignment.split("=", 1)
                assignments[key.strip()] = value.strip()
            if assignments:
                host_vars.setdefault(host, {}).update(assignments)

    for parent, child_list in children.items():
        aggregate: List[str] = []
        for child in child_list:
            aggregate.extend(groups.get(child, []))
        groups.setdefault(parent, [])
        groups[parent] = _dedupe(groups[parent] + aggregate)

    if "all" not in groups:
        groups["all"] = _dedupe(hosts[:])

    return InventorySummary(
        inventory_path=inventory_path,
        hosts=_dedupe(groups["all"]),
        groups=groups,
        group_vars=group_vars,
        host_vars=host_vars,
    )


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def summarise_inventory(inventory: str | Path | None = None) -> InventorySummary:
    settings = get_settings()
    inventory_path = _load_inventory(settings, inventory)
    return parse_inventory(inventory_path)


def resolve_hosts(selector: str, inventory: str | Path | None = None) -> ResolvedHosts:
    summary = summarise_inventory(inventory)

    tokens = [token.strip() for token in re.split(r"[,:]", selector) if token.strip()]
    includes = [token for token in tokens if not token.startswith("!")]
    excludes = [token[1:] for token in tokens if token.startswith("!")]

    if not includes and excludes:
        includes = ["all"]

    expanded: List[str] = []
    for token in includes or ["all"]:
        expanded.extend(_expand_token(token, summary))

    if excludes:
        exclusion_set = {host for token in excludes for host in _expand_token(token, summary)}
        expanded = [host for host in expanded if host not in exclusion_set]

    expanded = _dedupe(expanded)
    if not expanded:
        return ResolvedHosts(selector=selector, error=f"No hosts matched selector '{selector}'")

    return ResolvedHosts(selector=selector, hosts=expanded)


def _expand_token(token: str, summary: InventorySummary) -> List[str]:
    token = token.strip()
    if not token or token == "all":
        return summary.hosts[:]
    if token in summary.groups:
        return summary.groups[token][:]
    if token in summary.hosts:
        return [token]
    return [host for host in summary.hosts if fnmatch(host, token)]
