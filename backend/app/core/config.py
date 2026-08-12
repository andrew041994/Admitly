from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    app_name: str = Field(default="Admitly API", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    env: str = Field(default="development", alias="ENV")
    database_url: str = Field(alias="DATABASE_URL")

    cors_allowed_origins: str = Field(
        default=(
            "https://admitly.onrender.com,"
            "https://www.admitlyevents.com,"
            "https://admitlyevents.com"
        ),
        alias="CORS_ALLOWED_ORIGINS",
    )
    cors_development_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_DEVELOPMENT_ORIGINS",
    )

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

    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    rate_limit_key_prefix: str = Field(default="admitly:rate-limit", alias="RATE_LIMIT_KEY_PREFIX")
    rate_limit_login_count: int = Field(default=10, alias="RATE_LIMIT_LOGIN_COUNT")
    rate_limit_login_window_seconds: int = Field(default=300, alias="RATE_LIMIT_LOGIN_WINDOW_SECONDS")
    rate_limit_signup_count: int = Field(default=5, alias="RATE_LIMIT_SIGNUP_COUNT")
    rate_limit_signup_window_seconds: int = Field(default=3600, alias="RATE_LIMIT_SIGNUP_WINDOW_SECONDS")
    rate_limit_password_reset_count: int = Field(default=3, alias="RATE_LIMIT_PASSWORD_RESET_COUNT")
    rate_limit_password_reset_window_seconds: int = Field(default=900, alias="RATE_LIMIT_PASSWORD_RESET_WINDOW_SECONDS")

    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")
    sentry_release: str | None = Field(default=None, alias="SENTRY_RELEASE")
    render_git_commit: str | None = Field(default=None, alias="RENDER_GIT_COMMIT")
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0, alias="SENTRY_TRACES_SAMPLE_RATE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    email_notifications_enabled: bool = Field(default=False, alias="EMAIL_NOTIFICATIONS_ENABLED")
    email_provider: str = Field(default="noop", alias="EMAIL_PROVIDER")
    email_from_address: str | None = Field(default=None, alias="EMAIL_FROM_ADDRESS")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    sendgrid_api_key: str | None = Field(default=None, alias="SENDGRID_API_KEY")
    frontend_base_url: str = Field(default="https://admitly.app", alias="FRONTEND_BASE_URL")
    app_deep_link_base_url: str = Field(default="admitly://", alias="APP_DEEP_LINK_BASE_URL")

    push_notifications_enabled: bool = Field(default=False, alias="PUSH_NOTIFICATIONS_ENABLED")
    push_provider: str = Field(default="noop", alias="PUSH_PROVIDER")
    rate_limit_push_registration_count: int = Field(default=10, alias="RATE_LIMIT_PUSH_REGISTRATION_COUNT")
    rate_limit_push_registration_window_seconds: int = Field(default=300, alias="RATE_LIMIT_PUSH_REGISTRATION_WINDOW_SECONDS")
    rate_limit_event_cover_upload_count: int = Field(default=10, alias="RATE_LIMIT_EVENT_COVER_UPLOAD_COUNT")
    rate_limit_event_cover_upload_window_seconds: int = Field(default=300, alias="RATE_LIMIT_EVENT_COVER_UPLOAD_WINDOW_SECONDS")

    ticket_public_base_url: str = Field(default="https://admitly.app", alias="TICKET_PUBLIC_BASE_URL")

    aws_access_key_id: str | None = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")
    aws_region: str | None = Field(default=None, alias="AWS_REGION")
    s3_event_bucket: str | None = Field(default=None, alias="S3_EVENT_BUCKET")
    s3_event_prefix: str = Field(default="event-covers/", alias="S3_EVENT_PREFIX")
    s3_public_base_url: str | None = Field(default=None, alias="S3_PUBLIC_BASE_URL")



    jwt_secret: str = Field(default="dev-change-me", alias="JWT_SECRET")
    jwt_access_token_exp_minutes: int = Field(default=15, alias="JWT_ACCESS_TOKEN_EXP_MINUTES")
    jwt_refresh_token_exp_days: int = Field(default=30, alias="JWT_REFRESH_TOKEN_EXP_DAYS")
    verification_token_exp_hours: int = Field(default=24, alias="VERIFICATION_TOKEN_EXP_HOURS")
    rate_limit_verification_resend_count: int = Field(default=3, alias="RATE_LIMIT_VERIFICATION_RESEND_COUNT")
    rate_limit_verification_resend_window_seconds: int = Field(default=900, alias="RATE_LIMIT_VERIFICATION_RESEND_WINDOW_SECONDS")
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

    @property
    def is_production(self) -> bool:
        return self.env.strip().lower() in {"prod", "production"}

    @staticmethod
    def _parse_origins(value: str) -> list[str]:
        return list(dict.fromkeys(origin.strip() for origin in value.split(",") if origin.strip()))

    @property
    def allowed_cors_origins(self) -> list[str]:
        origins = self._parse_origins(self.cors_allowed_origins)
        if not self.is_production:
            origins.extend(self._parse_origins(self.cors_development_origins))
        return list(dict.fromkeys(origins))

    @property
    def resolved_sentry_release(self) -> str:
        explicit = (self.sentry_release or "").strip()
        if explicit:
            return explicit
        commit = (self.render_git_commit or "").strip()
        if commit:
            return f"admitly-backend@{commit}"
        return f"admitly-backend@{self.app_version.strip()}"

    @staticmethod
    def _valid_http_url(value: str, *, require_https: bool) -> bool:
        parsed = urlsplit(value)
        if parsed.scheme not in ({"https"} if require_https else {"http", "https"}):
            return False
        return bool(
            parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
        )

    @staticmethod
    def _is_local_hostname(hostname: str | None) -> bool:
        return (hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if not self.is_production:
            return self

        errors: list[str] = []
        if self.enable_dev_test_checkout:
            errors.append("ENABLE_DEV_TEST_CHECKOUT must be false")
        if not self.redis_url:
            errors.append("REDIS_URL is required for shared rate limiting")
        else:
            redis = urlsplit(self.redis_url)
            if redis.scheme not in {"redis", "rediss"} or not redis.hostname:
                errors.append("REDIS_URL must be a valid redis:// or rediss:// URL")
            elif self._is_local_hostname(redis.hostname):
                errors.append("REDIS_URL must point to a shared non-local Redis service")
        if self.jwt_secret == "dev-change-me" or len(self.jwt_secret) < 32:
            errors.append("JWT_SECRET must be non-default and at least 32 characters")
        if self.mmg_enabled and self.mmg_provider_mode != "live":
            errors.append("MMG_PROVIDER_MODE must be live when MMG is enabled")
        if self.mmg_enabled and self.mmg_provider_mode == "live":
            required_mmg = {
                "MMG_BASE_URL": self.mmg_base_url,
                "MMG_MERCHANT_ID": self.mmg_merchant_id,
                "MMG_API_KEY": self.mmg_api_key,
                "MMG_API_SECRET": self.mmg_api_secret,
                "MMG_CALLBACK_URL": self.mmg_callback_url,
            }
            missing_mmg = sorted(name for name, value in required_mmg.items() if not value)
            if missing_mmg:
                errors.append("enabled live MMG is missing: " + ", ".join(missing_mmg))

        configured_origins = self._parse_origins(self.cors_allowed_origins)
        if not configured_origins:
            errors.append("CORS_ALLOWED_ORIGINS must contain at least one production origin")
        for origin in configured_origins:
            parsed_origin = urlsplit(origin)
            if (
                not self._valid_http_url(origin, require_https=True)
                or self._is_local_hostname(parsed_origin.hostname)
                or parsed_origin.path not in {"", "/"}
                or origin.endswith("/")
                or "*" in origin
            ):
                errors.append(f"CORS_ALLOWED_ORIGINS contains unsafe production origin: {origin}")

        public_urls = {
            "FRONTEND_BASE_URL": self.frontend_base_url,
            "TICKET_PUBLIC_BASE_URL": self.ticket_public_base_url,
        }
        for name, value in public_urls.items():
            if not self._valid_http_url(value, require_https=True):
                errors.append(f"{name} must be a valid HTTPS URL in production")

        for name, value in {
            "MMG_BASE_URL": self.mmg_base_url,
            "MMG_CALLBACK_URL": self.mmg_callback_url,
            "MMG_RETURN_URL_SUCCESS": self.mmg_return_url_success,
            "MMG_RETURN_URL_CANCEL": self.mmg_return_url_cancel,
        }.items():
            if value and not self._valid_http_url(value, require_https=True):
                errors.append(f"{name} must be a valid HTTPS URL when configured in production")

        if self.app_deep_link_base_url != "admitly://":
            errors.append("APP_DEEP_LINK_BASE_URL must use the registered admitly:// scheme")
        if self.log_level.strip().upper() not in {"INFO", "WARNING", "ERROR", "CRITICAL"}:
            errors.append("LOG_LEVEL must be INFO, WARNING, ERROR, or CRITICAL in production")

        rate_limit_values = {
            name: value
            for name, value in self.__dict__.items()
            if name.startswith("rate_limit_") and name != "rate_limit_key_prefix"
        }
        if any(not isinstance(value, int) or value <= 0 for value in rate_limit_values.values()):
            errors.append("all production rate-limit counts and windows must be positive integers")
        if errors:
            raise ValueError("Unsafe production configuration: " + "; ".join(errors))
        return self

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
