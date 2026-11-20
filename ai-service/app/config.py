from pydantic import Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rabbitmq_url: SecretStr = SecretStr("amqp://guest:guest@localhost:5672/")
    rabbitmq_queue: str = Field(default="agent_requests", min_length=1)
    rabbitmq_response_queue: str = Field(default="agent_responses", min_length=1)

    ollama_base_url: HttpUrl = HttpUrl("http://localhost:11434")
    ollama_model: str = Field(default="qwen3:4b", min_length=1)
    ollama_timeout_seconds: float = Field(default=180, gt=0)
    ollama_num_predict: int = Field(default=512, gt=0)
    ollama_num_ctx: int = Field(default=4096, gt=0)

    retry_delay_seconds: float = Field(default=5, gt=0)
    response_cache_size: int = Field(default=128, ge=1)

    @model_validator(mode="after")
    def distinct_queues(self) -> "Settings":
        if self.rabbitmq_queue == self.rabbitmq_response_queue:
            raise ValueError("Request and response queues must have different names")

        return self
