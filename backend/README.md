# Backend

Для запуска всего проекта используйте `docker compose up --build -d` из корня репозитория; настройки описаны в [общем README](../README.md). Ниже приведён автономный запуск backend.

Запуск инфраструктуры и сервиса из каталога `backend`:

```sh
docker compose -f docker-compose.infrastructure.yml up -d
docker compose -f docker-compose.infrastructure.yml run --rm postgres-init
go run ./cmd/university-agent
```

`GET http://localhost:8080/health` возвращает статус 200. При запуске сервис подключается к PostgreSQL и RabbitMQ, создаёт очереди `agent_requests` (запросы агенту) и `agent_responses` (ответы агента), проверяет или создаёт бакет MinIO `images`. Очереди устойчивые и сохраняются после перезапуска RabbitMQ.

Настройки через переменные окружения: `HTTP_ADDRESS`, `POSTGRES_URL`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MINIO_SECURE`, `RABBITMQ_URL`, `RABBITMQ_QUEUE` (имя очереди запросов), `RABBITMQ_RESPONSE_QUEUE` (имя очереди ответов). Имена очередей должны различаться. Значения по умолчанию соответствуют локальному Compose и предназначены для разработки.

`MINIO_PUBLIC_ENDPOINT` — необязательный публичный URL вида `http://localhost:9000` для подписанных ссылок клиенту. Если он не задан, ссылки используют `MINIO_ENDPOINT`. `MINIO_REGION` по умолчанию равен `us-east-1` и должен совпадать с регионом сервера.

По умолчанию PostgreSQL: `postgres://backend_app:backend_app@localhost:5433/university?sslmode=disable&search_path=backend`. Роль `backend_app` владеет схемой `backend`; все таблицы и журнал миграций создаются в ней. Если `POSTGRES_URL` не задаёт `search_path`, подключение использует `backend`. Подготовку схем и ролей выполняет отдельный `postgres-init` от администратора. Схема `rag` принадлежит отдельной роли `rag_app`; backend не получает доступа к ней.

Миграции из `internal/migrations` применяются при запуске. Для отправки сообщения используйте `POST /request` с `multipart/form-data`: обязательный `user_id` — UUID пользователя, `message` — текст, повторяющееся поле `attachments` — файлы изображений. Необязательный `chat_id` (UUID) продолжает существующий чат; без него создаётся новый. Должны присутствовать текст или хотя бы одно изображение. Максимальный размер всего запроса — 32 МиБ.

```sh
curl -X POST http://localhost:8080/request \
  -F 'user_id=11111111-1111-4111-8111-111111111111' \
  -F 'message=Привет' \
  -F 'attachments=@photo.jpg'
```

Ответ `202 Accepted` содержит `chat_id`, `message_id` и список `attachments` с `attachment_id` и `filename`. Для следующего сообщения передайте полученный `chat_id`.

Сообщение и задача для агента сохраняются одной транзакцией. Фоновый обработчик читает таблицу `agent_request_outbox` раз в секунду, отправляет задачи в RabbitMQ как persistent-сообщения и удаляет их из outbox после подтверждения брокера. При сбое отправка повторяется. Агент должен обрабатывать повторные задачи с одним `message_id` идемпотентно.

## WebSocket

До отправки запроса подключитесь к `ws://localhost:8080/ws?user_id=<UUID>`. Сервер отправит `{"type":"ready"}`, когда подписка готова. После этого можно отправлять `POST /request`.

```js
const socket = new WebSocket(`ws://localhost:8080/ws?user_id=${userId}`);

