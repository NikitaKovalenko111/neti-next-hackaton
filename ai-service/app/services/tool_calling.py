import json
import logging
from collections.abc import Awaitable, Callable

import asyncpg
import httpx

from app.clients.ollama import OllamaClient, answer_text
from app.config import Settings
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
                    embedding_model=self.settings.ollama_embedding_model,
                )
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError):
            logger.warning("PostgreSQL unavailable for tool %s", name, exc_info=True)
            return {"status": "unavailable", "reason": "database_error"}


class ToolCallingAgent:
    def __init__(
        self, model: OllamaClient, execute_tool: Callable[[str, dict], Awaitable[dict]]
    ) -> None:
        self.model = model
        self.execute_tool = execute_tool
        self.tools = tool_definitions()

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        remaining = MAX_TOOL_CALLS

        for _ in range(MAX_TOOL_ROUNDS):
            message = await self.model.chat(messages, self.tools)
            calls = message.get("tool_calls") or []
            if not calls:
                return answer_text(message)
            if not isinstance(calls, list):
                raise ValueError("Ollama returned invalid tool calls")

            assistant = {**message, "role": "assistant", "tool_calls": calls[:remaining]}
            messages.append(assistant)
            for call in assistant["tool_calls"]:
                messages.append(await self.tool_message(call))

            remaining -= len(assistant["tool_calls"])
            if remaining == 0:
                break

        messages[0] = {
            "role": "system",
            "content": (
                f"{system_prompt}\nЗаверши ответ по уже полученным данным. "
                "Если их мало, объясни, чего не хватает."
            ),
        }
        final = await self.model.chat(messages)
        content = final.get("content")
        if final.get("tool_calls") or not isinstance(content, str) or not content.strip():
            return "Поиск по базе не удалось завершить. Уточните вопрос и попробуйте ещё раз."
        return answer_text(final)

    async def tool_message(self, call: dict) -> dict:
        function = call.get("function") if isinstance(call, dict) else None
        name = function.get("name") if isinstance(function, dict) else None
        if not isinstance(name, str) or not name:
            raise ValueError("Ollama returned a tool call without a name")

        arguments = function.get("arguments", {})
        if isinstance(arguments, dict):
            result = await self.execute_tool(name, arguments)
        else:
            # Native Ollama tool calls use a JSON object for arguments.
            function["arguments"] = {}
            result = {"status": "invalid_arguments", "errors": [{"field": "", "type": "dict_type"}]}

        return {
            "role": "tool",
            "tool_name": name,
            "content": json.dumps(result, ensure_ascii=False),
        }
