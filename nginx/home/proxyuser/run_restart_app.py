import subprocess
import sys
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def run_restart_app(container_ip: str) -> int:
    logging.info(f"Starting restart process for container: {container_ip}")

    try:
        command = ["sudo", "python3", "/fluxsign/restart_app.py", container_ip]
        logging.debug(f"Executing command: {' '.join(command)}")

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False
        )

        logging.debug(f"Command output: {result.stdout.strip()}")
        if result.stderr:
            logging.warning(f"Command error: {result.stderr.strip()}")

        return result.returncode
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running restart_app.py: {e.stderr}")
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logging.error("No container IP provided. Usage: run_restart_app.py <container_ip>")
        print("Usage: run_restart_app.py <container_ip>")
        sys.exit(1)

    container_ip = sys.argv[1]
    logging.info(f"Script started with IP: {container_ip}")
    exit_code = run_restart_app(container_ip)
    logging.info(f"Script finished with exit code: {exit_code}")
    sys.exit(exit_code)
