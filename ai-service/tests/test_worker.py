from types import SimpleNamespace
from unittest.mock import AsyncMock

import aio_pika
import pytest

from app.models import AgentResponse
from app.services.agent import AgentService
from app.transport.rabbitmq import RabbitWorker


def incoming(request, reply_to=None):
    return SimpleNamespace(
        body=request.model_dump_json().encode(),
        message_id=str(request.message_id),
        reply_to=reply_to,
        ack=AsyncMock(),
        nack=AsyncMock(),
        reject=AsyncMock(),
    )


async def test_ack_follows_confirmed_response_publication(settings, request_message):
    events = []
    model = AsyncMock()
    model.generate.return_value = "Answer"
    worker = RabbitWorker(settings, AgentService(model))
    message = incoming(request_message, reply_to="custom_responses")

    async def publish(response, **kwargs):
        parsed = AgentResponse.model_validate_json(response.body)
        assert parsed.request_message_id == request_message.message_id
        assert response.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
        assert response.correlation_id == str(request_message.message_id)
        assert kwargs["routing_key"] == "custom_responses"
        assert kwargs["mandatory"] is True
        message.ack.assert_not_awaited()
        events.append("publish_confirmed")

    async def ack():
        events.append("ack")

    message.ack.side_effect = ack
    worker.channel = SimpleNamespace(default_exchange=SimpleNamespace(publish=publish))

    await worker.handle(message)

    assert events == ["publish_confirmed", "ack"]
    message.nack.assert_not_awaited()


async def test_publish_failure_requeues_and_reuses_answer(settings, request_message):
    model = AsyncMock()
    model.generate.return_value = "Answer"
    worker = RabbitWorker(settings, AgentService(model))
    publish = AsyncMock(side_effect=[RuntimeError("broker disconnected"), None])
    worker.channel = SimpleNamespace(default_exchange=SimpleNamespace(publish=publish))
    first = incoming(request_message)

    await worker.handle(first)

    first.ack.assert_not_awaited()
    first.nack.assert_awaited_once_with(requeue=True)

    redelivery = incoming(request_message)
    await worker.handle(redelivery)

    redelivery.ack.assert_awaited_once()
    model.generate.assert_awaited_once()
    assert publish.call_args.kwargs["routing_key"] == "agent_responses"


async def test_model_failure_requeues_without_publishing(settings, request_message):
    model = AsyncMock()
    model.generate.side_effect = RuntimeError("OpenRouter unavailable")
    worker = RabbitWorker(settings, AgentService(model))
    publish = AsyncMock()
    worker.channel = SimpleNamespace(default_exchange=SimpleNamespace(publish=publish))
    message = incoming(request_message)

    await worker.handle(message)

    publish.assert_not_awaited()
    message.ack.assert_not_awaited()
    message.nack.assert_awaited_once_with(requeue=True)


@pytest.mark.parametrize("body", [b"not json", b"{}", b'{"message": "hello"}'])
async def test_invalid_request_is_rejected(settings, body):
    model = AsyncMock()
    worker = RabbitWorker(settings, AgentService(model))
    message = SimpleNamespace(body=body, message_id="invalid", reject=AsyncMock())

    await worker.handle(message)

    message.reject.assert_awaited_once_with(requeue=False)
    model.generate.assert_not_awaited()
