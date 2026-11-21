import json
from unittest.mock import AsyncMock, call

import httpx

from app.clients.openrouter import OpenRouterClient
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


def final_reply(text, source=(), audience="unknown"):
    return reply(
        content=json.dumps(
            {"message": text, "source": list(source), "audience": audience, "map_point": "none"}
        )
        + "<|endoftext|>"
    )


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
        assert len(payload["tools"]) == 12
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
            assert payload["messages"][-2]["role"] == "tool"
            schema = payload["response_format"]["json_schema"]["schema"]
            assert schema["properties"]["audience"]["enum"] == ["unknown", "applicant", "student"]
            return final_reply(
                "Срок по этому основанию — 6 месяцев. (status: official_address_confirmed)"
                "\n\nИсточник: https://uust.ru/policy/",
                [
                    "https://uust.ru/policy/",
                    "https://uust.ru/policy/",
                    "https://example.com/invented",
                ],
                audience="student",
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
        assert response.blocks[0].audience == "student"
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


async def test_agent_retries_a_malformed_final_answer():
    model = AsyncMock()
    model.chat.side_effect = [
        {"content": "Draft text"},
        {"content": '{"message":'},
        final_reply("Здравствуйте!").json()["choices"][0]["message"],
    ]
    execute = AsyncMock()

    answer = await ToolCallingAgent(model, execute).generate("system", "Привет!")

    assert answer.message == "Здравствуйте!"
    assert model.chat.await_count == 3
    assert all(message["role"] != "assistant" for message in model.chat.await_args.args[0])
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
        assert len(payload["tools"]) == 12
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

    assert "не удалось завершить" in answer.message
    assert execute.await_count == MAX_TOOL_ROUNDS
