"""Utilities for generating combined port availability data."""

import json
from typing import Dict, List

PortMap = Dict[str, List[int]]

def merge_ports(occupied: PortMap, available: PortMap) -> Dict[str, Dict[str, List[int]]]:
    """Merge occupied and available port mappings.

    Args:
        occupied: mapping of project name to list of occupied ports.
        available: mapping of project name to list of available ports.

    Returns:
        A mapping where each project contains ``occupied_ports`` and
        ``available_ports`` lists. Projects with both lists empty are omitted.
    """
    result: Dict[str, Dict[str, List[int]]] = {}
    projects = set(occupied) | set(available)
    for project in projects:
        occ = occupied.get(project, [])
        avail = available.get(project, [])
        if occ or avail:
            result[project] = {
                "occupied_ports": occ,
                "available_ports": avail,
            }
    return result


def load_json(path: str) -> Dict[str, List[int]]:
    with open(path, "r") as fh:
        return json.load(fh)


def save_json(path: str, data: Dict[str, Dict[str, List[int]]]) -> None:
    with open(path, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))


def generate_ports_json(occupied_path: str, available_path: str, out_path: str) -> Dict[str, Dict[str, List[int]]]:
    occupied = load_json(occupied_path)
    available = load_json(available_path)
    merged = merge_ports(occupied, available)
    save_json(out_path, merged)
    return merged


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 4:
        raise SystemExit("Usage: generate_ports_json.py <occupied.json> <available.json> <out.json>")
    generate_ports_json(sys.argv[1], sys.argv[2], sys.argv[3])
