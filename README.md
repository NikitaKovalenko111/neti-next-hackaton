# University AI agent

## Общий запуск

Из корня репозитория:

```sh
cp .env.example .env
docker compose up --build -d
docker compose logs -f ollama-init ai-service backend
```

Общий `docker-compose.yml` поднимает backend, ai-service, PostgreSQL, RabbitMQ, MinIO и Ollama в одной сети. Отдельный `ollama-init` скачивает `qwen3:4b`; AI-сервис запускается после завершения загрузки. Backend ждёт готовности PostgreSQL, RabbitMQ и MinIO и автоматически применяет миграции. До готовности модели запросы могут накапливаться в очереди.

Первый запуск требует сборки образов и загрузки модели. По умолчанию Ollama использует CPU. Frontend пока отсутствует в репозитории и в общий Compose не включён.

MinIO собирается из закреплённого исходного релиза `RELEASE.2025-09-07T16-13-09Z` через [deploy/minio/Dockerfile](deploy/minio/Dockerfile), поскольку [официальная community-версия распространяется как исходники](https://github.com/minio/minio#source-only-distribution). Dockerfile AI-сервиса находится в [ai-service/Dockerfile](ai-service/Dockerfile).

## Адреса

| Сервис | Адрес по умолчанию |
| --- | --- |
| Backend | http://localhost:8080/health |
| WebSocket | ws://localhost:8080/ws?user_id=UUID |
| AI service | http://localhost:8000/health |
| PostgreSQL | localhost:5433 |
| RabbitMQ | localhost:5672 |
| RabbitMQ UI | http://localhost:15672 |
| MinIO API | http://localhost:9000 |
| MinIO Console | http://localhost:9001 |
| Ollama | http://localhost:11434 |

Все порты публикуются на `127.0.0.1`. PostgreSQL снаружи использует порт `5433`, чтобы не конфликтовать с локальной БД; внутри сети контейнеров — `5432`.

В `.env.example` заданы настройки для локальной разработки: PostgreSQL `postgres/postgres`, RabbitMQ `university/university`, MinIO `minioadmin/minioadmin`. У backend и AI-сервиса одинаковые адрес RabbitMQ и имена очередей `agent_requests`/`agent_responses`.

Backend обращается к MinIO внутри сети по `minio:9000`, а ссылки для браузера подписывает с адресом `MINIO_PUBLIC_ENDPOINT`. По умолчанию это `http://localhost:${MINIO_PORT}`. Для доступа с другого компьютера укажите публичный URL и настройте публикацию соответствующих портов. `MINIO_REGION` применяется и к серверу MinIO, и к клиенту backend.

Имена пользователей и пароли PostgreSQL/RabbitMQ используются в URL подключения. Если в них есть зарезервированные символы URL, настройте URL подключения в Compose с корректным кодированием.

## Управление

```sh
docker compose ps
docker compose logs -f backend ai-service
docker compose stop
docker compose up -d
docker compose down
```

Данные PostgreSQL, RabbitMQ, MinIO и скачанная модель сохраняются в именованных volumes. `docker compose down` их сохраняет; `docker compose down -v` удаляет данные и модель.

Подкаталоги сохраняют отдельные Compose-файлы для автономной разработки. Для совместного запуска используйте только корневой файл, чтобы приложения работали с одним брокером и не конфликтовали по портам. Volumes разных Compose-проектов не объединяются; существующие данные автономных запусков автоматически не переносятся.

Описание контрактов и локальных запусков: [backend](backend/README.md), [ai-service](ai-service/README.md).
