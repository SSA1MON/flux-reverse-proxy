#!/bin/bash

while true; do
    if [ -f /app/.env ]; then
        set -o allexport
        source /app/.env
        set +o allexport
        echo "✅ Variables from .env are loaded."
        break
    else
        echo "❌ .env was not found. Retrying in 5 minutes..."
        sleep 300
    fi
done


# === Входные параметры ===
PROJECT_NAME="${1:-unknown_project}"
CONTAINER_IP="${2:-unknown_ip}"
PORTS_URL="http://$NGINX_HOST:$NGINX_PORT_API/available_ports"
LOG_FILE="/app/logs/port_project_watcher.log"
REMOTE_SCRIPT="/home/proxyuser/run_restart_app.py"

mkdir -p /app/logs
exec >> "$LOG_FILE" 2>&1

echo "$(date '+%F %T') ▶ Наблюдение за проектом: $PROJECT_NAME (IP: $CONTAINER_IP)"

while true; do
    echo "$(date '+%F %T') 🔍 Проверка портов в $PROJECT_NAME..."

    PORT_LIST=$(curl -s "$PORTS_URL" | jq -r --arg PROJECT "$PROJECT_NAME" '.[$PROJECT].available_ports | .[]')
    PORT_COUNT=$(echo "$PORT_LIST" | grep -cve '^\s*$')

    if [[ "$PORT_COUNT" -gt 0 ]]; then
        echo "PORT_LIST=$PORT_LIST"
        echo "$(date '+%F %T') ⏳ Найден свободный порт. Ждём 2 минуты..."
        sleep 120

        PORT_LIST=$(curl -s "$PORTS_URL" | jq -r --arg PROJECT "$PROJECT_NAME" '.[$PROJECT].available_ports | .[]')
        PORT_COUNT=$(echo "$PORT_LIST" | grep -cve '^\s*$')

        if [[ "$PORT_COUNT" -gt 0 ]]; then
            echo "PORT_LIST=$PORT_LIST"
            echo "$(date '+%F %T') ✅ Порт по-прежнему свободен. Перезапуск..."
            sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p "$NGINX_SSH_PORT" "$SSH_USER@$NGINX_HOST" \
                "python3 $REMOTE_SCRIPT '$CONTAINER_IP'"

            SSH_EXIT_CODE=$?

            if [[ "$SSH_EXIT_CODE" -eq 0 ]]; then
                echo "$(date '+%F %T') ✅ Перезапуск успешно выполнен."
                break
            else
                echo "$(date '+%F %T') ❌ Ошибка SSH-подключения (код $SSH_EXIT_CODE). Повтор через 1 минуту."
                sleep 60
            fi
        else
            echo "$(date '+%F %T') 🔁 Порт уже занят. Продолжаем наблюдение."
        fi
    else
        echo "$(date '+%F %T') ❌ Нет свободных портов. Ждём 5 минут..."
        sleep 300
    fi
done
