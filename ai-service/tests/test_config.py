import pytest
from pydantic import ValidationError

from app.config import Settings
from app.models import AgentRequest


def test_queues_must_be_distinct():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rabbitmq_queue="same", rabbitmq_response_queue="same")


def test_environment_names_match_backend(monkeypatch):
    monkeypatch.setenv("RABBITMQ_QUEUE", "tasks")
    monkeypatch.setenv("RABBITMQ_RESPONSE_QUEUE", "answers")
    settings = Settings(_env_file=None)

    assert settings.rabbitmq_queue == "tasks"
    assert settings.rabbitmq_response_queue == "answers"


def test_empty_question_is_invalid(request_message):
    payload = request_message.model_dump()
    payload["message"] = " "

    with pytest.raises(ValidationError):
        AgentRequest.model_validate(payload)
