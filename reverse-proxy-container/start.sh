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

# Попытка получить внешний IP с периодическим ожиданием
while true; do
    CONTAINER_IP=$(get_external_ip)
    if [[ -n "$CONTAINER_IP" ]]; then
        log "🌐 External IP detected: $CONTAINER_IP"
        break
    fi

    log "❌ Failed to determine external IP. Retrying in 15 minutes..."
    sleep 900
done

# Проверка на наличие IP контейнера в черном списке
check_blacklist() {
    log "🔍 Checking if IP $CONTAINER_IP is valid via remote script..."

    SSH_CMD="python3 $REMOTE_BLACKLIST_SCRIPT '$CONTAINER_IP'"
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
        "python3 $REMOTE_ADD_PROJECT_SCRIPT '$CONTAINER_IP' '$PROJECT_NAME' '$AVAILABLE_PORT'" 2>&1)
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

    PROJECT=$(echo "$IP_MAPPING_RESPONSE" | jq -r --arg CONTAINER_IP "$CONTAINER_IP" '
        to_entries | map(select(.value[]? == $CONTAINER_IP)) | if length == 0 then null else .[0].key end
    ')

    if [ -n "$PROJECT" ] && [ "$PROJECT" != "null" ]; then
        log "📡 Project found: $PROJECT"
    else
        log "🔎 IP $CONTAINER_IP not found in any project. Searching for any project with available ports (excluding 'other')..."
        for PROJ in $(echo "$RESPONSE" | jq -r 'keys_unsorted[]' | grep -v '^other$'); do
            PORTS=$(echo "$RESPONSE" | jq -r --arg PROJECT "$PROJ" '.[$PROJECT].available_ports | .[]')
            if [ -n "$PORTS" ]; then
                PROJECT="$PROJ"
                log "✅ Found available ports in project: $PROJECT"
                break
            fi
        done

        if [ -z "$PROJECT" ] || [ "$PROJECT" == "null" ]; then
            log "❗ No available ports in any projects. Using fallback project: 'other'."
            PROJECT="other"
        fi
    fi


    # Повторная проверка порта каждую минуту 5 раз
    for i in {1..5}; do
        PROJECT_PORTS=$(echo "$RESPONSE" | jq -r --arg PROJECT "$PROJECT" '.[$PROJECT].available_ports | .[]')

        if [ -n "$PROJECT_PORTS" ]; then
            break
        fi

        log "❌ No available ports in $PROJECT. Waiting 1 minutes... ($i/5)"
        sleep 60
    done

    if [ -z "$PROJECT_PORTS" ]; then
        log "⏳ 5 minutes elapsed. No ports available in current projects. Restarting project search..."

        while true; do
            RESPONSE=$(curl -s http://$NGINX_HOST:$NGINX_PORT_API/available_ports)

            # Повторяем проверку по всем проектам, кроме other
            for PROJ in $(echo "$RESPONSE" | jq -r 'keys_unsorted[]' | grep -v '^other$'); do
                PORTS=$(echo "$RESPONSE" | jq -r --arg PROJECT "$PROJ" '.[$PROJECT].available_ports | .[]')
                if [ -n "$PORTS" ]; then
                    PROJECT="$PROJ"
                    PROJECT_PORTS="$PORTS"
                    log "✅ Found available ports in project: $PROJECT"
                    break 2
                fi
            done

            if [ -z "$PROJECT_PORTS" ]; then
                echo "$(date '+%F %T') ❌ No available ports in $PROJECT. Starting background port watcher for $PROJECT..."
                bash /app/port_project_watcher.sh "$PROJECT" "$CONTAINER_IP" &

                echo "$(date '+%F %T') 🔍 Re-checking ports in 'other'..."
                PROJECT_PORTS=$(echo "$RESPONSE" | jq -r --arg PROJECT "$PROJECT" '."other".available_ports | .[]')
                if [ -n "$PROJECT_PORTS" ]; then
                    PROJECT="other"
                    echo "$(date '+%F %T') ⚠️ Temporarily switching to 'other'"
                    break
                else
                    echo "$(date '+%F %T') ❌ No ports in 'other'. Retrying in 5 minutes..."
                    sleep 300
                    exit 1
                fi
            fi
        done
    fi


    while true; do
        log "🔍 Fetching available ports..."
        RESPONSE=$(curl -s http://$NGINX_HOST:$NGINX_PORT_API/available_ports)

        log "🔍 Checking available ports in project: $PROJECT..."
        PROJECT_PORTS=$(echo "$RESPONSE" | jq -r --arg PROJECT "$PROJECT" '.[$PROJECT].available_ports | .[]')

        if [ -z "$PROJECT_PORTS" ]; then
            log "❌ No available ports in $PROJECT. Switching to 'other'."
            PROJECT="other"
            PROJECT_PORTS=$(echo "$RESPONSE" | jq -r --arg PROJECT "$PROJECT" '.[$PROJECT].available_ports | .[]')
        fi

        for PORT in $PROJECT_PORTS; do
            log "🔍 Checking port $PORT for project $PROJECT..."
            if ! nc -z $NGINX_HOST $PORT 2>/dev/null; then
                log "🚀 Port $PORT is free, using it!"
                AVAILABLE_PORT=$PORT
                PROJECT_NAME=$PROJECT
                add_project_address
                break 2
            fi
        done

        if [ -n "$AVAILABLE_PORT" ]; then
            break
        fi

        log "❌ All ports are occupied! Waiting 5 minutes before retrying..."
        sleep 300
    done

    log "🔗 Establishing SSH tunnel on port $AVAILABLE_PORT..."
    RESPONSE_SSH=$(sshpass -p "$SSH_PASS" ssh \
        -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=30 \
        -o ExitOnForwardFailure=yes \
        -o ConnectTimeout=5 \
        -N -R "$AVAILABLE_PORT":localhost:1080 \
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
