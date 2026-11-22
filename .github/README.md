# CI

Workflow `ci.yml` запускается на push во все ветки, pull request и вручную.

- Backend включается при наличии `backend/go.mod`: проверка зависимостей, `gofmt`, `go vet`, Staticcheck, тесты с `-race`, интеграционные тесты с PostgreSQL 16 и сборка. Версия Go берётся из `go.mod`.
- Frontend включается при наличии `frontend/package.json`: установка по lockfile и запуск доступных scripts `lint`, `format:check`, `typecheck` (или `type-check`), `test:ci` (или `test`), `build`. Поддерживаются npm, pnpm и Yarn; нужен один соответствующий lockfile. Node.js — 22, версии pnpm/Yarn берутся из `packageManager`, если он указан.
- При наличии `ai-service/pyproject.toml` запускаются Ruff и pytest на Python 3.12. Интеграционные тесты используют RabbitMQ и имитируют ответы OpenRouter.
- Отсутствующий компонент получает `skipped`. Отсутствующий frontend script также пропускается с сообщением в логе; ошибка существующего script проваливает CI.
- Если `npm ci` обнаруживает рассинхронизацию `package-lock.json`, CI сообщает о ней через warning и job summary, затем устанавливает зависимости из `package.json` с `--no-package-lock --no-save`. Файлы frontend не исправляются. До исправления lockfile frontend-разработчиком версии определяются диапазонами из `package.json`, а не закреплённым деревом. Линтер, тесты и сборка продолжают выполняться; остальные ошибки установки остаются блокирующими.
- Проверка workflow через actionlint выполняется всегда, даже в ветках без приложения.
- `CI result` — общая проверка для branch protection: принимает успешные проверки и пропуски отсутствующих компонентов, но не принимает ошибки и отмены.

Для Go-тестов в CI автоматически поднимается PostgreSQL. `TestFullPipeline` также требует RabbitMQ и MinIO. Его можно запустить локально по инструкции в README бэкенда. Секреты для CI не нужны.

Чтобы добавить новый компонент с другой структурой, дополните job `detect` и добавьте его проверку в зависимости `CI result`.
