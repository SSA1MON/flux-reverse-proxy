#!/bin/bash

# Function to load environment variables from .env file
load_env_variables() {
    if [ -f /app/.env ]; then
        # shellcheck disable=SC2046
        export $(grep -v '^#' /app/.env | xargs)
        echo "✅ Variables from .env are loaded."
        return 0
    else
        echo "❌ .env was not found."
        return 1
    fi
}

# Infinite loop to attempt loading environment variables
while true; do
    if load_env_variables; then
        break
    else
        echo "Retrying in 5 minutes..."
        sleep 300
    fi
done


REMOTE_SCRIPT_PATH="/home/proxyuser/run_remove_app.py"
REMOTE_ADD_PROJECT_SCRIPT="/home/proxyuser/run_add_project_address.py"
REMOTE_BLACKLIST_SCRIPT="/fluxsign/check_blacklist.py"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1"
}

# Получаем внешний IP контейнера
get_external_ip() {
    IP_SERVICES=(
        "https://ifconfig.me/ip"
        "https://icanhazip.com"
        "https://ipinfo.io/ip"
        "https://ifconfig.co/ip"
        "https://checkip.amazonaws.com/"
    )

    for SERVICE in "${IP_SERVICES[@]}"; do
        RESPONSE=$(curl -s --max-time 5 "$SERVICE")
        IP=$(echo "$RESPONSE" | grep -Eo '^([0-9]{1,3}\.){3}[0-9]{1,3}$')

        if [[ -n "$IP" ]]; then
            echo "$IP"
            return 0
        fi
    done

    return 1
}

# Получение сведений об IP с определением страны
get_ip_info() {
    local TARGET_IP="$1"

    if [[ -n "$IPHUB_API_KEY" ]]; then
        local RESP
        RESP=$(curl -s -H "X-Key: $IPHUB_API_KEY" "https://v2.api.iphub.info/ip/$TARGET_IP")
        local IP_RES COUNTRY
        IP_RES=$(echo "$RESP" | jq -r '.ip // empty')
        COUNTRY=$(echo "$RESP" | jq -r '.countryCode // empty')
        if [[ -n "$IP_RES" && -n "$COUNTRY" ]]; then
            echo "$IP_RES|$COUNTRY"
            return 0
        fi
    fi

    local RESP2
    RESP2=$(curl -s "https://ipwho.is/$TARGET_IP")
    local IP_RES2 COUNTRY2
    IP_RES2=$(echo "$RESP2" | jq -r '.ip // empty')
    COUNTRY2=$(echo "$RESP2" | jq -r '.country_code // empty')
    if [[ -n "$IP_RES2" && -n "$COUNTRY2" ]]; then
        echo "$IP_RES2|$COUNTRY2"
        return 0
    fi

    local TOKEN_PARAM=""
    if [[ -n "$TWOIP_API_TOKEN" ]]; then
        TOKEN_PARAM="&key=$TWOIP_API_TOKEN"
    fi
    local RESP3
    RESP3=$(curl -s "https://api.2ip.io/geo.json?ip=$TARGET_IP$TOKEN_PARAM")
    local IP_RES3 COUNTRY3
    IP_RES3=$(echo "$RESP3" | jq -r '.ip // empty')
    COUNTRY3=$(echo "$RESP3" | jq -r '.country_code // empty')
    if [[ -n "$IP_RES3" && -n "$COUNTRY3" ]]; then
        echo "$IP_RES3|$COUNTRY3"
        return 0
    fi

    return 1
}

# Попытка получить внешний IP с периодическим ожиданием
while true; do
    CONTAINER_IP=$(get_external_ip)
    if [[ -n "$CONTAINER_IP" ]]; then
        IP_INFO=$(get_ip_info "$CONTAINER_IP")
        if [[ -n "$IP_INFO" ]]; then
            CONTAINER_IP="${IP_INFO%%|*}"
            COUNTRY_CODE="${IP_INFO##*|}"
            log "🌐 External IP detected: $CONTAINER_IP ($COUNTRY_CODE)"
            break
        fi
    fi

    log "❌ Failed to determine external IP. Retrying in 15 minutes..."
    sleep 900
done

