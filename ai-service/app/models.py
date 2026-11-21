from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Attachment(BaseModel):
    attachment_id: UUID
    bucket: NonEmptyText
    object_key: NonEmptyText
    filename: NonEmptyText
    content_type: NonEmptyText


class ConversationTurn(BaseModel):
    user_message: str
    assistant_message: str = ""


class ConversationContext(BaseModel):
    history_summary: str = ""
    recent_turns: list[ConversationTurn] = Field(default_factory=list, max_length=5)
    older_turns: list[ConversationTurn] = Field(default_factory=list)


class AgentRequest(BaseModel):
    message_id: UUID
    chat_id: UUID
    user_id: UUID
    message: str = ""
    attachments: list[Attachment] = Field(default_factory=list)
    conversation: ConversationContext | None = None

    @field_validator("message_id", "chat_id", "user_id")
    @classmethod
    def nonzero_id(cls, value: UUID) -> UUID:
        if value.int == 0:
            raise ValueError("ID must not be zero")

        return value

    @model_validator(mode="after")
    def has_content(self) -> "AgentRequest":
        if not self.message.strip() and not self.attachments:
            raise ValueError("Message or attachments are required")

        return self


class AnswerText(BaseModel):
    message: NonEmptyText
    source: list[str] = Field(default_factory=list)


class UserAnswer(AnswerText):
    history_summary: str = ""
    photo_ids: list[str] = Field(default_factory=list)
    photos: list[Attachment] = Field(default_factory=list)


class TextBlock(AnswerText):
    type: Literal["text"] = "text"


class AttachmentsBlock(BaseModel):
    type: Literal["attachments"] = "attachments"
    attachments: list[Attachment] = Field(min_length=1)


class AgentResponse(BaseModel):
    request_message_id: UUID
    blocks: list[TextBlock | AttachmentsBlock] = Field(min_length=1)
    history_summary: str | None = None
