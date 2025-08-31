import json
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

PORTS_FILE = "/usr/share/nginx/html/port_mapping.json"
IP_MAPPING_FILE = "/usr/share/nginx/html/ip_mapping.json"
IP_COUNTRY_FILE = "/usr/share/nginx/html/ip_country.json"
PORTS_JSON_FILE = "/usr/share/nginx/html/ports.json"


def load_json(file_path):
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
    ports_data = load_json(PORTS_FILE)
    if project_name in ports_data and port in ports_data[project_name]:
        return True
    logging.error(f"Порт {port} не связан с проектом {project_name}.")
    return False


def generate_ports_json():
    ip_data = load_json(IP_MAPPING_FILE)
    country_map = load_json(IP_COUNTRY_FILE)
    result = {}
    for project, ips in ip_data.items():
        result[project] = []
        for ip in ips:
            result[project].append({
                "ip": ip,
                "country": country_map.get(ip, "")
            })
    save_json(PORTS_JSON_FILE, result)


def add_ip_to_project(container_ip, project_name, port, country_code):
    """Добавляет IP контейнера в проект, если это разрешено."""

    if project_name.lower() == "other":
        logging.info(
            f"Проект определен как 'other', IP {container_ip} не был добавлен."
        )
        return (
            f"Проект определен как 'other', "
            f"IP {container_ip} не был добавлен."
        )

    if not validate_project_and_port(project_name, port):
        logging.error(
            f"Порт {port} не связан с проектом {project_name}. "
            f"Добавление IP {container_ip} прервано."
        )
        return "Ошибка: порт не соответствует проекту."

    ip_data = load_json(IP_MAPPING_FILE)

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

    if project_name not in ip_data:
        ip_data[project_name] = []

    if container_ip not in ip_data[project_name]:
        ip_data[project_name].append(container_ip)
        save_json(IP_MAPPING_FILE, ip_data)
        country_map = load_json(IP_COUNTRY_FILE)
        country_map[container_ip] = country_code
        save_json(IP_COUNTRY_FILE, country_map)
        generate_ports_json()
        logging.info(
            f"Успешно добавлен IP {container_ip} в проект {project_name}."
        )
        return "success"

    logging.info(
        f"IP {container_ip} уже присутствует в проекте {project_name}."
    )
    return "success"


def main():
    if len(sys.argv) != 5:
        logging.error(
            "Использование: python3 run_add_project_address.py <container_ip> <project_name> <port> <countryCode>"
        )
        sys.exit(1)

    container_ip = sys.argv[1]
    project_name = sys.argv[2]
    try:
        port = int(sys.argv[3])
    except ValueError:
        logging.error("Ошибка: указан неверный номер порта.")
        sys.exit(1)

    country_code = sys.argv[4]
    result = add_ip_to_project(container_ip, project_name, port, country_code)
    print(result)


if __name__ == "__main__":
    main()

