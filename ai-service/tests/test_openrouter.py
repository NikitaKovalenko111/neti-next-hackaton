import json

import httpx
import pytest

from app.clients.openrouter import OpenRouterClient, openrouter_http
from app.embeddings import DIMENSIONS, embed


@pytest.mark.parametrize("qwen_3_5", [False, True])
async def test_openrouter_uses_configured_model_without_streaming(settings, qwen_3_5):
    if qwen_3_5:
        settings = settings.model_copy(update={"openrouter_model": "qwen/qwen3.5-9b"})

    def respond(request):
        assert request.url.path == "/api/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == settings.openrouter_model
        assert payload["stream"] is False
        assert payload["max_tokens"] == settings.openrouter_max_tokens
        assert payload["provider"] == {"require_parameters": True}
        assert payload.get("reasoning") == ({"enabled": False} if qwen_3_5 else None)
        assert payload["messages"] == [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "question"},
        ]
        return httpx.Response(200, json={"choices": [{"message": {"content": " Answer "}}]})

    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url), transport=httpx.MockTransport(respond)
    ) as client:
        assert await OpenRouterClient(client, settings).generate("system", "question") == "Answer"


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": "Answer"}, "error": {"code": 500}}]},
        {"choices": []},
    ],
)
async def test_empty_or_incomplete_answer_is_not_published(settings, payload):
    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    ) as client:
        with pytest.raises(ValueError):
            await OpenRouterClient(client, settings).generate("system", "question")


async def test_openrouter_unavailable_propagates_to_worker(settings):
    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url),
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await OpenRouterClient(client, settings).generate("system", "question")


@pytest.mark.parametrize("status, expected", [(200, True), (401, False)])
async def test_readiness_checks_the_api_key(settings, status, expected):
    def respond(request):
        assert request.url.path == "/api/v1/key"
        return httpx.Response(status, json={"data": {"label": "test"}})

    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url),
        transport=httpx.MockTransport(respond),
    ) as client:
        assert await OpenRouterClient(client, settings).is_ready() is expected


async def test_http_client_sets_bearer_token(settings):
    async with openrouter_http(settings) as client:
        assert client.headers["Authorization"] == "Bearer test-key"


async def test_local_ollama_uses_installed_models_and_sends_no_openrouter_credentials(settings):
    local = settings.model_copy(update={"ollama_base_url": "http://localhost:11434/v1/"})
    async with openrouter_http(local) as client:
        assert "Authorization" not in client.headers
        assert client.base_url.host == "localhost"

    response_format = {"type": "json_schema", "json_schema": {"name": "answer"}}

    def respond(request):
        if request.url.path == "/v1/models":
            return httpx.Response(
                200, json={"data": [{"id": local.ollama_model}, {"id": local.embedding_model}]}
            )
        payload = json.loads(request.content)
        assert payload["model"] == local.ollama_model
        assert payload["response_format"] == response_format
        assert {"provider", "tool_choice", "tools"}.isdisjoint(payload)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    async with httpx.AsyncClient(
        base_url=str(local.ollama_base_url), transport=httpx.MockTransport(respond)
    ) as client:
        model = OpenRouterClient(client, local)
        assert await model.is_ready()
        await model.chat(
            [{"role": "user", "content": "question"}],
            [{"type": "function"}],
            tool_choice="none",
            response_format=response_format,
        )


async def test_embeddings_are_reordered_by_openrouter_index(settings):
    def respond(request):
        assert request.url.path == "/api/v1/embeddings"
        payload = json.loads(request.content)
        assert payload["input"] == ["первый", "второй"]
        assert payload["model"] == settings.openrouter_embedding_model
        assert payload["dimensions"] == DIMENSIONS
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.2] * DIMENSIONS},
                    {"index": 0, "embedding": [0.1] * DIMENSIONS},
                ]
            },
        )

    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url), transport=httpx.MockTransport(respond)
    ) as client:
        vectors = await embed(client, settings.openrouter_embedding_model, ["первый", "второй"])
        assert [json.loads(vector)[0] for vector in vectors] == [0.1, 0.2]