# Проверка на наличие IP контейнера в черном списке
check_blacklist() {
    log "🔍 Checking if IP $CONTAINER_IP is valid via remote script..."

    SSH_CMD="python3 $REMOTE_BLACKLIST_SCRIPT '$CONTAINER_IP' '$COUNTRY_CODE'"
    sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$SSH_USER@$NGINX_HOST" "$SSH_CMD"
    EXIT_CODE=$?

    log "📡 Remote check exit code: $EXIT_CODE"

    case $EXIT_CODE in
        0)
            log "✅ IP is valid. Proceeding with normal operation..."
            ;;
        1|3)
            log "❌ IP is blacklisted or blocked. Triggering remote removal..."

            while true; do
                sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$SSH_USER@$NGINX_HOST" \
                    "python3 $REMOTE_SCRIPT_PATH '$CONTAINER_IP'"
                # shellcheck disable=SC2181
                if [[ $? -eq 0 ]]; then
                    log "✅ remove_app.py executed successfully!"
                    exit 0
                else
                    log "❌ Error executing remove_app.py. Retrying in 5 minutes..."
                    sleep 300
                fi
            done
            ;;
        4)
            # Wait until next UTC midnight (simple conservative logic)
            SECONDS_NOW=$(date +%s)
            SECONDS_NEXT_DAY=$(date -d tomorrow +%s)
            WAIT_SECONDS=$((SECONDS_NEXT_DAY - SECONDS_NOW))

            # shellcheck disable=SC2004
            log "⏳ API quota exceeded. Waiting $WAIT_SECONDS seconds (~$(($WAIT_SECONDS / 60)) minutes)..."
            sleep "$WAIT_SECONDS"
            ;;
        2)
            log "⚠️ Invalid IP or local error during IP check. Retrying in 5 minutes..."
            sleep 300
            check_blacklist
            ;;
        5)
            log "❌ IPHub API error or invalid response. Retrying in 5 minutes..."
            sleep 300
            check_blacklist
            ;;
        6)
            log "❌ API key missing. Cannot check IP. Retrying in 10 minutes..."
            sleep 600
            check_blacklist
            ;;

        *)
            log "❌ Unknown error during remote IP check. Retrying in 5 minutes..."
            sleep 300
            check_blacklist
            ;;
    esac
}

add_project_address() {
    log "📡 Adding IP $CONTAINER_IP to project: $PROJECT_NAME with port: $AVAILABLE_PORT"
    ADD_PROJECT_RESPONSE=$(sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "$SSH_USER@$NGINX_HOST" \
        "python3 $REMOTE_ADD_PROJECT_SCRIPT '$CONTAINER_IP' '$PROJECT_NAME' '$AVAILABLE_PORT' '$COUNTRY_CODE'" 2>&1)
    log "📡 Response from run_add_project_address.py: $ADD_PROJECT_RESPONSE"
}

# Изначальная проверка черного списка
check_blacklist

log "🚀 Starting 3proxy..."

#!/bin/bash

# Function to write the 3proxy configuration
write_config() {
    echo "📄 Writing to 3proxy.cfg with user $PROXY_USER..."

    cat <<EOF > /app/3proxy.cfg
auth strong
users $PROXY_USER:CL:$PROXY_PASS
socks -p1080
allow $PROXY_USER
EOF
}

# Infinite loop to attempt writing the configuration
while true; do
    write_config

    if grep -q "^users $PROXY_USER:CL:$PROXY_PASS" /app/3proxy.cfg; then
        echo "✅ 3proxy.cfg successfully written!"
        break
    else
        echo "❌ Failed to write correct 3proxy.cfg. Retrying in 5 minutes..."
        sleep 300
    fi
done

# Start 3proxy in the background
3proxy /app/3proxy.cfg &


