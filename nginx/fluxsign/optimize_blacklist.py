#!/usr/bin/env python3
import json
from ipaddress import ip_address, ip_network, summarize_address_range, collapse_addresses
from collections import defaultdict
from pathlib import Path
from dotenv import load_dotenv
import os
from loguru import logger

# === Load environment config ===
ENV_PATH = Path("/fluxsign/.env")
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

BLACKLIST_PATH = Path("/usr/share/nginx/html/blacklist.json")
TMP_PATH = Path("/usr/share/nginx/html/blacklist.json.tmp")
LOG_DIR = Path("/fluxsign/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "optimize_blacklist.log"

logger.add(
    str(LOG_FILE),
    rotation="5 MB",
    retention=0,
    format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
    level="INFO",
    enqueue=True,
    backtrace=False,
    diagnose=False
)

MIN_IPS_PER_24 = int(os.getenv("MIN_IPS_PER_24", 10))
RATIO_24_PER_16 = float(os.getenv("RATIO_24_PER_16", 0.5))
RATIO_16_PER_8 = float(os.getenv("RATIO_16_PER_8", 0.5))
MAX_AGGREGATE_PREFIX = 8

def load_blacklist(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("blacklist", [])
    except Exception as e:
        logger.error(f"Failed to load blacklist: {e}")
        return []

def save_blacklist_atomic(data, tmp_path, final_path):
    try:
        tmp_path.write_text(json.dumps({"blacklist": [str(n) for n in data]}, indent=2), encoding="utf-8")
        tmp_path.rename(final_path)
        logger.info(f"✔ Optimization complete. Total entries: {len(data)}")
        logger.info(f"✔ Saved to: {final_path}")
    except Exception as e:
        logger.error(f"Failed to write blacklist: {e}")

def group_ips(ips, min_ip_per_24, min_24_ratio_per_16, min_16_ratio_per_8):
    ip_objs = []
    subnet_entries = []

    for entry in ips:
        try:
            if '/' in entry:
                subnet_entries.append(ip_network(entry.strip(), strict=False))
            else:
                ip_objs.append(ip_address(entry.strip()))
        except Exception:
            continue

    logger.info(f"📦 Loaded: {len(ip_objs)} individual IPs, {len(subnet_entries)} subnets")

    subnet_24_map = defaultdict(list)
    for ip in ip_objs:
        subnet_24 = ip_network(f"{ip}/24", strict=False)
        subnet_24_map[subnet_24].append(ip)

    promoted_24 = set()
    retained_ips = []
    for subnet, iplist in subnet_24_map.items():
        if len(iplist) >= min_ip_per_24:
            logger.info(f"🔄 Promoted {len(iplist)} IPs to {subnet}:")
            for ip in sorted(iplist):
                logger.info(f"   - {ip}")
            promoted_24.add(subnet)
        else:
            retained_ips.extend(iplist)

    if retained_ips:
        logger.info(f"📌 Retained {len(retained_ips)} individual IPs (less than MIN_IPS_PER_24):")
        for ip in sorted(retained_ips):
            logger.info(f"   - {ip}")

    subnet_16_map = defaultdict(set)
    for subnet24 in promoted_24:
        subnet16 = ip_network(f"{subnet24.network_address}/16", strict=False)
        subnet_16_map[subnet16].add(subnet24)

    promoted_16 = set()
    remaining_24 = set()
    for subnet16, subs24 in subnet_16_map.items():
        if len(subs24) >= (256 * min_24_ratio_per_16):
            logger.info(f"🔁 Promoted {len(subs24)} /24 subnets to {subnet16}:")
            for s in sorted(subs24):
                logger.info(f"   - {s}")
            promoted_16.add(subnet16)
        else:
            remaining_24.update(subs24)

    subnet_8_map = defaultdict(set)
    for subnet16 in promoted_16:
        subnet8 = ip_network(f"{subnet16.network_address}/8", strict=False)
        subnet_8_map[subnet8].add(subnet16)

    promoted_8 = set()
    remaining_16 = set()
    for subnet8, subs16 in subnet_8_map.items():
        if len(subs16) >= (256 * min_16_ratio_per_8):
            logger.info(f"🔁 Promoted {len(subs16)} /16 subnets to {subnet8}:")
            for s in sorted(subs16):
                logger.info(f"   - {s}")
            promoted_8.add(subnet8)
        else:
            remaining_16.update(subs16)

    final_networks = set()
    final_networks.update(promoted_8)
    final_networks.update(remaining_16)
    final_networks.update(remaining_24)
    final_networks.update(subnet_entries)
    final_networks.update(ip_objs)

    collapsed = collapse_addresses(final_networks)
    final_filtered = [
        net for net in collapsed
        if net.prefixlen >= MAX_AGGREGATE_PREFIX or isinstance(net, ip_address)
    ]
    return sorted(final_filtered, key=lambda net: (net.prefixlen if hasattr(net, "prefixlen") else 32, str(net)))

def main():
    logger.info("🔍 Starting blacklist optimization...")
    raw = load_blacklist(BLACKLIST_PATH)
    optimized = group_ips(raw, MIN_IPS_PER_24, RATIO_24_PER_16, RATIO_16_PER_8)
    save_blacklist_atomic(optimized, TMP_PATH, BLACKLIST_PATH)

if __name__ == "__main__":
    main()
