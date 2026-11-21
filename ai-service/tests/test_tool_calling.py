import json
from unittest.mock import AsyncMock, call

import httpx

from app.clients.ollama import OllamaClient
from app.services.agent import AgentService
from app.services.tool_calling import MAX_TOOL_CALLS, MAX_TOOL_ROUNDS, ToolCallingAgent


def tool_call(name, **arguments):
    return {"type": "function", "function": {"name": name, "arguments": arguments}}


def reply(**message):
    return httpx.Response(200, json={"message": {"role": "assistant", **message}, "done": True})


async def test_agent_returns_answer_after_two_tool_rounds(settings, request_message):
    calls = []
    execute = AsyncMock(
        side_effect=[
            {"status": "ok", "data": [{"id": "death_of_close_relative"}]},
            {"status": "ok", "data": {"deadline_months": 6}},
            {"status": "not_found", "data": []},
        ]
    )

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert request.url.path == "/api/chat"
        assert len(payload["tools"]) == 12
        if len(calls) == 1:
            return reply(
                content="",
                tool_calls=[tool_call("search_support_grounds", query=request_message.message)],
            )
        if len(calls) == 2:
            assert payload["messages"][-2]["role"] == "assistant"
            assert payload["messages"][-1]["tool_name"] == "search_support_grounds"
            data = json.loads(payload["messages"][-1]["content"])
            assert data["data"][0]["id"] == "death_of_close_relative"
            return reply(
                content="",
                tool_calls=[
                    tool_call("get_support_ground", ground_id="death_of_close_relative"),
                    tool_call("list_support_channels", branch_id="ufa"),
                ],
            )
        results = payload["messages"][-2:]
        assert [result["tool_name"] for result in results] == [
            "get_support_ground",
            "list_support_channels",
        ]
        assert json.loads(results[0]["content"])["data"]["deadline_months"] == 6
        assert json.loads(results[1]["content"])["status"] == "not_found"
        return reply(content="Срок по этому основанию — 6 месяцев.")

    async with httpx.AsyncClient(
        base_url=str(settings.ollama_base_url),
        transport=httpx.MockTransport(respond),
    ) as client:
        agent = AgentService(ToolCallingAgent(OllamaClient(client, settings), execute))
        response = await agent.process(request_message)
        assert response.blocks[0].message == "Срок по этому основанию — 6 месяцев."
        assert await agent.process(request_message) == response

    assert len(calls) == 3
    assert execute.await_args_list == [
        call("search_support_grounds", {"query": request_message.message}),
        call("get_support_ground", {"ground_id": "death_of_close_relative"}),
        call("list_support_channels", {"branch_id": "ufa"}),
    ]


async def test_model_can_answer_without_querying_postgres(settings):
    execute = AsyncMock()
    async with httpx.AsyncClient(
        base_url=str(settings.ollama_base_url),
        transport=httpx.MockTransport(lambda _: reply(content="Здравствуйте!")),
    ) as client:
        agent = ToolCallingAgent(OllamaClient(client, settings), execute)
        assert await agent.generate("system", "Здравствуйте") == "Здравствуйте!"
    execute.assert_not_awaited()


async def test_tool_budget_limits_calls_in_one_model_response(settings):
    rounds = []
    execute = AsyncMock(return_value={"status": "unavailable", "reason": "database_error"})

    def respond(request):
        payload = json.loads(request.content)
        rounds.append(payload)
        if len(rounds) == 1:
            return reply(tool_calls=[tool_call("get_data_scope")] * (MAX_TOOL_CALLS + 1))
        assert "tools" not in payload
        assistant = payload["messages"][2]
        assert len(assistant["tool_calls"]) == MAX_TOOL_CALLS
        tool_results = payload["messages"][3:]
        assert len(tool_results) == MAX_TOOL_CALLS
        assert all(
            json.loads(result["content"])["status"] == "unavailable" for result in tool_results
        )
        return reply(content="Сейчас данные недоступны.")

    async with httpx.AsyncClient(
        base_url=str(settings.ollama_base_url), transport=httpx.MockTransport(respond)
    ) as client:
        agent = ToolCallingAgent(OllamaClient(client, settings), execute)
        assert await agent.generate("system", "question") == "Сейчас данные недоступны."

    assert len(rounds) == 2
    assert execute.await_count == MAX_TOOL_CALLS


async def test_repeated_requests_for_tools_end_after_max_rounds(settings):
    execute = AsyncMock(return_value={"status": "not_found", "data": []})
    async with httpx.AsyncClient(
        base_url=str(settings.ollama_base_url),
        transport=httpx.MockTransport(lambda _: reply(tool_calls=[tool_call("get_data_scope")])),
    ) as client:
        agent = ToolCallingAgent(OllamaClient(client, settings), execute)
        answer = await agent.generate("system", "question")

    assert "не удалось завершить" in answer
    assert execute.await_count == MAX_TOOL_ROUNDS