while true; do
    log "🔍 Fetching available ports..."
    RESPONSE=$(curl -s http://$NGINX_HOST:$NGINX_PORT_API/available_ports)
    log "📡 API response (available_ports): $RESPONSE"

    log "🔍 Checking if IP $CONTAINER_IP exists in ip_mapping..."
    IP_MAPPING_RESPONSE=$(curl -s http://$NGINX_HOST:$NGINX_PORT_API/ip_mapping.json)
    log "📡 API response (ip_mapping.json): $IP_MAPPING_RESPONSE"

    # Определяем, привязан ли IP к проекту
    PROJECT=$(echo "$IP_MAPPING_RESPONSE" | jq -r --arg CONTAINER_IP "$CONTAINER_IP" 'to_entries | map(select(.value[]? == $CONTAINER_IP)) | if length == 0 then null else .[0].key end')
    if [ -n "$PROJECT" ] && [ "$PROJECT" != "null" ]; then
        IP_FOUND=true  # IP уже есть в ip_mapping
        log "📡 Project found: $PROJECT"
    else
        IP_FOUND=false # IP новый, ищем проект с портами
        log "🔎 IP $CONTAINER_IP not found in any project. Searching for available project..."
        for PROJ in $(echo "$RESPONSE" | jq -r 'keys_unsorted[]' | grep -v '^other$'); do
            PORTS=$(echo "$RESPONSE" | jq -r --arg PROJECT "$PROJ" '.[$PROJECT].available_ports | .[]')
            if [ -n "$PORTS" ]; then
                PROJECT="$PROJ"
                log "✅ Found available ports in project: $PROJECT"
                break
            fi
        done
        if [ -z "$PROJECT" ] || [ "$PROJECT" == "null" ]; then
            log "❗ No available ports in any project. Using fallback project: 'other'."
            PROJECT="other"
        fi
    fi

    # Повторная проверка порта каждую минуту 5 раз (для текущего $PROJECT)
    for i in {1..5}; do
        RESPONSE=$(curl -s http://$NGINX_HOST:$NGINX_PORT_API/available_ports)
        PROJECT_PORTS=$(echo "$RESPONSE" | jq -r --arg PROJECT "$PROJECT" '.[$PROJECT].available_ports | .[]')
        if [ -n "$PROJECT_PORTS" ]; then
            log "✅ Свободные порты появились в проекте $PROJECT"
            break
        fi
        log "❌ Нет портов в $PROJECT. Ждём 1 минуту... ($i/5)"
        sleep 60
    done

    # Если после 5 попыток портов нет, обрабатываем отдельно
    if [ -z "$PROJECT_PORTS" ]; then
        log "⏳ 5 минут истекли. Нет свободных портов в проекте $PROJECT."
        if [ "$IP_FOUND" = true ]; then
            # Уже привязанный IP: не переключаем проект, только временный 'other'
            log "⚠️ IP $CONTAINER_IP уже привязан к $PROJECT — не переключаемся."
            bash /app/port_project_watcher.sh "$PROJECT" "$CONTAINER_IP" &
            RESPONSE=$(curl -s http://$NGINX_HOST:$NGINX_PORT_API/available_ports)
            PROJECT_PORTS=$(echo "$RESPONSE" | jq -r '."other".available_ports | .[]')
            if [ -n "$PROJECT_PORTS" ]; then
                PROJECT="other"
                log "⚠️ Временно используем проект 'other' для IP $CONTAINER_IP"
            else
                log "❌ Нет портов даже в 'other'. Ждём 5 минут и выходим."
                sleep 300
                exit 1
            fi
        else
            # Новый IP: получаем свежие данные по портам
            RESPONSE=$(curl -s http://$NGINX_HOST:$NGINX_PORT_API/available_ports)
            log "🔄 IP новый, получаем свежие данные портов..."

            # Пробуем найти непустой проект (кроме other)
            for PROJ in $(echo "$RESPONSE" | jq -r 'keys_unsorted[]' | grep -v '^other$'); do
                PORTS=$(echo "$RESPONSE" | jq -r --arg PROJECT "$PROJ" '.[$PROJECT].available_ports | .[]')
                if [ -n "$PORTS" ]; then
                    PROJECT="$PROJ"
                    PROJECT_PORTS="$PORTS"
                    log "✅ Найдены порты в проекте $PROJECT"
                    break
                fi
            done

            # Если всё ещё нет портов, делаем фолбек на other
            if [ -z "$PROJECT_PORTS" ]; then
                log "❗ Не найдено портов ни в одном проекте. Фолбек на 'other'."
                PROJECT="other"
                RESPONSE=$(curl -s http://$NGINX_HOST:$NGINX_PORT_API/available_ports)
                PROJECT_PORTS=$(echo "$RESPONSE" | jq -r '."other".available_ports | .[]')
                if [ -z "$PROJECT_PORTS" ]; then
                    log "❌ Нет портов даже в 'other'. Ждём и выходим."
                    sleep 300
                    exit 1
                fi
            fi
        fi
    fi

    # === Выбор конкретного свободного порта ===
    for PORT in $PROJECT_PORTS; do
        log "🔍 Checking port $PORT for project $PROJECT...."
        if ! nc -z $NGINX_HOST $PORT 2>/dev/null; then
            log "🚀 Port $PORT is free, using it!"
            AVAILABLE_PORT="$PORT"
            PROJECT_NAME="$PROJECT"
            add_project_address
            break
        fi
    done

    # Если порт не найден — выходим с ошибкой
    if [ -z "$AVAILABLE_PORT" ]; then
        log "❌ Не удалось найти свободный порт в проекте $PROJECT"
        exit 1
    fi


    log "🔗 Establishing SSH tunnel on port $AVAILABLE_PORT..."
    RESPONSE_SSH=$(sshpass -p "$SSH_PASS" ssh \
        -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=30 \
        -o ExitOnForwardFailure=yes \
        -o ConnectTimeout=5 \
        -N -R 127.0.0.1:"$AVAILABLE_PORT":127.0.0.1:1080 \
        "$SSH_USER"@"$NGINX_HOST" -p "$NGINX_SSH_PORT" 2>&1)

    log "📡 SSH response: $RESPONSE_SSH"

    if echo "$RESPONSE_SSH" | grep -q "successfully"; then
        log "✅ SSH tunnel established on port $AVAILABLE_PORT!"
    else
        log "❌ Error setting up SSH tunnel: $RESPONSE_SSH"
        sleep 10
        continue
    fi

    while true; do
        SSH_STATUS=$(sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no \
            -o ConnectTimeout=5 \
            -o BatchMode=yes \
            -o ConnectionAttempts=1 \
            "$SSH_USER"@"$NGINX_HOST" -p "$NGINX_SSH_PORT" "echo SSH_OK" 2>&1)

        if echo "$SSH_STATUS" | grep -q "SSH_OK"; then
            log "🔄 SSH tunnel is active."
        else
            log "❌ SSH tunnel lost connection."
            break
        fi

        sleep 10
    done
done
