import json

import httpx
import pytest

from app.clients.ollama import OllamaClient


async def test_ollama_uses_configured_model_without_streaming_or_thinking(settings):
    def respond(request):
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        assert payload["model"] == "qwen3:4b"
        assert payload["stream"] is False
        assert payload["think"] is False
        assert payload["messages"] == [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "question"},
        ]
        return httpx.Response(200, json={"message": {"content": " Answer "}, "done": True})

    async with httpx.AsyncClient(
        base_url=str(settings.ollama_base_url), transport=httpx.MockTransport(respond)
    ) as client:
        assert await OllamaClient(client, settings).generate("system", "question") == "Answer"


@pytest.mark.parametrize(
    "payload",
    [
        {"message": {"content": ""}, "done": True},
        {"message": {"content": "Answer"}, "done": False},
        {"done": True},
    ],
)
async def test_empty_or_incomplete_answer_is_not_published(settings, payload):
    async with httpx.AsyncClient(
        base_url=str(settings.ollama_base_url),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    ) as client:
        with pytest.raises(ValueError):
            await OllamaClient(client, settings).generate("system", "question")


async def test_ollama_unavailable_propagates_to_worker(settings):
    async with httpx.AsyncClient(
        base_url=str(settings.ollama_base_url),
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await OllamaClient(client, settings).generate("system", "question")


@pytest.mark.parametrize("models, expected", [([], False), ([{"name": "qwen3:4b"}], True)])
async def test_readiness_requires_downloaded_model(settings, models, expected):
    async with httpx.AsyncClient(
        base_url=str(settings.ollama_base_url),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"models": models})),
    ) as client:
        assert await OllamaClient(client, settings).is_ready() is expected
