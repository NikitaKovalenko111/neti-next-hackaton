import json
from unittest.mock import AsyncMock, call

import httpx

from app.clients.openrouter import OpenRouterClient
from app.models import ConversationContext, ConversationTurn
from app.services.agent import AgentService
from app.services.tool_calling import MAX_TOOL_CALLS, MAX_TOOL_ROUNDS, ToolCallingAgent


def tool_call(name, **arguments):
    return {
        "id": f"call_{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def reply(**message):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", **message}}]})


def final_reply(text, source=()):
    return reply(content=json.dumps({"message": text, "source": list(source)}) + "<|endoftext|>")


async def test_agent_returns_answer_after_two_tool_rounds(settings, request_message):
    calls = []
    execute = AsyncMock(
        side_effect=[
            {"status": "ok", "data": [{"id": "death_of_close_relative"}]},
            {
                "status": "ok",
                "data": {
                    "deadline_months": 6,
                    "source_url": "https://uust.ru/policy/",
                    "verification": "official_address_confirmed",
                    "checked_on": "2026-11-20",
                },
            },
            {"status": "not_found", "data": []},
        ]
    )

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert request.url.path == "/api/v1/chat/completions"
        assert len(payload["tools"]) == 23
        if len(calls) == 1:
            return reply(
                content="",
                tool_calls=[tool_call("search_support_grounds", query=request_message.message)],
            )
        if len(calls) == 2:
            assert payload["messages"][-2]["role"] == "assistant"
            assert payload["messages"][-1]["tool_call_id"] == "call_search_support_grounds"
            data = json.loads(payload["messages"][-1]["content"])
            assert data["data"][0]["id"] == "death_of_close_relative"
            return reply(
                content="",
                tool_calls=[
                    tool_call("get_support_ground", ground_id="death_of_close_relative"),
                    tool_call("list_support_channels", branch_id="ufa"),
                ],
            )
        if len(calls) == 4:
            assert payload["response_format"]["type"] == "json_schema"
            assert payload["tool_choice"] == "none"
            return final_reply(
                "Срок по этому основанию — 6 месяцев. (status: official_address_confirmed)"
                "\n\nИсточник: https://uust.ru/policy/",
                [
                    "https://uust.ru/policy/",
                    "https://uust.ru/policy/",
                    "https://example.com/invented",
                ],
            )
        results = payload["messages"][-2:]
        assert [result["tool_call_id"] for result in results] == [
            "call_get_support_ground",
            "call_list_support_channels",
        ]
        data = json.loads(results[0]["content"])["data"]
        assert data == {"deadline_months": 6, "source_url": "https://uust.ru/policy/"}
        assert json.loads(results[1]["content"])["status"] == "not_found"
        return reply(content="Срок по этому основанию — 6 месяцев.")

    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url),
        transport=httpx.MockTransport(respond),
    ) as client:
        agent = AgentService(ToolCallingAgent(OpenRouterClient(client, settings), execute))
        response = await agent.process(request_message)
        assert response.blocks[0].message == "Срок по этому основанию — 6 месяцев."
        assert response.blocks[0].source == ["https://uust.ru/policy/"]
        assert await agent.process(request_message) == response

    assert len(calls) == 4
    assert execute.await_args_list == [
        call("search_support_grounds", {"query": request_message.message}),
        call("get_support_ground", {"ground_id": "death_of_close_relative"}),
        call("list_support_channels", {"branch_id": "ufa"}),
    ]


async def test_model_can_answer_without_querying_postgres(settings):
    execute = AsyncMock()
    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url),
        transport=httpx.MockTransport(lambda _: final_reply("Здравствуйте!")),
    ) as client:
        agent = ToolCallingAgent(OpenRouterClient(client, settings), execute)
        assert (await agent.generate("system", "Здравствуйте")).message == "Здравствуйте!"
    execute.assert_not_awaited()


