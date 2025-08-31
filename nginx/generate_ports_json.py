#!/usr/bin/env python3
"""Generate ports.json for dashboard from mapping files."""
import json
from datetime import datetime
import os
from typing import Dict, Optional
from urllib.request import urlopen
from urllib.error import URLError

IP_MAPPING_FILE = os.getenv("IP_MAPPING_FILE", "/usr/share/nginx/html/ip_mapping.json")
PORT_MAPPING_FILE = os.getenv("PORT_MAPPING_FILE", "/usr/share/nginx/html/port_mapping.json")
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "/var/lib/flux-dashboard/ports.json")
UPTIME_FILE = os.getenv("UPTIME_FILE", "/var/lib/flux-dashboard/uptime.json")

def load_json(path: str):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

def lookup_country(ip: str):
    if not ip:
        return None
    try:
        with urlopen(f"https://ipinfo.io/{ip}/country", timeout=5) as resp:
            return resp.read().decode().strip()
    except URLError:
        return None


def main(now: Optional[datetime] = None):
    if now is None:
        now = datetime.utcnow()

    ip_mapping = load_json(IP_MAPPING_FILE)
    port_mapping = load_json(PORT_MAPPING_FILE)
    uptime_map: Dict[str, Dict[str, str]] = load_json(UPTIME_FILE)

    result = {
        "generatedAt": now.isoformat(timespec="seconds") + "Z",
        "projects": [],
    }

    for project, ports in port_mapping.items():
        ips = ip_mapping.get(project, [])
        external_ip = ips[0] if ips else None
        country = lookup_country(external_ip) if external_ip else None
        project_entry = {"id": project, "name": project, "ports": []}
        for port in ports:
            port_key = str(port)
            if external_ip:
                proj_times = uptime_map.setdefault(project, {})
                started = proj_times.get(port_key)
                if not started:
                    started = now.isoformat()
                    proj_times[port_key] = started
                uptime = _format_uptime(datetime.fromisoformat(started), now)
                status = "active"
            else:
                if project in uptime_map and port_key in uptime_map[project]:
                    del uptime_map[project][port_key]
                    if not uptime_map[project]:
                        del uptime_map[project]
                uptime = "—"
                status = "inactive"

            project_entry["ports"].append(
                {
                    "port": port,
                    "status": status,
                    "externalIp": external_ip,
                    "country": country,
                    "uptime": uptime,
                }
            )
        if project_entry["ports"]:
            result["projects"].append(project_entry)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f)
    os.makedirs(os.path.dirname(UPTIME_FILE), exist_ok=True)
    with open(UPTIME_FILE, "w") as f:
        json.dump(uptime_map, f)

    return result


def _format_uptime(start: datetime, now: datetime) -> str:
    delta = now - start
    total = int(delta.total_seconds())
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{days}d {hours:02}:{minutes:02}:{seconds:02}"

if __name__ == "__main__":
    main()
