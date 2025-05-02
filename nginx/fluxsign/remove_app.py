import datetime
import ipaddress
import json
import os
import re
import smtplib
import ssl
import subprocess
import sys
import urllib.parse
from email.message import EmailMessage
from typing import List, Tuple, Optional

import requests
from dotenv import load_dotenv
from loguru import logger

ENABLE_EMAIL_NOTIFICATIONS = False

# Load environment variables from .env file
load_dotenv()

# Configuration from environment
FLUX_API_URL = "https://api.runonflux.io"
FLUX_ID = os.getenv("FLUX_ID")
APP_NAME = os.getenv("APP_NAME")
EXTERNAL_API_URL = os.getenv("EXTERNAL_API_URL")

# Email settings
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT")


def send_email_after_removal(ip_address: str, removal_time: str):
    """
    Sends an email notification after an application is removed using SMTP without SSL.

    :param ip_address: The IP address of the removed application.
    :param removal_time: The timestamp when the removal happened.
    """
    if not ENABLE_EMAIL_NOTIFICATIONS:
        logger.info("🔕 Email notifications are disabled.")
        return

    # Email content
    EMAIL_SUBJECT = "Application Removal Notification"
    EMAIL_BODY_TEMPLATE = """\
    Hello,

    The application associated with IP {ip_address} has been successfully removed.

    Details:
    - IP Address: {ip_address}
    - Removal Time: {removal_time}

    Best regards,
    Your System
    """
    try:
        logger.info(f"📧 Preparing to send email about IP {ip_address} removal at {removal_time}")

        # Create email message
        msg = EmailMessage()
        msg.set_content(EMAIL_BODY_TEMPLATE.format(ip_address=ip_address, removal_time=removal_time))
        msg["Subject"] = EMAIL_SUBJECT
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECIPIENT

        # Secure connection and send email
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)

        logger.info(f"✅ Email successfully sent to {EMAIL_RECIPIENT} about IP {ip_address}")
    except Exception as e:
        logger.error(f"❌ Error sending email: {e}")



def extract_ip_and_port(ip_entry: dict) -> Tuple[str, int]:
    """Определяет IP и порт, если порт не указан, возвращает 16127."""
    ip_str = ip_entry.get("ip", "")
    match = re.match(r"([\d.]+)(?::(\d+))?", ip_str)
    if match:
        ip_address = match.group(1)
        port = int(match.group(2)) if match.group(2) else 16127
        return ip_address, port
    return ip_str, 16127


def log_response(response: requests.Response, server_name: str) -> None:
    """
    Логирует ответ от сервера.

    :param response: Ответ от сервера
    :param server_name: Название сервера для контекста
    """
    logger.debug(f"Ответ от сервера {server_name} - Статус: {response.status_code}")
    logger.debug(f"Ответ от сервера {server_name} - Тело ответа: {response.text}")


def get_app_location() -> List[Tuple[str, int]]:
    """Запрашивает данные о местоположении приложения и возвращает список IP-адресов с портами."""
    params = {"appname": APP_NAME}
    try:
        response = requests.get(f"{FLUX_API_URL}/apps/location", params=params)
        response.raise_for_status()
        response_data = response.json()
        ip_list = [extract_ip_and_port(entry) for entry in response_data.get("data", [])]
        return ip_list  # Возвращаем список кортежей (IP, порт)
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к API Flux: {e}")
    except requests.exceptions.JSONDecodeError:
        logger.error("Ошибка: не удалось распарсить JSON из ответа API Flux")
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")
    return []


def get_external_data() -> List[str]:
    """
    Получает данные из внешнего источника и возвращает список IP-адресов черного списка.
    """
    try:
        response = requests.get(EXTERNAL_API_URL)
        log_response(response, "Внешний API (Черный список)")
        response.raise_for_status()
        response_data = response.json()

        if 'blacklist' in response_data:
            return response_data['blacklist']
        else:
            logger.error("Ошибка: ключ 'blacklist' не найден в данных.")
            return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к внешнему API: {e}")
    except requests.exceptions.JSONDecodeError:
        logger.error("Ошибка: не удалось распарсить JSON из ответа внешнего API")
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")
    return []


def is_ip_in_blacklist(ip_address: str) -> bool:
    """
    Check if the given IP address is blacklisted by invoking check_blacklist.py
    Return True if IP is blacklisted, otherwise False
    """
    try:
        result = subprocess.run(
            ["python3", "/fluxsign/check_blacklist.py", ip_address],
            capture_output=True,
            text=True
        )

        if result.returncode in [1, 3]:
            logger.warning(f"🚫 IP {ip_address} is blacklisted (code {result.returncode}).")
            return True
        elif result.returncode == 0:
            logger.info(f"✅ IP {ip_address} is not blacklisted.")
            return False
        else:
            logger.error(f"⚠️ Unknown return code from check_blacklist.py: {result.returncode}")
            return False  # или True — по ситуации
    except Exception as e:
        logger.error(f"❌ Failed to run check_blacklist.py for {ip_address}: {e}")
        return False

