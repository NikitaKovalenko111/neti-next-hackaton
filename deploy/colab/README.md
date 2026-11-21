# Go на VPS, AI-воркер в Google Colab

VPS хранит данные и обслуживает Go API и WebSocket. Colab запускает Python-воркер и
Ollama. Воркер читает задания и публикует ответы в RabbitMQ, а через PostgreSQL
читает и индексирует схему `rag`. Оба соединения проходят через SSH. Порты базы,
RabbitMQ, MinIO и Go API в этой конфигурации слушают только `127.0.0.1` на VPS.

Колаб подходит для демонстраций и временных сеансов. Для воркера, обслуживающего
внешнее приложение, используйте среду, допускающую такой сценарий, например Colab
с положительным балансом compute units или Colab Enterprise. Сеанс может
завершиться, поэтому запуск повторяется из ноутбука. Пока воркер отключён, VPS
продолжает принимать и сохранять запросы. [Ограничения Colab](https://research.google.com/colaboratory/faq.html)

## 1. Поднимите сервер

На VPS с Docker Engine и Docker Compose откройте каталог репозитория. Для новой
установки создайте `.env` из примера и замените стандартные пароли и ключ MinIO.
Используйте случайные значения из букв и цифр, например вывод `openssl rand -hex 24` для
каждого пароля. Если тома PostgreSQL и RabbitMQ уже созданы, используйте реальные
учётные данные этих сервисов.

```bash
umask 077
cp -n .env.example .env
# Заполните секреты в .env перед запуском.
docker compose up -d --build backend
docker compose ps -a
curl -fsS http://127.0.0.1:8080/health
```

Команда `up backend` поднимет PostgreSQL, `postgres-init`, RabbitMQ, MinIO и Go.
В выводе `ps -a` для `postgres-init` ожидается `Exited (0)`. Для SSH-туннеля доступ
из интернета нужен к SSH VPS. Порты базы, очереди и их панели оставьте закрытыми
в файрволе.

Создайте отдельного пользователя RabbitMQ для воркера. Команды ниже рассчитаны
на стандартные очереди `agent_requests` и `agent_responses`. При других именах
согласуйте регулярные выражения и настройки ноутбука. Введите длинный случайный
пароль и сохраните его в Colab Secrets.

```bash
read -rsp 'Пароль colab_worker: ' COLAB_RABBIT_PASSWORD
printf '\n'
docker compose exec -T rabbitmq rabbitmqctl add_user colab_worker "$COLAB_RABBIT_PASSWORD"
docker compose exec -T rabbitmq rabbitmqctl set_permissions -p / colab_worker \
  '^agent_(requests|responses)$' '^amq\.default$' '^agent_requests$'
unset COLAB_RABBIT_PASSWORD
```

Пользователь объявляет две очереди, читает запросы и публикует ответы в стандартный
exchange. Для PostgreSQL используется `RAG_POSTGRES_USER` из `.env`, по умолчанию
`rag_app`. Роль позволяет воркеру применять миграции и индексировать данные в `rag`.
[Права RabbitMQ](https://www.rabbitmq.com/docs/access-control)

## 2. Разрешите SSH-туннель

На своём компьютере сгенерируйте отдельный ключ для ноутбука. OpenSSH будет
использовать его без интерактивного запроса пароля.

```bash
mkdir -p -m 700 ~/.ssh
ssh-keygen -t ed25519 -N '' -f ~/.ssh/university-colab -C 'university-colab'
```

На VPS создайте пользователя `colab-agent`. Пример ниже для Ubuntu/Debian.
Если на сервере действуют `AllowUsers` или `AllowGroups`, учтите их при добавлении
пользователя.

```bash
sudo adduser --disabled-password --gecos "" colab-agent
sudo install -d -m 700 -o colab-agent -g colab-agent /home/colab-agent/.ssh
sudoedit /home/colab-agent/.ssh/authorized_keys
sudo chown colab-agent:colab-agent /home/colab-agent/.ssh/authorized_keys
sudo chmod 600 /home/colab-agent/.ssh/authorized_keys
```

В `authorized_keys` добавьте одной строкой параметры и содержимое
`~/.ssh/university-colab.pub`. Подставьте фактические порты `RABBITMQ_PORT` и
`POSTGRES_PORT` из `.env`.

```text
restrict,port-forwarding,permitopen="127.0.0.1:5672",permitopen="127.0.0.1:5433",command="/bin/false" ssh-ed25519 AAAA... university-colab
```

В `/etc/ssh/sshd_config.d/90-colab-agent.conf` добавьте:

```text
Match User colab-agent
    AllowTcpForwarding local
    PasswordAuthentication no
    KbdInteractiveAuthentication no
Match all
```

Проверьте конфигурацию и перечитайте её, сохранив текущую административную сессию.
Публичный ключ хоста возьмите из вывода `cat` на доверенной сессии VPS. Ноутбук
сверяет этот ключ при подключении.

```bash
sudo sshd -t && sudo systemctl reload ssh
cat /etc/ssh/ssh_host_ed25519_key.pub
```

[Ограничения ключей OpenSSH](https://man.openbsd.org/sshd#AUTHORIZED_KEYS_FILE_FORMAT)

## 3. Запустите ноутбук

Соберите архив на компьютере из той версии репозитория, которую хотите запустить.
Архив содержит только код, зависимости и миграции AI-сервиса. Он подходит и для
локальной ветки, которую ещё не отправили в GitHub.

```bash
tar --exclude='__pycache__' --exclude='*.pyc' -czf /tmp/colab-worker.tar.gz \
  -C ai-service app tools pyproject.toml
```

1. Загрузите [worker.ipynb](worker.ipynb) в Colab и выберите GPU. В первой ячейке укажите белый IPv4 или DNS VPS, SSH-порт и параметры сервисов из `.env`. Локальные порты Colab можно оставить по умолчанию.
2. На своём компьютере получите ключ в однострочном формате, затем добавьте секреты в панели **Secrets** и разрешите доступ этому ноутбуку.

   ```bash
   base64 < ~/.ssh/university-colab | tr -d '\r\n'
   ```

   | Имя секрета | Значение |
   | --- | --- |
   | `VPS_SSH_PRIVATE_KEY_B64` | Однострочный вывод команды выше |
   | `VPS_SSH_HOST_KEY` | Ключ хоста из `/etc/ssh/ssh_host_ed25519_key.pub` |
   | `VPS_RABBITMQ_PASSWORD` | Пароль `colab_worker` |
   | `VPS_RAG_POSTGRES_PASSWORD` | Значение `RAG_POSTGRES_PASSWORD` из `.env` VPS |

3. Выполните ячейки по порядку и загрузите `colab-worker.tar.gz` по запросу. Ноутбук поднимет SSH-туннель, применит миграции, скачает модели Ollama, заполнит pgvector и запустит воркер. В конце `/health` покажет `rabbitmq: true` и `ollama: true`.

После завершения сеанса Colab запустите ноутбук снова. Модели загружаются в новую
среду, а векторы остаются на VPS. При замене модели измените её имя в настройках
ноутбука и повторите индексацию. [Установка Ollama](https://docs.ollama.com/linux)

## 4. Проверьте ответ

Выполните на VPS. Для повторной проверки создайте новый запрос.

```bash
USER_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
RESPONSE=$(curl -fsS http://127.0.0.1:8080/request \
  -F "user_id=$USER_ID" -F 'message=Какой адрес главного корпуса УУНиТ в Уфе?')
CHAT_ID=$(printf '%s' "$RESPONSE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["chat_id"])')
curl -fsS "http://127.0.0.1:8080/chats/$CHAT_ID/messages?user_id=$USER_ID"
```

Повторяйте последний GET, пока в истории не появится сообщение с
`"role":"assistant"`. Первый ответ на GPU может потребовать загрузки модели в
память. Для диагностики откройте журналы в ноутбуке или выполните
`docker compose logs --tail 100 backend rabbitmq postgres` на VPS.

Для демо с вашего компьютера пробросьте Go API и MinIO отдельной командой под
обычной административной учётной записью VPS. Так браузер сможет открыть
WebSocket и подписанные ссылки, если `MINIO_PUBLIC_ENDPOINT` оставлен стандартным
и совпадает с локальным портом.

```bash
ssh -N -L 127.0.0.1:8080:127.0.0.1:8080 -L 127.0.0.1:9000:127.0.0.1:9000 deploy@VPS_HOST
```

Публичное размещение браузерного клиента требует HTTPS и аутентификации на
границе приложения. Сейчас Go API принимает идентификатор пользователя из запроса.
