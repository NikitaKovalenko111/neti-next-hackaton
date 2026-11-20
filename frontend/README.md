# Think-About-It-Agent для УУНиТ

Веб-интерфейс помощника для абитуриентов и студентов Уфимского университета науки и технологий. В нём можно задать вопрос о поступлении, направлениях и студенческой жизни, продолжить диалог и открыть источники ответа.

Сценарий взят из базового университетского кейса трека ML Product и адаптирован для УУНиТ. [Описание кейса](https://docs.google.com/document/d/1abM0XMALBRC0ESZaYuCnDU85l00msq9RZelh9iXKuY4/edit) · [Официальный сайт УУНиТ](https://uust.ru/)

## Запуск

```powershell
cd frontend
npm ci
npm run dev
```

По умолчанию Vite запускается на `http://localhost:5137/` и направляет запросы к API на `http://localhost:3001`. Чтобы указать другой адрес ML-сервиса, добавьте в `frontend/.env.local` строку `CHAT_API_TARGET=http://localhost:8000` с вашим адресом и перезапустите Vite.

`npm run build` собирает фронтенд в `dist/`. При размещении сборки настройте на её домене маршрутизацию `/api/chat` к ML-сервису.

## Структура

Структура повторяет основные точки входа из [client в gazprom-hackaton](https://github.com/NikitaKovalenko111/gazprom-hackaton/tree/04f8a8181f082baea00b1df68c49a229e3250b06/client).

| Файл или каталог | Назначение |
| --- | --- |
| `src/main.tsx`, `src/App.tsx` | Точка входа React и маршруты React Router DOM |
| `src/pages/assistant/AssistantPage.tsx` | Экран чата |
| `src/components/` | Шапка, сообщения и иконки |
| `src/redux/store.ts`, `src/redux/assistantSlice.ts` | Redux Toolkit, текущая сессия, профиль и сообщения |
| `src/redux/saga/saga.ts` | Redux Saga, запрос ответа и обработка ошибки |
| `src/api/api.ts` | Клиент Axios и типы контракта чата |
| `src/assets/styles/scss/styles.scss` | Стили интерфейса |

## Контракт чата

`POST /api/chat` принимает JSON с `sessionId`, ролью `audience` (`applicant` или `student`) и массивом `history` из реплик с полями `role` и `content`. При создании нового диалога фронтенд выдаёт новый идентификатор и очищает историю. История текущей сессии хранится в памяти вкладки.

Сервис возвращает `answer` с текстом ответа или уточняющего вопроса, а также необязательные поля `sources` (список с `title`, `url` и необязательным `section`) и `followUps` (список предлагаемых вопросов).

Поиск по базе знаний УУНиТ, выбор источников, уточнение условий, обработка отсутствующих фактов и защита от prompt injection реализуются в ML-сервисе. В этом репозитории находится фронтенд и его клиент API.
