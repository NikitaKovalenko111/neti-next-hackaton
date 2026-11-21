from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Audience = Literal["unknown", "applicant", "student"]
MapPoint = Literal["none", "uust_main_building"]


class Attachment(BaseModel):
    attachment_id: UUID
    bucket: NonEmptyText
    object_key: NonEmptyText
    filename: NonEmptyText
    content_type: NonEmptyText


class DialogueTurn(BaseModel):
    role: Literal["user", "assistant"]
    message: NonEmptyText


class AgentRequest(BaseModel):
    message_id: UUID
    chat_id: UUID
    user_id: UUID
    message: str = ""
    attachments: list[Attachment] = Field(default_factory=list)
    history: list[DialogueTurn] = Field(default_factory=list, max_length=8)

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


class UserAnswer(BaseModel):
    message: NonEmptyText
    source: list[str] = Field(default_factory=list)
    audience: Audience = "unknown"
    map_point: MapPoint = "none"


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    message: NonEmptyText
    source: list[str] = Field(default_factory=list)
    audience: Audience = "unknown"


class MapBlock(BaseModel):
    type: Literal["map"] = "map"
    lat: float = Field(ge=-85, le=85, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    title: NonEmptyText
    address: NonEmptyText


class AgentResponse(BaseModel):
    request_message_id: UUID
    blocks: list[TextBlock | MapBlock] = Field(min_length=1)
