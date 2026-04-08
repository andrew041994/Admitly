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
    enable_dev_test_checkout: bool = Field(default=False, alias="ENABLE_DEV_TEST_CHECKOUT")

    email_notifications_enabled: bool = Field(default=False, alias="EMAIL_NOTIFICATIONS_ENABLED")
    email_provider: str = Field(default="noop", alias="EMAIL_PROVIDER")
    email_from_address: str | None = Field(default=None, alias="EMAIL_FROM_ADDRESS")

    push_notifications_enabled: bool = Field(default=False, alias="PUSH_NOTIFICATIONS_ENABLED")
    push_provider: str = Field(default="noop", alias="PUSH_PROVIDER")

    ticket_public_base_url: str = Field(default="https://admitly.app", alias="TICKET_PUBLIC_BASE_URL")



    jwt_secret: str = Field(default="dev-change-me", alias="JWT_SECRET")
    jwt_access_token_exp_minutes: int = Field(default=15, alias="JWT_ACCESS_TOKEN_EXP_MINUTES")
    jwt_refresh_token_exp_days: int = Field(default=30, alias="JWT_REFRESH_TOKEN_EXP_DAYS")
    verification_token_exp_hours: int = Field(default=24, alias="VERIFICATION_TOKEN_EXP_HOURS")
    password_reset_token_exp_minutes: int = Field(default=60, alias="PASSWORD_RESET_TOKEN_EXP_MINUTES")
    rate_limit_order_create_count: int = Field(default=8, alias="RATE_LIMIT_ORDER_CREATE_COUNT")
    rate_limit_order_create_window_seconds: int = Field(default=60, alias="RATE_LIMIT_ORDER_CREATE_WINDOW_SECONDS")
    rate_limit_payment_initiate_count: int = Field(default=6, alias="RATE_LIMIT_PAYMENT_INITIATE_COUNT")
    rate_limit_payment_initiate_window_seconds: int = Field(default=60, alias="RATE_LIMIT_PAYMENT_INITIATE_WINDOW_SECONDS")
    rate_limit_payment_submit_count: int = Field(default=6, alias="RATE_LIMIT_PAYMENT_SUBMIT_COUNT")
    rate_limit_payment_submit_window_seconds: int = Field(default=300, alias="RATE_LIMIT_PAYMENT_SUBMIT_WINDOW_SECONDS")
    rate_limit_transfer_invite_count: int = Field(default=10, alias="RATE_LIMIT_TRANSFER_INVITE_COUNT")
    rate_limit_transfer_invite_window_seconds: int = Field(default=300, alias="RATE_LIMIT_TRANSFER_INVITE_WINDOW_SECONDS")
    rate_limit_admin_action_count: int = Field(default=20, alias="RATE_LIMIT_ADMIN_ACTION_COUNT")
    rate_limit_admin_action_window_seconds: int = Field(default=60, alias="RATE_LIMIT_ADMIN_ACTION_WINDOW_SECONDS")
    rate_limit_callback_count: int = Field(default=120, alias="RATE_LIMIT_CALLBACK_COUNT")
    rate_limit_callback_window_seconds: int = Field(default=60, alias="RATE_LIMIT_CALLBACK_WINDOW_SECONDS")

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
