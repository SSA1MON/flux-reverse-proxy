FROM debian:latest

# Устанавливаем только необходимые зависимости
RUN apt update && apt install -y \
    wget \
    curl \
    sshpass \
    jq \
    netcat-openbsd \
    git \
    libssl-dev \
    make \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Клонируем репозиторий 3proxy и собираем его
RUN git clone https://github.com/3proxy/3proxy.git && \
    cd 3proxy && \
    make -f Makefile.Linux && \
    cp bin/3proxy /usr/local/bin/3proxy && \
    cd .. && rm -rf 3proxy

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы в контейнер
COPY start.sh /app/start.sh
COPY 3proxy.cfg /app/3proxy.cfg
COPY .env /app/.env
COPY port_project_watcher.sh /app/port_project_watcher.sh

# Даем права на выполнение скрипта
RUN chmod +x /app/start.sh
RUN chmod +x /app/port_project_watcher.sh

# Запуск 3proxy и start.sh
CMD ["/bin/bash", "/app/start.sh"]
