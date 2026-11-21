# Go на VPS, AI-воркер в Google Colab

На VPS работают Go, PostgreSQL, RabbitMQ и MinIO. Colab запускает Python-воркер
и Ollama. Воркер подключается напрямую к опубликованным портам PostgreSQL и RabbitMQ.

## 1. Запустите VPS

Из корня репозитория скопируйте `.env.example` в `.env` при новой установке.
Задайте отдельные случайные пароли и ключи вместо значений из примера. Для уже
созданных томов используйте действующие учётные данные.

| Сервис | Внешний порт по умолчанию | Настройка в `.env` |
| --- | --- | --- |
| Go API и WebSocket | 18080 | `COLAB_BACKEND_PORT` |
| PostgreSQL | 15432 | `COLAB_POSTGRES_PORT` |
| RabbitMQ | 25673 | `COLAB_RABBITMQ_PORT` |
| MinIO S3 | 19000 | `COLAB_MINIO_PORT` |

Если порт занят, задайте свободное значение соответствующей переменной в `.env`.
Для браузерных ссылок на вложения задайте
`MINIO_PUBLIC_ENDPOINT=http://ПУБЛИЧНЫЙ_IP_VPS:19000` с фактическим портом MinIO.

Для запуска нужен Docker Compose 2.24.4 или новее. [Переопределение настроек Compose](https://docs.docker.com/reference/compose-file/merge/#replace-value)

```bash
docker compose -f docker-compose.yml -f deploy/colab/compose.public.yml up -d --build backend
docker compose ps -a
curl -fsS http://127.0.0.1:18080/health
```

Откройте выбранные TCP-порты в сетевом файрволе VPS для тех клиентов, которым
нужен доступ. Эта конфигурация публикует PostgreSQL и RabbitMQ напрямую, а
RabbitMQ использует AMQP без TLS. Go API использует переданный клиентом `user_id`,
поэтому доступ к нему стоит ограничить участниками демо. Панели RabbitMQ и
MinIO в этой конфигурации остаются внутри сети Docker.
[Публикация портов Docker](https://docs.docker.com/engine/network/port-publishing/)

## 2. Запустите Colab

Используйте репозиторий, склонированный в текущей среде Colab. По умолчанию
ноутбук ищет его в `/content/neti-next-hackaton`. Если клон лежит в другом каталоге,
задайте путь в `REPO_DIR` в первой ячейке.

1. Откройте [worker.ipynb](worker.ipynb) в Colab и выберите GPU. Укажите публичный IPv4 или DNS VPS, внешние порты PostgreSQL и RabbitMQ и имена пользователей из `.env`.
2. Добавьте в **Secrets** `VPS_RABBITMQ_PASSWORD` со значением `RABBITMQ_PASSWORD` и `VPS_RAG_POSTGRES_PASSWORD` со значением `RAG_POSTGRES_PASSWORD`. Разрешите ноутбуку доступ к обоим секретам.
3. Выполните ячейки по порядку. Ноутбук установит зависимости из клона, проверит подключения, применит миграции, построит эмбеддинги и запустит воркер.

После сброса среды Colab восстановите клон и повторите запуск ноутбука. Эмбеддинги остаются в PostgreSQL
на VPS. [Ограничения Colab](https://research.google.com/colaboratory/faq.html)

## 3. Проверьте ответ

Отправьте тестовый запрос с VPS. Подставьте фактический порт Go API.

```bash
API_URL=http://127.0.0.1:18080
USER_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
RESPONSE=$(curl -fsS "$API_URL/request" \
  -F "user_id=$USER_ID" -F 'message=Какой адрес главного корпуса УУНиТ в Уфе?')
CHAT_ID=$(printf '%s' "$RESPONSE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["chat_id"])')
curl -fsS "$API_URL/chats/$CHAT_ID/messages?user_id=$USER_ID"
```

Повторите последний GET после обработки запроса. Ответ агента появится в истории
с ролью `assistant`. Из браузера используйте публичный адрес VPS и порт Go API.
