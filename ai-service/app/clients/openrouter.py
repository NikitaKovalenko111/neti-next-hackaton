import httpx

from app.config import Settings


def openrouter_http(settings: Settings, *, require_key: bool = True) -> httpx.AsyncClient:
    key = settings.openrouter_api_key.get_secret_value().strip()
    if require_key and not key:
        raise ValueError("Set OPENROUTER_API_KEY before starting the AI service or indexer")

    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return httpx.AsyncClient(
        base_url=str(settings.openrouter_base_url),
        headers=headers,
        timeout=settings.openrouter_timeout_seconds,
    )


class OpenRouterClient:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        tool_choice: str | None = None,
    ) -> dict:
        request = {
            "model": self.settings.openrouter_model,
            "messages": messages,
            "stream": False,
            "max_tokens": self.settings.openrouter_max_tokens,
            "provider": {"require_parameters": True},
        }
        if tools:
            request["tools"] = tools
        if tool_choice is not None:
            request["tool_choice"] = tool_choice

        response = await self.client.post("chat/completions", json=request)
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("OpenRouter returned no completion choices")

        choice = choices[0]
        message = choice.get("message")
        if choice.get("error") or not isinstance(message, dict):
            raise ValueError("OpenRouter returned an incomplete answer")

        return message

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        message = await self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        return answer_text(message)

    async def is_ready(self) -> bool:
        try:
            response = await self.client.get("key", timeout=3)
            response.raise_for_status()
            return isinstance(response.json()["data"], dict)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            return False


def answer_text(message: dict) -> str:
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("OpenRouter returned an incomplete or empty answer")
    return content.strip()
