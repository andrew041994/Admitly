import pytest
from pydantic import ValidationError
from redis.exceptions import ConnectionError

from app.core.config import Settings
from app.services.rate_limit import (
    RateLimitExceededError,
    RateLimitUnavailableError,
    RedisRateLimiter,
    clear_rate_limit_state,
    enforce_rate_limit,
    set_rate_limiter_for_testing,
)


def _safe_production_settings(**overrides) -> Settings:
    values = {
        "DATABASE_URL": "postgresql://database.example/admitly",
        "ENV": "production",
        "JWT_SECRET": "a-production-secret-that-is-longer-than-32-characters",
        "REDIS_URL": "rediss://redis.example:6380/0",
        "ENABLE_DEV_TEST_CHECKOUT": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def setup_function() -> None:
    set_rate_limiter_for_testing(None)
    clear_rate_limit_state()


def test_rate_limit_allows_under_threshold() -> None:
    enforce_rate_limit(scope="payments", key="user-1", limit=2, window_seconds=60)
    enforce_rate_limit(scope="payments", key="user-1", limit=2, window_seconds=60)


def test_rate_limit_blocks_over_threshold_with_clear_error() -> None:
    enforce_rate_limit(scope="payments", key="user-1", limit=1, window_seconds=60)
    try:
        enforce_rate_limit(scope="payments", key="user-1", limit=1, window_seconds=60)
        assert False, "Expected rate limit exception"
    except RateLimitExceededError as exc:
        assert "Too many requests" in str(exc)


class _FakeRedis:
    def __init__(self) -> None:
        self.count = 0

    def eval(self, *_args):
        self.count += 1
        return [self.count, 60]


def test_redis_limiter_is_shared_through_atomic_counter() -> None:
    fake = _FakeRedis()
    first_worker = RedisRateLimiter(fake, prefix="test")
    second_worker = RedisRateLimiter(fake, prefix="test")
    first_worker.enforce(scope="login", key="same", limit=1, window_seconds=60)
    with pytest.raises(RateLimitExceededError) as exc_info:
        second_worker.enforce(scope="login", key="same", limit=1, window_seconds=60)
    assert exc_info.value.retry_after_seconds == 60


def test_redis_failure_fails_closed() -> None:
    class BrokenRedis:
        def eval(self, *_args):
            raise ConnectionError("offline")

    limiter = RedisRateLimiter(BrokenRedis(), prefix="test")
    with pytest.raises(RateLimitUnavailableError):
        limiter.enforce(scope="login", key="same", limit=1, window_seconds=60)


def test_production_rejects_local_limiter_and_dev_checkout() -> None:
    with pytest.raises(ValidationError, match="ENABLE_DEV_TEST_CHECKOUT must be false"):
        Settings(
            _env_file=None,
            DATABASE_URL="postgresql://example",
            ENV="production",
            JWT_SECRET="not-the-development-secret",
            REDIS_URL="redis://example",
            ENABLE_DEV_TEST_CHECKOUT=True,
        )

    with pytest.raises(ValidationError, match="REDIS_URL is required"):
        Settings(
            _env_file=None,
            DATABASE_URL="postgresql://example",
            ENV="production",
            JWT_SECRET="not-the-development-secret",
            ENABLE_DEV_TEST_CHECKOUT=False,
        )


def test_production_rejects_mock_payments() -> None:
    with pytest.raises(ValidationError, match="MMG_PROVIDER_MODE must be live"):
        Settings(
            _env_file=None,
            DATABASE_URL="postgresql://example",
            ENV="production",
            JWT_SECRET="not-the-development-secret",
            REDIS_URL="redis://example",
            ENABLE_DEV_TEST_CHECKOUT=False,
            MMG_ENABLED=True,
            MMG_PROVIDER_MODE="mock",
        )


def test_safe_production_configuration_passes() -> None:
    configured = _safe_production_settings()
    assert configured.is_production
    assert "http://localhost:5173" not in configured.allowed_cors_origins


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"JWT_SECRET": "dev-change-me"}, "JWT_SECRET must be non-default"),
        ({"JWT_SECRET": "too-short"}, "JWT_SECRET must be non-default"),
        ({"REDIS_URL": "redis://localhost:6379/0"}, "shared non-local Redis"),
        ({"REDIS_URL": "https://redis.example"}, "valid redis:// or rediss://"),
        ({"CORS_ALLOWED_ORIGINS": "http://localhost:5173"}, "unsafe production origin"),
        ({"CORS_ALLOWED_ORIGINS": "https://*.example.com"}, "unsafe production origin"),
        ({"FRONTEND_BASE_URL": "http://admitlyevents.com"}, "valid HTTPS URL"),
        ({"TICKET_PUBLIC_BASE_URL": "not-a-url"}, "valid HTTPS URL"),
        ({"APP_DEEP_LINK_BASE_URL": "http://localhost"}, "registered admitly://"),
        ({"LOG_LEVEL": "DEBUG"}, "LOG_LEVEL must be"),
        ({"RATE_LIMIT_LOGIN_COUNT": 0}, "rate-limit counts and windows"),
    ],
)
def test_production_rejects_individual_unsafe_values(overrides: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _safe_production_settings(**overrides)


def test_disabled_mmg_does_not_require_live_credentials() -> None:
    configured = _safe_production_settings(MMG_ENABLED=False, MMG_PROVIDER_MODE="mock")
    assert configured.mmg_enabled is False


def test_enabled_live_mmg_requires_existing_repository_config_fields() -> None:
    with pytest.raises(ValidationError, match="enabled live MMG is missing"):
        _safe_production_settings(MMG_ENABLED=True, MMG_PROVIDER_MODE="live")

    configured = _safe_production_settings(
        MMG_ENABLED=True,
        MMG_PROVIDER_MODE="live",
        MMG_BASE_URL="https://mmg.example",
        MMG_MERCHANT_ID="merchant",
        MMG_API_KEY="key",
        MMG_API_SECRET="secret",
        MMG_CALLBACK_URL="https://api.example/payments/mmg/callback",
    )
    assert configured.mmg_provider_mode == "live"


def test_sentry_release_resolution_prefers_explicit_then_render_then_version() -> None:
    assert _safe_production_settings(SENTRY_RELEASE="custom-release").resolved_sentry_release == "custom-release"
    assert _safe_production_settings(RENDER_GIT_COMMIT="abc123").resolved_sentry_release == "admitly-backend@abc123"
    assert _safe_production_settings(APP_VERSION="2.4.0").resolved_sentry_release == "admitly-backend@2.4.0"
