# Think-About-It-Agent для УУНиТ

Веб-интерфейс помощника для абитуриентов и студентов Уфимского университета науки и технологий. В нём можно задать вопрос о поступлении, направлениях и студенческой жизни, продолжить диалог и открыть источники ответа.

Сценарий взят из базового университетского кейса трека ML Product и адаптирован для УУНиТ. [Описание кейса](https://docs.google.com/document/d/1abM0XMALBRC0ESZaYuCnDU85l00msq9RZelh9iXKuY4/edit) · [Официальный сайт УУНиТ](https://uust.ru/)

## Запуск

```powershell
cd frontend
npm ci
npm run dev
```

Vite запускает помощник УУНиТ на `http://localhost:5138/` и проксирует HTTP и WebSocket на Go-бэкенд по адресу `http://127.0.0.1:8080`. Для другого адреса задайте `CHAT_API_TARGET` в `frontend/.env.local` и перезапустите Vite. Инструкция запуска находится в [README бэкенда](../backend/README.md).

`npm run build` собирает фронтенд в `dist/`. При размещении сборки проксируйте `/request`, `/chats/` и `/ws` к Go-бэкенду на том же публичном домене. Для `/ws` прокси должен поддерживать WebSocket Upgrade. Адрес MinIO, на который указывают подписанные ссылки из вложений, должен быть доступен браузеру.

## Структура

Структура повторяет основные точки входа из [client в gazprom-hackaton](https://github.com/NikitaKovalenko111/gazprom-hackaton/tree/04f8a8181f082baea00b1df68c49a229e3250b06/client).

| Файл или каталог | Назначение |
| --- | --- |
| `src/main.tsx`, `src/App.tsx` | Точка входа React и маршруты React Router DOM |
| `src/pages/assistant/AssistantPage.tsx` | Экран чата |
| `src/components/` | Шапка, сообщения и иконки |
| `src/redux/store.ts`, `src/redux/assistantSlice.ts` | Redux Toolkit, текущая сессия, профиль и сообщения |
| `src/redux/saga/saga.ts` | Redux Saga, запрос ответа и обработка ошибки |
| `src/api/api.ts`, `src/api/messageBlocks.ts` | Axios, WebSocket и блоки сообщений |
| `src/assets/styles/scss/styles.scss` | Стили интерфейса |

## Контракт чата

Фронтенд подключается к `/ws?user_id=<UUID>`, ждёт событие `ready` и отправляет вопрос через `POST /request` как `multipart/form-data`. Для продолжения диалога отправляется `chat_id`, полученный от бэкенда. При создании нового диалога фронтенд выдаёт новый UUID и очищает историю.

Событие `agent_response` содержит блоки сообщения в порядке отображения. Фронтенд сопоставляет ответ с вопросом по `chat_id` и `request_message_id`. После обрыва соединения он ищет принятый ответ через `GET /chats/{chat_id}/messages`. Если вопрос уже принят, кнопка повтора проверяет его историю и не отправляет его заново.

Текст передаётся в блоке `text`, картинки — в `attachments` с подписанным `url`. Блок `map` содержит массив `points` с `latitude` и `longitude`. Одиночные карты из старых ответов поддерживают поля `lat` и `lon`. Модель определяет профиль по репликам диалога и передаёт его в текстовом блоке как `audience` (`applicant`, `student` или `unknown`). Фронтенд обновляет карточку профиля после ответа.

Фото главного корпуса FlankerFF кадрировано и тонировано в интерфейсе. [Оригинал на Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Bashkir_State_University_(Ufa).jpg) · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)
