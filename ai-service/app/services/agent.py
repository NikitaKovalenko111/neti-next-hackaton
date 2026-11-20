from collections import OrderedDict
from typing import Protocol
from uuid import UUID

from app.models import AgentRequest, AgentResponse, TextBlock

SYSTEM_PROMPT = """Ты — помощник по университету. Отвечай на языке пользователя.
Это прототип: у тебя нет базы знаний университета, RAG, поиска и других инструментов.
Не выдумывай расписание, номера аудиторий, контакты, правила и другие сведения конкретного
университета. Если вопрос требует таких данных, объясни ограничение и попроси уточнение.
Можешь отвечать на общие вопросы и помогать формулировать запросы.
У тебя нет доступа к содержимому прикреплённых файлов. Не утверждай, что изучил их.
"""


class TextModel(Protocol):
    async def generate(self, system_prompt: str, user_prompt: str) -> str: ...


class AgentService:
    def __init__(self, model: TextModel, cache_size: int = 128) -> None:
        self.model = model
        self.cache_size = cache_size
        self.responses: OrderedDict[UUID, AgentResponse] = OrderedDict()

    async def process(self, request: AgentRequest) -> AgentResponse:
        cached = self.responses.get(request.message_id)
        if cached is not None:
            self.responses.move_to_end(request.message_id)
            return cached

        prompt = request.message.strip()
        if request.attachments:
            filenames = ", ".join(attachment.filename for attachment in request.attachments)
            prompt += f"\n\nПрикреплённые файлы (доступны только имена): {filenames}"

        answer = await self.model.generate(SYSTEM_PROMPT, prompt)
        response = AgentResponse(
            request_message_id=request.message_id,
            blocks=[TextBlock(message=answer)],
        )

        self.responses[request.message_id] = response
        if len(self.responses) > self.cache_size:
            self.responses.popitem(last=False)

        return response
