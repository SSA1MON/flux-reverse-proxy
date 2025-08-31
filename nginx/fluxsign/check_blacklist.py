import sys
import json
import ipaddress
import requests
from loguru import logger
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import os

# === Load .env ===
ENV_PATH = Path("/fluxsign/.env")
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    logger.warning(f".env file not found at {ENV_PATH}, using defaults")

USE_API = True

# === Config from .env or defaults ===
API_KEY = os.getenv("IPHUB_API_KEY", "").strip()
TWOIP_API_TOKEN = os.getenv("TWOIP_API_TOKEN", "").strip()
BLACKLIST_FILE = Path("/usr/share/nginx/html/blacklist.json")
WHITELIST_FILE = Path("/usr/share/nginx/html/whitelist.json")
API_URL = "https://v2.api.iphub.info/ip/"
API_USAGE_LOG = Path("/tmp/iphub_api_usage.log")
API_DAILY_LIMIT = 990
LOG_FILE_PATH = "/tmp/check_blacklist.log"

# === Configure Loguru ===
logger.add(sys.stderr, format="{time} {level} {message}", level="INFO")
logger.add(
    LOG_FILE_PATH,
    rotation="5 MB",
    retention=0,  # Do NOT keep old log files
    format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
    level="INFO",
    enqueue=True,
    backtrace=False,
    diagnose=False
)

# === Utility functions ===

def load_json_list(path: Path, key: str) -> list:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get(key, [])
    except Exception as e:
        logger.error(f"Failed to load {path}: {e}")
        return []

def save_json_list(path: Path, key: str, data: list):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({key: sorted(set(data))}, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save {path}: {e}")

def is_ip_in_list(ip: str, ip_list: list) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip.strip())
    except ValueError:
        logger.error(f"Invalid IP address: {ip}")
        sys.exit(2)
    for entry in ip_list:
        try:
            if '/' in entry:
                if ip_obj in ipaddress.ip_network(entry, strict=False):
                    return True
            elif ip_obj == ipaddress.ip_address(entry):
                return True
        except Exception:
            continue
    return False

def get_api_usage_today() -> int:
    today = datetime.now().date().isoformat()
    if not API_USAGE_LOG.exists():
        return 0
    try:
        with open(API_USAGE_LOG, "r") as f:
            lines = [line.strip() for line in f if line.strip()]
        today_lines = [line for line in lines if line == today]
        with open(API_USAGE_LOG, "w") as f:
            f.write("\n".join(today_lines) + "\n")
        return len(today_lines)
    except Exception as e:
        logger.error(f"Failed to process API usage log: {e}")
        return 0

def increment_api_usage():
    today = datetime.now().date().isoformat()
    with open(API_USAGE_LOG, "a") as f:
        f.write(f"{today}\n")

def fetch_ip_info_fallback(ip: str) -> dict:
    try:
        resp = requests.get(f"https://ipwho.is/{ip}", timeout=5)
        data = resp.json()
        if data.get("ip") and data.get("country_code"):
            return {"ip": data["ip"], "countryCode": data["country_code"]}
    except Exception:
        pass

    try:
        url = f"https://api.2ip.io/geo.json?ip={ip}"
        if TWOIP_API_TOKEN:
            url += f"&key={TWOIP_API_TOKEN}"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get("ip") and data.get("country_code"):
            return {"ip": data["ip"], "countryCode": data["country_code"]}
    except Exception:
        pass

    return {}

def check_with_iphub(ip: str) -> dict:
    try:
        headers = {"X-Key": API_KEY}
        response = requests.get(API_URL + ip, headers=headers, timeout=5)
        if response.status_code != 200:
            logger.error(f"Non-200 response from IPHub: {response.status_code}")
            return {}
        return response.json()
    except Exception as e:
        logger.error(f"Exception during IPHub request: {e}")
        return {}

# === Legacy mode (blacklist only) ===

def run_legacy_check(ip: str):
    blacklist = load_json_list(BLACKLIST_FILE, "blacklist")
    if is_ip_in_list(ip, blacklist):
        logger.warning(f"{ip} found in blacklist")
        logger.info(f"{ip} | BLACKLIST_HIT")
        sys.exit(1)
    logger.info(f"{ip} not found in blacklist")
    logger.info(f"{ip} | GOOD")
    sys.exit(0)

# === Full mode (blacklist → whitelist → IPHub) ===

def run_full_check(ip: str, country_code: str):
    logger.info(f"Checking {ip} ({country_code})")
    blacklist = load_json_list(BLACKLIST_FILE, "blacklist")
    if is_ip_in_list(ip, blacklist):
        logger.warning(f"{ip} found in blacklist")
        logger.info(f"{ip} | BLACKLIST_HIT")
        sys.exit(1)

    whitelist = load_json_list(WHITELIST_FILE, "whitelist")
    if is_ip_in_list(ip, whitelist):
        logger.info(f"{ip} found in whitelist")
        logger.info(f"{ip} | GOOD")
        sys.exit(0)

    if get_api_usage_today() >= API_DAILY_LIMIT:
        logger.warning(f"API usage limit reached: {API_DAILY_LIMIT}")
        info = fetch_ip_info_fallback(ip)
        if info:
            logger.info(f"{ip} | GOOD_FALLBACK")
            sys.exit(0)
        logger.info(f"{ip} | ERROR_API_LIMIT")
        sys.exit(4)

    data = check_with_iphub(ip)
    if not data or "block" not in data:
        info = fetch_ip_info_fallback(ip)
        if info:
            logger.info(f"{ip} | GOOD_FALLBACK")
            sys.exit(0)
        logger.error("IPHub API error or invalid response")
        logger.info(f"{ip} | ERROR_API_RESPONSE")
        sys.exit(5)

    increment_api_usage()

    if data["block"] == 1:
        logger.warning(f"{ip} is classified as bad (data center or proxy)")
        logger.info(f"{ip} | BLOCKED_BY_API")
        blacklist.append(ip)
        save_json_list(BLACKLIST_FILE, "blacklist", blacklist)
        sys.exit(3)
    else:
        logger.info(f"{ip} is classified as good (residential)")
        logger.info(f"{ip} | GOOD")
        whitelist.append(ip)
        save_json_list(WHITELIST_FILE, "whitelist", whitelist)
        sys.exit(0)

# === Entry point ===

if __name__ == "__main__":
    if len(sys.argv) < 3:
        logger.error("Usage: check_ip.py <ip-address> <countryCode>")
        sys.exit(2)

    ip_to_check = sys.argv[1]
    country_code = sys.argv[2]

    if USE_API:
        if not API_KEY:
            logger.error("IPHUB_API_KEY is not set in .env")
            logger.info(f"{ip_to_check} | ERROR_NO_API_KEY")
            sys.exit(6)
        run_full_check(ip_to_check, country_code)
    else:
        run_legacy_check(ip_to_check)
