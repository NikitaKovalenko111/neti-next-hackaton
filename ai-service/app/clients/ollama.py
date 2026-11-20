import httpx

from app.config import Settings


class OllamaClient:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = await self.client.post(
            "/api/chat",
            json={
                "model": self.settings.ollama_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "think": False,
                "options": {
                    "num_predict": self.settings.ollama_num_predict,
                    "num_ctx": self.settings.ollama_num_ctx,
                },
            },
        )
        response.raise_for_status()
        payload = response.json()

        content = payload.get("message", {}).get("content")
        if payload.get("done") is not True or not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned an incomplete or empty answer")

        return content.strip()

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
