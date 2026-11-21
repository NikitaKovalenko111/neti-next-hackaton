from pydantic import Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rabbitmq_url: SecretStr = SecretStr("amqp://guest:guest@localhost:5672/")
    rabbitmq_queue: str = Field(default="agent_requests", min_length=1)
    rabbitmq_response_queue: str = Field(default="agent_responses", min_length=1)

    rag_postgres_host: str = "localhost"
    rag_postgres_port: int = Field(default=5433, ge=1, le=65535)
    rag_postgres_db: str = "university"
    rag_postgres_user: str = "rag_app"
    rag_postgres_password: SecretStr = SecretStr("rag_app")

    minio_endpoint: str = "localhost:9000"
    minio_access_key: SecretStr = SecretStr("minioadmin")
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_bucket: str = "images"
    minio_region: str = "us-east-1"
    minio_secure: bool = False

    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_base_url: HttpUrl = HttpUrl("https://openrouter.ai/api/v1/")
    openrouter_model: str = Field(default="qwen/qwen3-30b-a3b-instruct-2507", min_length=1)
    openrouter_embedding_model: str = Field(default="baai/bge-m3", min_length=1)
    openrouter_timeout_seconds: float = Field(default=180, gt=0)
    openrouter_max_tokens: int = Field(default=1024, gt=0)

    retry_delay_seconds: float = Field(default=5, gt=0)
    response_cache_size: int = Field(default=128, ge=1)

    @model_validator(mode="after")
    def distinct_queues(self) -> "Settings":
        if self.rabbitmq_queue == self.rabbitmq_response_queue:
            raise ValueError("Request and response queues must have different names")

        return self
