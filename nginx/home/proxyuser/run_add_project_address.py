import json
import sys
import logging
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

PORTS_FILE = os.getenv("PORTS_FILE", "/usr/share/nginx/html/port_mapping.json")
if "PORTS_FILE" not in os.environ:
    logging.error(
        f"Переменная PORTS_FILE не установлена. Используется значение по умолчанию: {PORTS_FILE}"
    )

IP_MAPPING_FILE = os.getenv("IP_MAPPING_FILE", "/usr/share/nginx/html/ip_mapping.json")
if "IP_MAPPING_FILE" not in os.environ:
    logging.error(
        f"Переменная IP_MAPPING_FILE не установлена. Используется значение по умолчанию: {IP_MAPPING_FILE}"
    )

def load_json(file_path):
    """ Загружает JSON-файл """
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        logging.error(f"Файл не найден: {file_path}")
        return {}
    except json.JSONDecodeError:
        logging.error(f"Ошибка декодирования JSON в файле: {file_path}")
        return {}

def save_json(file_path, data):
    """ Сохраняет JSON-файл с обновленными данными """
    try:
        with open(file_path, "w") as file:
            json.dump(data, file, separators=(",", ":"))
        logging.info(f"Файл {file_path} успешно обновлен.")
        return True
    except PermissionError:
        logging.error(f"Ошибка прав доступа к файлу: {file_path}. Проверьте права доступа.")
        return False
    except Exception as e:
        logging.error(f"Ошибка при сохранении файла {file_path}: {e}")
        return False

def validate_project_and_port(project_name, port):
    """ Проверяет, существует ли проект и порт """
    ports_data = load_json(PORTS_FILE)
    if project_name in ports_data and port in ports_data[project_name]:
        return True
    logging.error(f"Порт {port} не связан с проектом {project_name}.")
    return False

def add_ip_to_project(container_ip, project_name, port):
    """Добавляет IP контейнера в проект, если это разрешено."""

    # 1) Если проект — "other", ничего не делаем
    if project_name.lower() == "other":
        logging.info(
            f"Проект определен как 'other', "
            f"IP {container_ip} не был добавлен."
        )
        return (
            f"Проект определен как 'other', "
            f"IP {container_ip} не был добавлен."
        )

    # 2) Проверяем, что порт действительно принадлежит проекту
    if not validate_project_and_port(project_name, port):
        logging.error(
            f"Порт {port} не связан с проектом {project_name}. "
            f"Добавление IP {container_ip} прервано."
        )
        return "Ошибка: порт не соответствует проекту."

    # 3) Загружаем текущее распределение IP
    ip_data = load_json(IP_MAPPING_FILE)

    # 4) Глобальная проверка: IP не должен быть в другом проекте
    for existing_proj, ips in ip_data.items():
        if existing_proj != project_name and container_ip in ips:
            logging.error(
                f"IP {container_ip} уже принадлежит проекту {existing_proj}, "
                f"нельзя добавить в {project_name}."
            )
            return (
                f"Ошибка: IP {container_ip} уже назначен проекту "
                f"{existing_proj}."
            )

    # 5) Если проекта нет в маппинге — создаём подраздел
    if project_name not in ip_data:
        ip_data[project_name] = []

    # 6) Если IP ещё не в своём проекте — добавляем и сохраняем
    if container_ip not in ip_data[project_name]:
        ip_data[project_name].append(container_ip)
        save_json(IP_MAPPING_FILE, ip_data)
        logging.info(
            f"Успешно добавлен IP {container_ip} в проект {project_name}."
        )
        return "success"

    # 7) Если IP уже в списке этого же проекта — просто возвращаем успех
    logging.info(
        f"IP {container_ip} уже присутствует "
        f"в проекте {project_name}."
    )
    return "success"


def main():
    if len(sys.argv) != 4:
        logging.error("Использование: python3 run_add_project_address.py <container_ip> <project_name> <port>")
        sys.exit(1)
    
    container_ip = sys.argv[1]
    project_name = sys.argv[2]
    try:
        port = int(sys.argv[3])
    except ValueError:
        logging.error("Ошибка: указан неверный номер порта.")
        sys.exit(1)

    result = add_ip_to_project(container_ip, project_name, port)
    print(result)
    
if __name__ == "__main__":
    main()
