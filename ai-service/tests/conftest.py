from uuid import uuid4

import pytest

from app.config import Settings
from app.models import AgentRequest


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, retry_delay_seconds=0.001, openrouter_api_key="test-key")


@pytest.fixture
def request_message() -> AgentRequest:
    return AgentRequest(
        message_id=uuid4(), chat_id=uuid4(), user_id=uuid4(), message="Как найти аудиторию?"
    )
