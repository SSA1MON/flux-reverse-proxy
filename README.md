# flux-reverse-proxy

**flux-reverse-proxy** – это система динамической маршрутизации IP-адресов с использованием NGINX и SSH-туннелей, управляемая из нескольких контейнеров. Проект предназначен для работы в децентрализованной среде (например, платформа Flux) и позволяет автоматически пробрасывать сетевые подключения от удалённых узлов (контейнеров) через центральный сервер с NGINX. Основная идея – каждый удалённый контейнер сам регистрирует свой внешний IP-адрес и устанавливает SSH-туннель, благодаря чему сервисы, запущенные на распределённых узлах, становятся доступными через единый центральный узел.

## Архитектура системы
* **Reverse Proxy Container (контейнер обратного прокси):** Запускается на удалённом узле (например, Flux-нода) и отвечает за подключение этого узла к центральному серверу. При старте он определяет собственный внешний IP-адрес, связывает его с определённым проектом и запрашивает свободный порт у центрального API. Затем контейнер устанавливает обратный SSH-туннель, который пробрасывает выбранный порт на центральном сервере к локальному сервису контейнера. Таким образом, запросы, приходящие на центральный сервер (NGINX) на этом порту, перенаправляются через SSH-туннель на удалённый узел.
  
* **NGINX + API Server (центральный сервер с NGINX и API):** Размещён в папке `nginx/` и выполняет двойную функцию. С одной стороны, NGINX служит входной точкой для трафика (принимает подключения на множестве портов и может проксировать их), а с другой – запущенный рядом Python API управляет распределением IP и портов. Этот API хранит две ключевые JSON-конфигурации:

  * `ip_mapping.json` – маппинг проектов на IP-адреса. В этом файле хранится, какие IP уже привязаны к какому проекту. Это гарантирует, что один и тот же IP-адрес не будет назначен двум разным проектам одновременно.
  * `port_mapping.json` – маппинг проектов на наборы разрешённых портов. Определяет диапазоны или списки портов, которые могут использоваться для туннелей каждого проекта. Благодаря этому, проекты изолированы по портам и не конфликтуют друг с другом при пробросе соединений.

* Взаимодействие компонентов: Reverse Proxy Container при запуске обращается к API на центральном сервере: он получает список доступных портов и текущий маппинг IP, после чего выбирает, к какому проекту отнести свой IP (согласно свободным портам). Через SSH-подключение контейнер удалённо запускает на сервере скрипт добавления IP (`run_add_project_address.py`), обновляя central mapping. После этого устанавливается постоянный SSH-туннель (Remote Port Forwarding) от выбранного порта на сервере к локальному порту контейнера. NGINX на центральном узле либо сам слушает эти порты, либо SSH-сервер обеспечивает приём подключений – в результате внешний трафик, адресованный на выделенный порт центрального сервера, маршрутизируется через туннель на удалённый сервис.

## Назначение и применение
Данный репозиторий обеспечивает автоматическое распределение и проброс IP/портов без ручной настройки. Это особенно полезно в условиях децентрализованных облачных платформ (как Flux), где приложения развернуты на множестве узлов с динамическими IP. Система flux-reverse-proxy абстрагирует сетевую сложность: каждый новый контейнер сам регистрируется и получает входной канал связи, а центральный сервер знает о всех активных туннелях через JSON-маппинги. Такая архитектура облегчает масштабирование и исключает конфликт IP-адресов между проектами, поддерживая единообразный доступ к сервисам в распределённой среде.

## Ссылки
1. [reverse-proxy-container/: Контейнер обратного прокси](https://github.com/SSA1MON/flux-reverse-proxy/blob/main/reverse-proxy-container/README.md)
2. [nginx/: NGINX и API-сервер](https://github.com/SSA1MON/flux-reverse-proxy/blob/main/nginx/README.md)