async def test_tool_budget_limits_calls_in_one_model_response(settings):
    rounds = []
    execute = AsyncMock(return_value={"status": "unavailable", "reason": "database_error"})

    def respond(request):
        payload = json.loads(request.content)
        rounds.append(payload)
        if len(rounds) == 1:
            return reply(tool_calls=[tool_call("get_data_scope")] * (MAX_TOOL_CALLS + 1))
        assert payload["tool_choice"] == "none"
        assert len(payload["tools"]) == 23
        assistant = payload["messages"][2]
        assert len(assistant["tool_calls"]) == MAX_TOOL_CALLS
        tool_results = payload["messages"][3:-1]
        assert len(tool_results) == MAX_TOOL_CALLS
        assert all(
            json.loads(result["content"])["status"] == "unavailable" for result in tool_results
        )
        return final_reply("Сейчас данные недоступны.")

    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url), transport=httpx.MockTransport(respond)
    ) as client:
        agent = ToolCallingAgent(OpenRouterClient(client, settings), execute)
        assert (await agent.generate("system", "question")).message == "Сейчас данные недоступны."

    assert len(rounds) == 2
    assert execute.await_count == MAX_TOOL_CALLS


async def test_repeated_requests_for_tools_end_after_max_rounds(settings):
    execute = AsyncMock(return_value={"status": "not_found", "data": []})
    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url),
        transport=httpx.MockTransport(lambda _: reply(tool_calls=[tool_call("get_data_scope")])),
    ) as client:
        agent = ToolCallingAgent(OpenRouterClient(client, settings), execute)
        answer = await agent.generate("system", "question")

    assert "Не удалось завершить" in answer.message
    assert execute.await_count == MAX_TOOL_ROUNDS


async def test_passing_score_requires_lookup_and_retries_invalid_final_answer(settings):
    source = "https://uust.ru/admission/scores/"
    arguments = {
        "metric": "passing_scores",
        "codes": ["01.03.02"],
        "branch_id": "ufa",
        "year": 2026,
        "funding": "budget",
        "form": "очная",
    }
    execute = AsyncMock(
        return_value={"status": "ok", "data": [{"passing_score": 231, "sources": [source]}]}
    )
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            assert payload["tool_choice"] == {
                "type": "function",
                "function": {"name": "get_admission_options"},
            }
            return reply(tool_calls=[tool_call("get_admission_options", **arguments)])
        if len(requests) == 2:
            return reply(content="Проходной балл — 231.")
        assert payload["tool_choice"] == "none"
        if len(requests) == 3:
            return reply(content='{"message":')

        assert any(msg["role"] == "tool" and "231" in msg["content"] for msg in payload["messages"])
        content = json.dumps({"message": "Проходной балл — 231.", "source": [source]})
        return reply(content=f"```json\n{content}\n```")

    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url),
        transport=httpx.MockTransport(respond),
    ) as client:
        agent = ToolCallingAgent(OpenRouterClient(client, settings), execute)
        answer = await agent.generate(
            "system", "Какой был проходной балл на очный бюджет по 01.03.02 в Уфе в 2026 году?"
        )

    assert len(requests) == 4
    assert answer.message == "Проходной балл — 231."
    assert answer.source == [source]
    execute.assert_awaited_once_with("get_admission_options", arguments)


async def test_agent_uses_text_draft_when_model_returns_reasoning_instead_of_json(settings):
    source = "https://uust.ru/programs/"
    execute = AsyncMock(return_value={"status": "ok", "data": [{"sources": [source]}]})
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            return reply(tool_calls=[tool_call("get_admission_options", metric="programs")])
        if len(requests) == 2:
            assert "reasoning" not in payload
            return reply(content=f"Для начала попробуйте веб-разработку.\n\nИсточник: {source}")
        assert payload["reasoning"] == {"enabled": False}
        return reply(content="Thinking Process:\n1. Analyze the request.")

    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url),
        transport=httpx.MockTransport(respond),
    ) as client:
        agent = ToolCallingAgent(OpenRouterClient(client, settings), execute)
        answer = await agent.generate(
            "system",
            "Какие направления разработки можешь посоветовать?",
            conversation=ConversationContext(history_summary="Пользователь интересуется УУНиТ."),
        )

    assert len(requests) == 4
    assert answer.message == "Для начала попробуйте веб-разработку."
    assert answer.source == [source]
    execute.assert_awaited_once()


