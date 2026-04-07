from app.services.rate_limit import RateLimitExceededError, clear_rate_limit_state, enforce_rate_limit


def setup_function() -> None:
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
