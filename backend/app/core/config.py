from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Admitly API", alias="APP_NAME")
    env: str = Field(default="development", alias="ENV")
    database_url: str = Field(alias="DATABASE_URL")

    mmg_enabled: bool = Field(default=False, alias="MMG_ENABLED")
    mmg_provider_mode: str = Field(default="mock", alias="MMG_PROVIDER_MODE")
    mmg_base_url: str | None = Field(default=None, alias="MMG_BASE_URL")
    mmg_merchant_id: str | None = Field(default=None, alias="MMG_MERCHANT_ID")
    mmg_api_key: str | None = Field(default=None, alias="MMG_API_KEY")
    mmg_api_secret: str | None = Field(default=None, alias="MMG_API_SECRET")
    mmg_callback_url: str | None = Field(default=None, alias="MMG_CALLBACK_URL")
    mmg_return_url_success: str | None = Field(default=None, alias="MMG_RETURN_URL_SUCCESS")
    mmg_return_url_cancel: str | None = Field(default=None, alias="MMG_RETURN_URL_CANCEL")
    mmg_request_timeout_seconds: int = Field(default=10, alias="MMG_REQUEST_TIMEOUT_SECONDS")
    mmg_agent_auto_verify_enabled: bool = Field(default=True, alias="MMG_AGENT_AUTO_VERIFY_ENABLED")
    mmg_agent_manual_fallback_enabled: bool = Field(
        default=True, alias="MMG_AGENT_MANUAL_FALLBACK_ENABLED"
    )

    email_notifications_enabled: bool = Field(default=False, alias="EMAIL_NOTIFICATIONS_ENABLED")
    email_provider: str = Field(default="noop", alias="EMAIL_PROVIDER")
    email_from_address: str | None = Field(default=None, alias="EMAIL_FROM_ADDRESS")

    push_notifications_enabled: bool = Field(default=False, alias="PUSH_NOTIFICATIONS_ENABLED")
    push_provider: str = Field(default="noop", alias="PUSH_PROVIDER")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
