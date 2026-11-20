from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

import app.main as main


async def test_health_and_lifespan(monkeypatch, settings):
    worker = SimpleNamespace(start=AsyncMock(), close=AsyncMock(), is_ready=True)
    model = SimpleNamespace(is_ready=AsyncMock(return_value=True))
    monkeypatch.setattr(main, "RabbitWorker", lambda *_: worker)
    monkeypatch.setattr(main, "OllamaClient", lambda *_: model)

    application = main.create_app(settings)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as client:
            assert (await client.get("/health")).status_code == 200

            worker.is_ready = False
            assert (await client.get("/health")).status_code == 503

            worker.is_ready = True
            model.is_ready.return_value = False
            assert (await client.get("/health")).status_code == 503

    worker.start.assert_awaited_once()
    worker.close.assert_awaited_once()
