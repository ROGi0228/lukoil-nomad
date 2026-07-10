from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "staging", "production"] = "local"
    debug: bool = True

    bot_token: str
    bot_use_webhook: bool = False
    webhook_url: str = ""
    webhook_secret: str = ""
    # NoDecode: без него pydantic-settings пытается JSON-распарсить значение
    # env-переменной для list[int] ДО field_validator и падает на "123,456"
    admin_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    news_channel_url: str = ""

    database_url: str

    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_region: str = "us-east-1"

    ocr_primary_provider: Literal["google_vision", "yandex_vision"] = "google_vision"
    google_application_credentials: str = ""
    yandex_vision_api_key: str = ""
    yandex_vision_folder_id: str = ""

    sentry_dsn: str = ""
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(v.strip()) for v in value.split(",") if v.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
