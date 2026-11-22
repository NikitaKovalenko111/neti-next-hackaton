# Фронтенд

Веб-чат УУНиТ на React, TypeScript и Vite. Показывает историю диалогов, ответы в Markdown, источники, фотографии и карты. В Docker Nginx обслуживает сборку и проксирует HTTP, WebSocket и подписанные ссылки MinIO.

## Запуск

Подготовьте корневой `.env` по [общей инструкции](../README.md#запуск-с-чистого-окружения), выполните из корня `docker compose up --build -d` и откройте [веб-чат](http://localhost:5138/).

Для локальной разработки запустите бэкенд и выполните команды из каталога `frontend` с Node.js 22.

```sh
npm ci
npm run dev
```

Vite доступен на `http://localhost:5138/` и проксирует API и `/ws` на `http://127.0.0.1:8080`. Другой адрес Go-бэкенда можно задать переменной `CHAT_API_TARGET` в `frontend/.env.local`. Если этот порт уже занят контейнером фронтенда, укажите другой через `npm run dev -- --port 5173`. Для изображений в режиме разработки бэкенду нужен `MINIO_PUBLIC_ENDPOINT` с адресом, доступным браузеру, например `http://localhost:9000`.

## Проверка

`npm run lint` проверяет код. `npm run build` проверяет типы и сохраняет сборку в `dist/`. Формат ответов описан в [контракте WebSocket](../backend/API.md#websocket).

Сценарий разработан на основе университетского кейса трека ML Product. [Описание кейса](https://docs.google.com/document/d/1abM0XMALBRC0ESZaYuCnDU85l00msq9RZelh9iXKuY4/edit) · [Официальный сайт УУНиТ](https://uust.ru/)

Фото главного корпуса FlankerFF кадрировано и тонировано в интерфейсе. [Оригинал на Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Bashkir_State_University_(Ufa).jpg) · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)
