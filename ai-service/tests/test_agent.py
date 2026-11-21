import json
from unittest.mock import AsyncMock
from uuid import uuid4

from app.models import Attachment, DialogueTurn, UserAnswer
from app.services.agent import AgentService


async def test_response_matches_backend_blocks_contract(request_message):
    model = AsyncMock()
    model.generate.return_value = "Уточните, пожалуйста, название корпуса."

    response = await AgentService(model).process(request_message)

    assert response.model_dump(mode="json", exclude_none=True) == {
        "request_message_id": str(request_message.message_id),
        "blocks": [
            {
                "type": "text",
                "message": "Уточните, пожалуйста, название корпуса.",
                "source": [],
                "audience": "unknown",
            }
        ],
    }
    prompt = model.generate.call_args.args[0]
    assert "используй инструменты" in prompt
    assert "обращайся на «вы»" in prompt
    assert "уточняющий вопрос" in prompt
    assert "Если информации достаточно, сразу дай ответ" in prompt


async def test_attachments_are_metadata_only(request_message):
    request_message.message = ""
    request_message.attachments = [
        Attachment(
            attachment_id=uuid4(),
            bucket="images",
            object_key="image.png",
            filename="photo.png",
            content_type="image/png",
        )
    ]
    model = AsyncMock()
    model.generate.return_value = "Опишите, пожалуйста, вопрос текстом."

    await AgentService(model).process(request_message)

    assert "photo.png" in model.generate.call_args.args[1]
    assert "доступны только имена" in model.generate.call_args.args[1]


async def test_redelivery_uses_cached_answer(request_message):
    model = AsyncMock()
    model.generate.return_value = "Answer"
    service = AgentService(model)

    first = await service.process(request_message)
    second = await service.process(request_message)

    assert first == second
    model.generate.assert_awaited_once()


async def test_cache_is_bounded(request_message):
    model = AsyncMock()
    model.generate.return_value = "Answer"
    service = AgentService(model, cache_size=1)

    await service.process(request_message)
    other = request_message.model_copy(update={"message_id": uuid4()})
    await service.process(other)

    assert len(service.responses) == 1
    assert request_message.message_id not in service.responses


async def test_previous_user_turn_informs_audience_and_map(request_message):
    request_message.history = [DialogueTurn(role="user", message="Я учусь на первом курсе.")]
    request_message.message = "Как добраться до главного корпуса?"
    model = AsyncMock()
    model.generate.return_value = UserAnswer(
        message="Вот главный корпус.",
        source=["https://uust.ru/page-contacts/"],
        audience="student",
        map_point="uust_main_building",
    )

    response = await AgentService(model).process(request_message)

    system, prompt = model.generate.call_args.args
    assert "Уфимского университета" in system
    assert json.loads(prompt)["предыдущие реплики"] == [
        {"role": "user", "message": "Я учусь на первом курсе."}
    ]
    assert response.blocks[0].source == ["https://uust.ru/page-contacts/"]
    assert response.blocks[0].audience == "student"
    assert response.blocks[1].type == "map"
    assert response.blocks[1].address == "Уфа, ул. Заки Валиди, 32"


async def test_non_navigation_question_does_not_get_a_map(request_message):
    request_message.message = "Какие документы нужны для поступления?"
    model = AsyncMock()
    model.generate.return_value = UserAnswer(
        message="Посмотрите правила приёма.", audience="applicant", map_point="uust_main_building"
    )

    response = await AgentService(model).process(request_message)

    assert len(response.blocks) == 1
    assert response.blocks[0].audience == "applicant"


async def test_explicit_main_building_route_gets_map_even_if_model_omits_it(request_message):
    request_message.message = "Я студент. Как добраться до главного корпуса УУНиТ?"
    model = AsyncMock()
    model.generate.return_value = UserAnswer(message="Главный корпус на Заки Валиди, 32.")

    response = await AgentService(model).process(request_message)

    assert response.blocks[0].source == ["https://uust.ru/page-contacts/"]
    assert response.blocks[1].type == "map"


async def test_explicit_route_to_branch_does_not_get_ufa_map(request_message):
    request_message.message = "Как добраться до главного корпуса УУНиТ в Бирске?"
    model = AsyncMock()
    model.generate.return_value = UserAnswer(message="Какой корпус вас интересует?")

    response = await AgentService(model).process(request_message)

    assert len(response.blocks) == 1
