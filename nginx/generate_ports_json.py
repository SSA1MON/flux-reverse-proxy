#!/usr/bin/env python3
"""Generate ports.json for dashboard from mapping files."""
import json
from datetime import datetime
import os
from urllib.request import urlopen
from urllib.error import URLError

IP_MAPPING_FILE = "/usr/share/nginx/html/ip_mapping.json"
PORT_MAPPING_FILE = "/usr/share/nginx/html/port_mapping.json"
OUTPUT_FILE = "/var/lib/flux-dashboard/ports.json"

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


def main():
    ip_mapping = load_json(IP_MAPPING_FILE)
    port_mapping = load_json(PORT_MAPPING_FILE)

    result = {
        "generatedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "projects": []
    }

    for project, ports in port_mapping.items():
        ips = ip_mapping.get(project, [])
        external_ip = ips[0] if ips else None
        country = lookup_country(external_ip) if external_ip else None
        project_entry = {"name": project, "ports": []}
        for port in ports:
            project_entry["ports"].append({
                "port": port,
                "status": "active" if external_ip else "inactive",
                "externalIp": external_ip,
                "country": country,
                "uptime": None
            })
        result["projects"].append(project_entry)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f)

if __name__ == "__main__":
    main()
