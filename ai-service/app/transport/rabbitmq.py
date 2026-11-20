import asyncio
import logging
from contextlib import suppress

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from aio_pika.exceptions import CONNECTION_EXCEPTIONS
from pydantic import ValidationError

from app.config import Settings
from app.models import AgentRequest
from app.services.agent import AgentService

logger = logging.getLogger(__name__)


class RabbitWorker:
    def __init__(self, settings: Settings, service: AgentService) -> None:
        self.settings = settings
        self.service = service
        self.connection = None
        self.channel = None
        self.requests = None
        self.task: asyncio.Task | None = None

    async def start(self) -> None:
        self.connection = await aio_pika.connect_robust(
            self.settings.rabbitmq_url.get_secret_value(), timeout=10
        )
        self.channel = await self.connection.channel(publisher_confirms=True, on_return_raises=True)
        await self.channel.set_qos(prefetch_count=1)

        self.requests = await self.channel.declare_queue(self.settings.rabbitmq_queue, durable=True)
        await self.channel.declare_queue(self.settings.rabbitmq_response_queue, durable=True)

        self.task = asyncio.create_task(self.run(), name="agent-requests")

    @property
    def is_ready(self) -> bool:
        return bool(
            self.connection
            and self.connection.connected.is_set()
            and self.channel
            and not self.channel.is_closed
            and self.task
            and not self.task.done()
        )

    async def close(self) -> None:
        try:
            if self.task is not None:
                self.task.cancel()
                with suppress(asyncio.CancelledError):
                    await self.task
        finally:
            if self.connection is not None:
                await self.connection.close()

    async def run(self) -> None:
        while True:
            try:
                async with self.requests.iterator() as messages:
                    async for message in messages:
                        await self.handle(message)
            except CONNECTION_EXCEPTIONS:
                logger.exception("RabbitMQ connection interrupted; awaiting restoration")
                await asyncio.sleep(self.settings.retry_delay_seconds)

    async def handle(self, message: AbstractIncomingMessage) -> None:
        try:
            request = AgentRequest.model_validate_json(message.body)
        except ValidationError:
            logger.warning("Rejecting invalid agent request: message_id=%s", message.message_id)
            await message.reject(requeue=False)
            return

        try:
            response = await self.service.process(request)
            await self.channel.default_exchange.publish(
                aio_pika.Message(
                    body=response.model_dump_json().encode(),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    message_id=str(request.message_id),
                    correlation_id=str(request.message_id),
                ),
                routing_key=message.reply_to or self.settings.rabbitmq_response_queue,
                mandatory=True,
                timeout=10,
            )
        except Exception:
            logger.exception("Processing failed; retrying request %s", request.message_id)
            await asyncio.sleep(self.settings.retry_delay_seconds)
            await message.nack(requeue=True)
            return

        # Acknowledge the request only after the response is confirmed by RabbitMQ.
        await message.ack()
