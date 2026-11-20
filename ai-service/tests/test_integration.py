import asyncio
import json
import os
from uuid import uuid4

import aio_pika
import httpx
import pytest

from app.clients.ollama import OllamaClient
from app.config import Settings
from app.models import AgentResponse
from app.services.agent import AgentService
from app.transport.rabbitmq import RabbitWorker


@pytest.mark.integration
async def test_real_rabbitmq_request_response_roundtrip(request_message):
    broker_url = os.getenv("TEST_RABBITMQ_URL")
    if not broker_url:
        pytest.skip("set TEST_RABBITMQ_URL to run the real RabbitMQ integration test")

    suffix = uuid4().hex
    settings = Settings(
        _env_file=None,
        rabbitmq_url=broker_url,
        rabbitmq_queue=f"test.ai.requests.{suffix}",
        rabbitmq_response_queue=f"test.ai.responses.{suffix}",
    )
    generations = []

    def respond(request):
        generations.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "Test answer"}, "done": True})

    async with httpx.AsyncClient(
        base_url=str(settings.ollama_base_url), transport=httpx.MockTransport(respond)
    ) as client:
        service = AgentService(OllamaClient(client, settings))
        worker = RabbitWorker(settings, service)
        connection = await aio_pika.connect_robust(broker_url, timeout=5)

        async with connection:
            channel = await connection.channel(publisher_confirms=True)
            try:
                await worker.start()
                responses = await channel.declare_queue(
                    settings.rabbitmq_response_queue, durable=True
                )
                response_ids = []

                for _ in range(2):
                    await channel.default_exchange.publish(
                        aio_pika.Message(
                            body=request_message.model_dump_json().encode(),
                            content_type="application/json",
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            reply_to=settings.rabbitmq_response_queue,
                        ),
                        routing_key=settings.rabbitmq_queue,
                    )

                    async with asyncio.timeout(10), responses.iterator() as iterator:
                        message = await anext(iterator)
                        response = AgentResponse.model_validate_json(message.body)
                        assert response.request_message_id == request_message.message_id
                        assert response.blocks[0].message == "Test answer"
                        assert message.correlation_id == str(request_message.message_id)
                        assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
                        response_ids.append(response.request_message_id)
                        await message.ack()

                assert len(generations) == 1
                assert response_ids[0] == response_ids[1]

            finally:
                await worker.close()
                await channel.queue_delete(settings.rabbitmq_queue)
                await channel.queue_delete(settings.rabbitmq_response_queue)
