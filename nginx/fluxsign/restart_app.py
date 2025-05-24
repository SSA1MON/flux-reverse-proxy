import requests
import re
import json
import urllib.parse
import subprocess
import sys
import os
from loguru import logger
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

# === Конфигурация ===
load_dotenv()
FLUX_API_URL = "https://api.runonflux.io"
FLUX_ID = os.getenv("FLUX_ID")
APP_NAME = os.getenv("APP_NAME")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
LOG_PATH = "logs/app_restart.log"

# === Очистка лога от строк старше 3 дней ===
def truncate_old_logs():
    if not os.path.exists(LOG_PATH):
        return
    try:
        cutoff = datetime.now() - timedelta(days=3)
        lines_to_keep = []
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    timestamp_str = line.split(" ")[0] + " " + line.split(" ")[1]
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
                    if timestamp >= cutoff:
                        lines_to_keep.append(line)
                except Exception:
                    lines_to_keep.append(line)
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            f.writelines(lines_to_keep)
    except Exception as e:
        print(f"⚠️ Ошибка при очистке логов: {e}")

truncate_old_logs()
logger.add(LOG_PATH, level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}")

# === Получение порта по IP ===
def get_port_for_ip(target_ip: str) -> Optional[str]:
    try:
        response = requests.get(f"{FLUX_API_URL}/apps/location", params={"appname": APP_NAME})
        response.raise_for_status()
        for entry in response.json().get("data", []):
            ip = entry.get("ip")
            if ip and ip.startswith(target_ip):
                match = re.match(r"([\d.]+)(?::(\d+))?", ip)
                if match:
                    return match.group(2) or "16127"
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении порта по IP {target_ip}: {e}")
        return None

# === Аутентификация ===
def get_loginphrase() -> Optional[str]:
    try:
        response = requests.get(f"{FLUX_API_URL}/id/loginphrase")
        return response.json().get("data") if response.status_code == 200 else None
    except Exception as e:
        logger.error(f"Ошибка получения loginphrase: {e}")
        return None

def sign_message(message: str, private_key: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["node", "/fluxsign/sign_message.js", message, private_key],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            logger.error(f"Node sign_message.js failed: {result.stderr}")
            return None
        return result.stdout.strip()
    except Exception as e:
        logger.error(f"Ошибка подписи: {e}")
        return None


def provide_signature(loginphrase: str, signature: str) -> bool:
    try:
        payload = json.dumps({"address": FLUX_ID, "message": loginphrase, "signature": signature})
        response = requests.post(f"{FLUX_API_URL}/id/providesign", data=payload, headers={"Content-Type": "text/plain"})
        return response.status_code == 200 and response.json().get("status") == "success"
    except Exception as e:
        logger.error(f"Ошибка provide_signature: {e}")
        return False

def verify_login(loginphrase: str, signature: str) -> bool:
    try:
        payload = json.dumps({"loginPhrase": loginphrase, "zelid": FLUX_ID, "signature": signature})
        response = requests.post(f"{FLUX_API_URL}/id/verifylogin", data=payload, headers={"Content-Type": "text/plain"})
        return response.status_code == 200 and response.json().get("status") == "success"
    except Exception as e:
        logger.error(f"Ошибка verify_login: {e}")
        return False

# === Перезапуск ===
def restart_app(ip: str, port: str, loginphrase: str, signature: str) -> bool:
    try:
        url = f"http://{ip}:{port}/apps/apprestart/{APP_NAME}"
        headers = {
            "zelidauth": f"zelid={urllib.parse.quote(FLUX_ID)}&signature={urllib.parse.quote(signature)}&loginPhrase={urllib.parse.quote(loginphrase)}"
        }
        response = requests.get(url, headers=headers)
        logger.debug(f"Ответ от перезапуска: {response.status_code} {response.text}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Ошибка запроса на перезапуск: {e}")
        return False

# === Основной блок ===
def main():
    if len(sys.argv) < 2:
        logger.error("Не указан IP. Использование: python3 app_restart.py <IP>")
        sys.exit(1)

    ip_arg = sys.argv[1]
    logger.info(f"▶ Запрос на перезапуск приложения по IP: {ip_arg}")

    port = get_port_for_ip(ip_arg)
    if not port:
        logger.error(f"Порт не найден для IP: {ip_arg}")
        sys.exit(1)

    loginphrase = get_loginphrase()
    if not loginphrase:
        logger.error("Ошибка получения loginphrase")
        sys.exit(1)

    signature = sign_message(loginphrase, PRIVATE_KEY)
    if not signature:
        logger.error("Ошибка подписи")
        sys.exit(1)

    if not provide_signature(loginphrase, signature):
        logger.error("Ошибка provide_signature")
        sys.exit(1)

    if not verify_login(loginphrase, signature):
        logger.error("Ошибка verify_login")
        sys.exit(1)

    if restart_app(ip_arg, port, loginphrase, signature):
        logger.success("Приложение успешно перезапущено")
        sys.exit(0)
    else:
        logger.error("Не удалось перезапустить приложение")
        sys.exit(1)

if __name__ == "__main__":
    main()
