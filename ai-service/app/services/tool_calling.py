import json
import logging
from collections.abc import Awaitable, Callable

import asyncpg
import httpx

from app.clients.openrouter import OpenRouterClient, answer_text
from app.config import Settings
from app.models import UserAnswer
from app.services.answer import (
    ANSWER_FORMAT,
    collect_source_urls,
    model_tool_data,
    parse_user_answer,
)
from app.storage import connect_rag
from tools import call_tool, tool_definitions

MAX_TOOL_ROUNDS = 4
MAX_TOOL_CALLS = 8
logger = logging.getLogger(__name__)


class DatabaseTools:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client

    async def __call__(self, name: str, arguments: dict) -> dict:
        try:
            async with connect_rag(self.settings) as connection:
                return await call_tool(
                    connection,
                    name,
                    arguments,
                    embedding_client=self.client,
                    embedding_model=self.settings.openrouter_embedding_model,
                )
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError):
            logger.warning("PostgreSQL unavailable for tool %s", name, exc_info=True)
            return {"status": "unavailable", "reason": "database_error"}


class ToolCallingAgent:
    def __init__(
        self, model: OpenRouterClient, execute_tool: Callable[[str, dict], Awaitable[dict]]
    ) -> None:
        self.model = model
        self.execute_tool = execute_tool
        self.tools = tool_definitions()

    async def generate(self, system_prompt: str, user_prompt: str) -> UserAnswer:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        remaining = MAX_TOOL_CALLS
        allowed_sources: set[str] = set()

        for _ in range(MAX_TOOL_ROUNDS):
            message = await self.model.chat(messages, self.tools)
            calls = message.get("tool_calls") or []
            if not calls:
                messages.append({"role": "assistant", "content": answer_text(message)})
                break
            if not isinstance(calls, list):
                raise ValueError("OpenRouter returned invalid tool calls")

            assistant = {**message, "role": "assistant", "tool_calls": calls[:remaining]}
            messages.append(assistant)
            for call in assistant["tool_calls"]:
                messages.append(await self.tool_message(call, allowed_sources))

            remaining -= len(assistant["tool_calls"])
            if remaining == 0:
                break

        messages.append(
            {
                "role": "user",
                "content": (
                    "Заверши ответ по полученным данным. Если их мало, объясни, чего не хватает. "
                    "Верни объект JSON. В message пиши ответ без ссылок на источники и раздела "
                    "«Источники». В source верни массив ссылок из результатов инструментов, "
                    "на которые опирается ответ. При отсутствии источников верни пустой массив. "
                    "Укажи в audience профиль по репликам пользователя, а в map_point — ID точки "
                    "только для запроса о её адресе или маршруте. Без точки укажи none."
                ),
            }
        )
        final = await self.model.chat(
            messages, self.tools, tool_choice="none", response_format=ANSWER_FORMAT
        )
        if not final.get("tool_calls"):
            try:
                return parse_user_answer(answer_text(final), allowed_sources)
            except ValueError:
                logger.warning("OpenRouter returned an invalid final answer format")

        return UserAnswer(
            message="Поиск по базе не удалось завершить. Уточните вопрос и попробуйте ещё раз."
        )

    async def tool_message(self, call: dict, allowed_sources: set[str]) -> dict:
        function = call.get("function") if isinstance(call, dict) else None
        name = function.get("name") if isinstance(function, dict) else None
        if not isinstance(name, str) or not name:
            raise ValueError("OpenRouter returned a tool call without a name")

        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id:
            raise ValueError("OpenRouter returned a tool call without an ID")

        raw_arguments = function.get("arguments")
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else None
        except json.JSONDecodeError:
            arguments = None

        if isinstance(arguments, dict):
            result = await self.execute_tool(name, arguments)
        else:
            function["arguments"] = "{}"
            result = {"status": "invalid_arguments", "errors": [{"field": "", "type": "dict_type"}]}

        allowed_sources.update(collect_source_urls(result))
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(model_tool_data(result), ensure_ascii=False),
        }
