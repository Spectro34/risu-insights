"""
Lightweight inventory helpers that do not rely on spawning Ansible commands.

The parser implemented here covers common INI-style inventories with host lists,
group definitions, and simple `:children` sections. It trades full Ansible
parity for the predictability required in constrained execution environments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Optional

from .config import get_paths


class InventoryError(RuntimeError):
    """Raised when inventory operations cannot be completed."""


@dataclass
class InventorySummary:
    inventory_path: Path
    hosts: List[str] = field(default_factory=list)
    groups: Dict[str, List[str]] = field(default_factory=dict)
    group_vars: Dict[str, Dict[str, str]] = field(default_factory=dict)
    host_vars: Dict[str, Dict[str, str]] = field(default_factory=dict)

    @property
    def total_hosts(self) -> int:
        return len(self.hosts)

    def to_dict(self) -> Dict[str, object]:
        return {
            "inventory": str(self.inventory_path),
            "total_hosts": self.total_hosts,
            "hosts": self.hosts,
            "groups": self.groups,
        }

    def get_host_variables(self, host: str) -> Dict[str, str]:
        combined: Dict[str, str] = {}
        combined.update(self.group_vars.get("all", {}))
        for group_name, group_hosts in self.groups.items():
            if group_name == "all":
                continue
            if host in group_hosts:
                combined.update(self.group_vars.get(group_name, {}))
        combined.update(self.host_vars.get(host, {}))
        return combined


@dataclass
class ResolvedHosts:
    selector: str
    hosts: List[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def count(self) -> int:
        return len(self.hosts)

    @property
    def validated(self) -> bool:
        return self.count > 0 and not self.error

    def to_dict(self) -> Dict[str, object]:
        data = {
            "selector": self.selector,
            "count": self.count,
            "hosts": self.hosts,
            "validated": self.validated,
        }
        if self.error:
            data["error"] = self.error
        return data


@dataclass
class GroupHosts:
    group: str
    hosts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "group": self.group,
            "count": len(self.hosts),
            "hosts": self.hosts,
        }


def _load_inventory_file(inventory: Optional[str] = None) -> Path:
    paths = get_paths()
    inventory_path = Path(inventory).expanduser() if inventory else paths.default_inventory
    if not inventory_path.exists():
        raise InventoryError(f"Inventory not found: {inventory_path}")
    return inventory_path


SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _parse_inventory_file(inventory_path: Path) -> InventorySummary:
    groups: Dict[str, List[str]] = {}
    children_map: Dict[str, List[str]] = {}
    group_vars: Dict[str, Dict[str, str]] = {}
    host_vars: Dict[str, Dict[str, str]] = {}
    all_hosts: List[str] = []

    current_group: Optional[str] = None
    current_children_parent: Optional[str] = None
    current_vars_group: Optional[str] = None

    with inventory_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            match = SECTION_RE.match(line)
            if match:
                section = match.group(1)
                current_group = None
                current_children_parent = None
                current_vars_group = None

                if section.endswith(":vars"):
                    current_vars_group = section.split(":")[0]
                    group_vars.setdefault(current_vars_group, {})
                    continue

                if section.endswith(":children"):
                    current_children_parent = section.split(":")[0]
                    children_map.setdefault(current_children_parent, [])
                    continue

                current_group = section
                groups.setdefault(current_group, [])
                continue

            if current_children_parent:
                child = line.split()[0]
                children_map.setdefault(current_children_parent, []).append(child)
                continue

            if current_vars_group:
                if "=" in line:
                    key, value = line.split("=", 1)
                    group_vars.setdefault(current_vars_group, {})[key.strip()] = value.strip()
                continue

            host = line.split()[0]
            all_hosts.append(host)

            if current_group:
                groups.setdefault(current_group, []).append(host)
            else:
                groups.setdefault("ungrouped", []).append(host)

            parts = line.split()
            if len(parts) > 1:
                assignments = {}
                for part in parts[1:]:
                    if "=" not in part:
                        continue
                    key, value = part.split("=", 1)
                    assignments[key.strip()] = value.strip()
                if assignments:
                    host_vars.setdefault(host, {}).update(assignments)

    # Resolve children relationships
    for parent, child_groups in children_map.items():
        aggregated: List[str] = []
        for child in child_groups:
            aggregated.extend(groups.get(child, []))
        groups.setdefault(parent, [])
        groups[parent].extend(aggregated)
        groups[parent] = _dedupe_preserve_order(groups[parent])

    # Ensure the all group contains every host mentioned.
    if "all" not in groups:
        aggregated = all_hosts[:]
        for host_list in groups.values():
            aggregated.extend(host_list)
        groups["all"] = _dedupe_preserve_order(aggregated)

    hosts = _dedupe_preserve_order(groups.get("all", all_hosts))

    return InventorySummary(
        inventory_path=inventory_path,
        hosts=hosts,
        groups=groups,
        group_vars=group_vars,
        host_vars=host_vars,
    )


def summarise_inventory(inventory: Optional[str] = None) -> InventorySummary:
    inventory_path = _load_inventory_file(inventory)
    return _parse_inventory_file(inventory_path)


def _expand_selector(selector: str, summary: InventorySummary) -> List[str]:
    selector = selector.strip()
    if not selector or selector == "all":
        return summary.hosts[:]

    if selector in summary.groups:
        return summary.groups[selector][:]

    if selector in summary.hosts:
        return [selector]

    matches = [host for host in summary.hosts if fnmatch(host, selector)]
    return matches


def resolve_hosts(selector: str, inventory: Optional[str] = None) -> ResolvedHosts:
    summary = summarise_inventory(inventory)

    tokens = [tok.strip() for tok in re.split(r"[,:]", selector) if tok.strip()]
    include_tokens: List[str] = []
    exclude_tokens: List[str] = []
    for token in tokens:
        if token.startswith("!"):
            exclude_tokens.append(token[1:])
        else:
            include_tokens.append(token)

    if not include_tokens and exclude_tokens:
        include_tokens = ["all"]

    expanded: List[str] = []
    for token in include_tokens or ["all"]:
        expanded.extend(_expand_selector(token, summary))

    if exclude_tokens:
        exclusions: List[str] = []
        for token in exclude_tokens:
            exclusions.extend(_expand_selector(token, summary))
        exclusion_set = set(exclusions)
        expanded = [host for host in expanded if host not in exclusion_set]

    expanded = _dedupe_preserve_order(expanded)

    if not expanded:
        return ResolvedHosts(selector=selector, error=f"No hosts matched selector '{selector}'")

    return ResolvedHosts(selector=selector, hosts=expanded)


def get_group_hosts(group: str, inventory: Optional[str] = None) -> GroupHosts:
    summary = summarise_inventory(inventory)
    return GroupHosts(group=group, hosts=summary.groups.get(group, []))
