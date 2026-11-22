# AI-сервис

Воркер на Python и FastAPI. Читает вопросы и контекст чата из `agent_requests`, обращается к OpenRouter и ищет сведения в схеме `rag` PostgreSQL через SQL и pgvector. Публикует ответы с текстом, источниками, фотографиями и координатами в `agent_responses`.

## Запуск

Укажите `OPENROUTER_API_KEY` в корневом `.env` по [общей инструкции](../README.md#запуск-с-чистого-окружения). Из корня репозитория запустите воркер и проверьте его доступность после индексации.

```sh
docker compose up --build -d ai-service
curl -fsS http://localhost:8000/health
```

Compose подготавливает базу знаний через `rag-index` и загружает фотографии через `campus-photos` перед запуском воркера. Имена очередей должны совпадать у Go-бэкенда и AI-сервиса.

## Проверка

Из каталога `ai-service` установите зависимости `python -m pip install -e '.[dev]'` в окружении Python 3.12+ и выполните `ruff check .` и `python -m pytest -q`. Тесты используют заглушку OpenRouter.

[Настройки, контракт очередей и переиндексация](REFERENCE.md) · [Инструменты поиска](tools/README.md)