def remove_app(loginphrase: str, signature: str, app_ip: str, port: int) -> bool:
    """Удаляет приложение через GET запрос."""

    # Преобразуем значения в LF (URL-encoded)
    def utf8_to_LF(value: str) -> str:
        return urllib.parse.quote(value)

    # Перекодируем данные
    encoded_flux_id = utf8_to_LF(FLUX_ID)
    encoded_signature = utf8_to_LF(signature)
    encoded_loginphrase = utf8_to_LF(loginphrase)

    # Формируем URL для удаления приложения, используя IP адрес из аргумента
    url = f"http://{app_ip}:{port}/apps/appremove/{APP_NAME}/true/false"
    headers = {
        "zelidauth": f"zelid={encoded_flux_id}&signature={encoded_signature}&loginPhrase={encoded_loginphrase}"
    }

    try:
        response = requests.get(url, headers=headers)
        log_response(response, f"Удаление приложения с IP: {app_ip}, порт: {port}")
        if response.status_code == 200:
            logger.info(f"Приложение {APP_NAME} успешно удалено с {app_ip}:{port}")
            removal_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            send_email_after_removal(f"{app_ip}:{port}", removal_time)
            return True
        else:
            logger.error(
                f"Ошибка удаления приложения с {app_ip}:{port}. Код ответа: {response.status_code}, {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к API удаления приложения: {e}")
        return False


def get_loginphrase() -> Optional[str]:
    """Получает loginphrase для авторизации."""
    url = f"{FLUX_API_URL}/id/loginphrase"
    try:
        response = requests.get(url)
        log_response(response, "API Flux (loginphrase)")
        return response.json().get("data") if response.status_code == 200 else None
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к API для получения loginphrase: {e}")
    return None


def sign_message_in_js(message: str) -> str:
    """
    Запускает `sign_message.js` и получает подписанное сообщение.

    :param message: Сообщение для подписи
    :return: Подписанное сообщение или сообщение об ошибке
    """
    try:
        # Запускаем sign_message.js из той же директории, что и этот скрипт
        result = subprocess.run(
            ["sudo", "/usr/bin/node", "/fluxsign/sign_message.js", message],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Ошибка при выполнении sign_message.js: {e.stderr}")
        return f"Error in JS script: {e.stderr}"



def provide_signature(loginphrase: str, signature: str) -> bool:
    """Подтверждает подпись через API providesign."""
    url = f"{FLUX_API_URL}/id/providesign"
    payload = json.dumps({"address": FLUX_ID, "message": loginphrase, "signature": signature})
    headers = {"Content-Type": "text/plain"}
    try:
        response = requests.post(url, data=payload, headers=headers)
        log_response(response, "API Flux (providesign)")
        return response.status_code == 200 and response.json().get("status") == "success"
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса для подтверждения подписи: {e}")
    return False

def verify_login(loginphrase: str, signature: str) -> Optional[dict]:
    """Подтверждает логин через API verifylogin."""
    url = f"{FLUX_API_URL}/id/verifylogin"
    payload = json.dumps({"loginPhrase": loginphrase, "zelid": FLUX_ID, "signature": signature})
    headers = {"Content-Type": "text/plain"}
    try:
        response = requests.post(url, data=payload, headers=headers)
        log_response(response, "API Flux (verifylogin)")
        if response.status_code == 200:
            response_data = response.json()
            return response_data["data"] if response_data.get("status") == "success" else None
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса для подтверждения логина: {e}")
    return None

def authenticate() -> Tuple[Optional[str], Optional[str]]:
    """
    Процесс аутентификации пользователя с автоматической подписью.
    """
    loginphrase = get_loginphrase()
    if not loginphrase:
        logger.error("Ошибка получения loginphrase")
        return None, None

    try:
        signature = sign_message_in_js(loginphrase)
    except Exception as e:
        logger.error(f"Ошибка подписи сообщения: {e}")
        return None, None

    if not provide_signature(loginphrase, signature):
        logger.error("Ошибка подтверждения подписи")
        return None, None

    login_data = verify_login(loginphrase, signature)
    if not login_data:
        logger.error("Ошибка авторизации")
        return None, None

    return loginphrase, signature


def compare_and_remove() -> None:
    """Удаляет приложение, если IP контейнера передан в аргументе."""
    if len(sys.argv) != 2:
        logger.error("❌ Не указан IP контейнера!")
        sys.exit(1)

    container_ip = sys.argv[1]
    app_locations = get_app_location()

    matched_entries = [entry for entry in app_locations if entry[0] == container_ip]

    if not matched_entries:
        logger.error(f"❌ IP {container_ip} не найден среди активных приложений.")
        sys.exit(1)

    for ip, port in matched_entries:
        logger.info(f"🔍 Удаление приложения для IP {ip}:{port}...")
        loginphrase, signature = authenticate()

        if loginphrase and signature:
            success = remove_app(loginphrase, signature, ip, port)
            if not success:
                logger.error("❌ Удаление не удалось, повторная попытка через 30 минут в start.sh.")
                sys.exit(1)
        else:
            logger.error("❌ Ошибка аутентификации, удаление невозможно.")
            sys.exit(1)

    logger.info("✅ Удаление приложения выполнено. Продолжаем выполнение start.sh.")
    return


if __name__ == "__main__":
    LOG_FILE = "email_notifications.log"
    logger.add(LOG_FILE, format="{time} {level} {message}", level="INFO", rotation="10 MB", compression="zip")
    compare_and_remove()
