import httpx

from app.config import Settings


class OllamaClient:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        request = {
            "model": self.settings.ollama_model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "num_predict": self.settings.ollama_num_predict,
                "num_ctx": self.settings.ollama_num_ctx,
            },
        }
        if tools:
            request["tools"] = tools

        response = await self.client.post("/api/chat", json=request)
        response.raise_for_status()
        payload = response.json()
        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, dict) or payload.get("done") is not True:
            raise ValueError("Ollama returned an incomplete or empty answer")

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
            response = await self.client.get("/api/tags", timeout=3)
            response.raise_for_status()
            return any(
                model.get("name") == self.settings.ollama_model
                for model in response.json()["models"]
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            return False


def answer_text(message: dict) -> str:
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Ollama returned an incomplete or empty answer")
    return content.strip()