async def test_conversation_context_and_annotation_cross_queue_boundary(settings, request_message):
    request_message.message = "Уфа"
    request_message.conversation = ConversationContext(
        history_summary="Пользователь ищет, где подать заявление.",
        older_turns=[
            ConversationTurn(user_message="Я хочу подать заявление о материальной помощи.")
        ],
        recent_turns=[
            ConversationTurn(
                user_message="Куда подать документы?",
                assistant_message="В каком городе вы учитесь?",
            )
        ],
    )
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            assert "tools" not in payload
            context = json.loads(payload["messages"][1]["content"])
            assert "материальной помощи" in context["older_turns"][0]["user_message"]
            return reply(content="Пользователь подаёт заявление о материальной помощи.")
        if len(requests) == 2:
            assert "материальной помощи" in payload["messages"][1]["content"]
            assert payload["messages"][2:] == [
                {"role": "user", "content": "Куда подать документы?"},
                {"role": "assistant", "content": "В каком городе вы учитесь?"},
                {"role": "user", "content": "Уфа"},
            ]
            return reply(content="В Уфе обращайтесь в студенческий офис.")
        schema = payload["response_format"]["json_schema"]["schema"]
        assert "history_summary" in schema["required"]
        return reply(
            content=json.dumps(
                {
                    "message": "В Уфе обращайтесь в студенческий офис.",
                    "source": [],
                    "history_summary": "Пользователь подаёт заявление о материальной помощи в Уфе.",
                }
            )
        )

    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url),
        transport=httpx.MockTransport(respond),
    ) as client:
        service = AgentService(ToolCallingAgent(OpenRouterClient(client, settings), AsyncMock()))
        result = await service.process(request_message)

    assert len(requests) == 3
    payload = result.model_dump(mode="json", exclude_none=True)
    assert payload["history_summary"].endswith("в Уфе.")
    assert "history_summary" not in payload["blocks"][0]


async def test_agent_attaches_only_imported_campus_photos(settings, request_message):
    fake_tool = AsyncMock(
        return_value={
            "status": "ok",
            "data": [
                {
                    "id": "ishimbay-photo-001",
                    "photo_available": True,
                    "object_key": "campus/ishimbay-photo-001-test.jpg",
                    "minio_bucket": "images",
                    "content_type": "image/jpeg",
                },
                {"id": "unavailable-photo", "photo_available": False},
            ],
        }
    )

    def respond(request):
        payload = json.loads(request.content)
        if payload.get("tool_choice") == "none":
            return reply(
                content=json.dumps(
                    {
                        "message": "Вот архивное фото филиала.",
                        "source": [],
                        "photo_ids": [
                            "ishimbay-photo-001",
                            "ishimbay-photo-001",
                            "unavailable-photo",
                            "invented-photo",
                        ],
                    }
                )
            )
        if payload["messages"][-1]["role"] == "tool":
            assert "object_key" not in payload["messages"][-1]["content"]
            return reply(content="Вот архивное фото филиала.")
        return reply(tool_calls=[tool_call("list_photos", place_id="ishimbay-main")])

    async with httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url),
        transport=httpx.MockTransport(respond),
    ) as client:
        service = AgentService(ToolCallingAgent(OpenRouterClient(client, settings), fake_tool))
        result = await service.process(request_message)

    blocks = result.model_dump(mode="json")["blocks"]
    assert blocks[-1]["type"] == "attachments"
    assert len(blocks[-1]["attachments"]) == 1
    assert blocks[-1]["attachments"][0]["object_key"] == "campus/ishimbay-photo-001-test.jpg"