socket.onmessage = ({ data }) => {
  const event = JSON.parse(data);

  if (event.type === "ready") {
    // Подписка активна: можно отправлять POST /request и загрузить историю.
  }

  if (event.type === "agent_response") {
    // Добавьте ответ в чат. Удаляйте дубликаты по event.message_id.
    console.log(event);
  }
};
```

Ответы отправляются всем активным WebSocket-соединениям пользователя:

```json
{
  "type": "agent_response",
  "chat_id": "UUID",
  "request_message_id": "UUID исходного запроса",
  "message_id": "UUID ответа",
  "blocks": [
    {
      "type": "text",
      "message": "Вот схема корпуса:",
      "source": ["https://uust.ru/reception/pass-application/"]
    },
    {
      "type": "attachments",
      "attachments": [
        {
          "attachment_id": "UUID",
          "filename": "building.png",
          "content_type": "image/png",
          "bucket": "images",
          "object_key": "agent/building.png",
          "size_bytes": 12345,
          "url": "http://localhost:9000/images/agent/building.png?X-Amz-..."
        }
      ]
    },
    { "type": "text", "message": "Аудитория находится на втором этаже." }
  ],
  "created_at": "2026-11-20T10:00:00Z"
}
```

Сервер проверяет Origin: браузерные подключения разрешены с того же хоста. WebSocket используется для событий от сервера; текст и файлы клиент отправляет через HTTP. Сервер отправляет ping, браузер отвечает pong автоматически.

После переподключения дождитесь `ready` и загрузите историю через `GET /chats/{chat_id}/messages?user_id=<UUID>`. Возвращается массив сообщений с `role` (`user` или `assistant`), `blocks`, временем и `request_message_id` у ответов. Формат `blocks` одинаков в истории и WebSocket. Сообщения пользователя также представлены блоками: текст, затем вложения. Страница содержит до 100 сообщений в хронологическом порядке. Чтобы получить следующую страницу, добавьте `after=<message_id последнего сообщения>`. Объединяйте историю с WebSocket-событиями по `message_id`.

У текстового блока может быть поле `source` с массивом ссылок на использованные источники. Оно доступно в WebSocket и в истории чата.

Порядок блоков и вложений сохраняется. Для отображения вложений используйте `url`: backend формирует подписанные ссылки MinIO сроком на 15 минут. В БД ссылки не сохраняются; повторное получение истории обновляет их. Для отдельного адреса, доступного браузеру, задайте `MINIO_PUBLIC_ENDPOINT`.

Ответ сохраняется в PostgreSQL перед отправкой события и подтверждением RabbitMQ. Если клиент отключён, результат остаётся в истории. WebSocket не гарантирует доставку; медленные соединения закрываются, после переподключения следует загрузить историю. Повторная доставка ответа агентом не создаёт второе сообщение, но может повторно отправить событие с тем же `message_id`.

Проверка `user_id` ограничивается форматом UUID и принадлежностью чата; аутентификация пока не реализована. Эта схема подписок рассчитана на один экземпляр backend, поскольку активные соединения хранятся в его памяти. При потере соединения RabbitMQ backend завершает работу; outbox и история сохраняются для следующего запуска.

## Контракт агента

Агент читает JSON из `agent_requests`. В продолжении диалога `history` содержит до восьми предыдущих текстовых реплик из этого же чата в хронологическом порядке. Каждая реплика имеет поля `role` и `message`.

```json
{
  "message_id": "UUID исходного запроса",
  "chat_id": "UUID",
  "user_id": "UUID",
  "message": "Вопрос пользователя",
  "attachments": [
    {
      "attachment_id": "UUID",
      "bucket": "images",
      "object_key": "chat_id/message_id/attachment_id",
      "filename": "photo.jpg",
      "content_type": "image/jpeg"
    }
  ]
}
```

Для получения изображения агент использует `bucket` и `object_key` через MinIO SDK со своими настройками подключения. AMQP `message_id` и `correlation_id` равны ID исходного сообщения, `reply_to` содержит имя очереди ответов.

После обработки агент публикует persistent-сообщение в `agent_responses` (или имя из `reply_to`):

```json
{
  "request_message_id": "UUID исходного запроса",
  "blocks": [
    { "type": "text", "message": "Вот схема корпуса:" },
    {
      "type": "attachments",
      "attachments": [
        {
          "attachment_id": "UUID",
          "filename": "building.png",
          "content_type": "image/png",
          "bucket": "images",
          "object_key": "agent/building.png"
        }
      ]
    },
    { "type": "text", "message": "Аудитория находится на втором этаже." }
  ]
}
```

`blocks` обязателен и должен содержать хотя бы один блок. Сейчас поддерживаются:

- `text` с непустым `message` и необязательным `audience` (`applicant`, `student` или `unknown`).
- `attachments`: обязательный непустой массив `attachments`; у каждого файла обязательны `attachment_id`, `filename`, корректный MIME `content_type`, `bucket` и `object_key`.
- `map` с координатами `lat` и `lon` и необязательными `title` и `address`.

До публикации ответа агент загружает файлы в бакет из `MINIO_BUCKET`. Backend проверяет их наличие в MinIO, определяет размер и сохраняет метаданные в таблице `attachments` одной транзакцией с блоками ответа. Для каждого вложения нужен новый UUID; один объект MinIO может использоваться в разных сообщениях с разными `attachment_id`. Повторять ID или объект в одном ответе нельзя. `size_bytes` определяет backend, переданный агентом `url` не используется.

Блоки сохраняются в поле `messages.blocks` типа JSONB. Миграция `003_message_blocks.sql` преобразует существующий текст и вложения в блоки. Старый формат ответа агента с единственным полем `message` больше не принимается; формат `POST /request` и задач в `agent_requests` остаётся текстом с вложениями.

Агент должен подтвердить задачу после подтверждённой публикации ответа. Backend определяет чат и пользователя по исходному сообщению в БД. Некорректный JSON, неизвестный тип блока, пустой текст или массив вложений, отсутствующий файл в MinIO, конфликт attachment ID или неизвестный `request_message_id` отклоняются без повторной постановки; временные ошибки БД и MinIO приводят к повторной доставке.

## Проверка

```sh
go test ./...
# Интеграционный тест использует отдельную временную схему в указанной БД:
TEST_DATABASE_URL='postgres://postgres:postgres@localhost:5432/university?sslmode=disable' go test ./internal/app ./internal/migrations -v
```

Интеграционные тесты проверяют преобразование старых сообщений, HTTP, PostgreSQL, outbox, порядок блоков, вложения, повторную доставку ответа, историю и WebSocket. RabbitMQ и MinIO в этих тестах заменены тестовыми реализациями.

Для сквозного теста с реальными PostgreSQL, RabbitMQ и MinIO:

```sh
TEST_DATABASE_URL='postgres://postgres:postgres@localhost:5432/university?sslmode=disable' \
TEST_RABBITMQ_URL='amqp://guest:guest@localhost:5672/' \
TEST_MINIO_ENDPOINT='localhost:9000' \
go test -race -count=1 -timeout 60s ./internal/app -run '^TestFullPipeline$' -v
```

При необходимости задайте `TEST_MINIO_ACCESS_KEY` и `TEST_MINIO_SECRET_KEY` (по умолчанию `minioadmin`). Тест запускает приложение, использует отдельные схему БД, бакет и очереди, после завершения удаляет свои данные. Нейросеть заменяется AMQP-клиентом, который получает настоящую задачу из RabbitMQ и публикует ответ. Проверяются загрузка исходного изображения, сохранение истории, публикация и получение через обе очереди, WebSocket, скачивание ответа по подписанному URL MinIO, отсутствие дубликатов и восстановление истории после отключения клиента. Без всех трёх переменных окружения этот тест пропускается.
