from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
import hashlib
import logging
from threading import Lock
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings


logger = logging.getLogger(__name__)


class RateLimitExceededError(ValueError):
    """Raised when too many requests are made for a key/scope."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__(f"Too many requests. Retry in {self.retry_after_seconds} seconds.")


class RateLimitUnavailableError(RuntimeError):
    """Raised when a required shared limiter cannot be reached safely."""


class RateLimiter(Protocol):
    def enforce(self, *, scope: str, key: str, limit: int, window_seconds: int) -> None: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryRateLimiter:
    """Single-process limiter for local development and isolated tests only."""

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], deque[datetime]] = {}
        self._lock = Lock()

    def enforce(self, *, scope: str, key: str, limit: int, window_seconds: int) -> None:
        now = _now()
        window_start = now - timedelta(seconds=window_seconds)
        bucket_key = (scope, key)
        with self._lock:
            bucket = self._buckets.setdefault(bucket_key, deque())
            while bucket and bucket[0] <= window_start:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = int(
                    max(1, (bucket[0] + timedelta(seconds=window_seconds) - now).total_seconds())
                )
                raise RateLimitExceededError(retry_after)
            bucket.append(now)

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()


_REDIS_INCREMENT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


class RedisRateLimiter:
    """Atomic fixed-window limiter shared by all API workers."""

    def __init__(self, client: Redis, *, prefix: str) -> None:
        self._client = client
        self._prefix = prefix.rstrip(":")

    def _redis_key(self, *, scope: str, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"{self._prefix}:{scope}:{digest}"

    def enforce(self, *, scope: str, key: str, limit: int, window_seconds: int) -> None:
        redis_key = self._redis_key(scope=scope, key=key)
        try:
            current, ttl = self._client.eval(
                _REDIS_INCREMENT_SCRIPT,
                1,
                redis_key,
                max(1, window_seconds),
            )
        except RedisError as exc:
            logger.exception("Shared rate limiter unavailable", extra={"scope": scope})
            raise RateLimitUnavailableError("Rate limiting is temporarily unavailable.") from exc
        if int(current) > limit:
            raise RateLimitExceededError(max(1, int(ttl)))


_memory_limiter = MemoryRateLimiter()
_configured_limiter: RateLimiter | None = None
_configuration_lock = Lock()


def _get_limiter() -> RateLimiter:
    global _configured_limiter
    if _configured_limiter is not None:
        return _configured_limiter
    with _configuration_lock:
        if _configured_limiter is None:
            if settings.redis_url:
                client = Redis.from_url(
                    settings.redis_url,
                    decode_responses=False,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                _configured_limiter = RedisRateLimiter(
                    client, prefix=settings.rate_limit_key_prefix
                )
            else:
                _configured_limiter = _memory_limiter
                logger.warning("Using process-local rate limiting outside production")
    return _configured_limiter


def enforce_rate_limit(*, scope: str, key: str, limit: int, window_seconds: int) -> None:
    if limit <= 0:
        return
    try:
        _get_limiter().enforce(
            scope=scope,
            key=key,
            limit=limit,
            window_seconds=window_seconds,
        )
    except RateLimitExceededError:
        logger.warning(
            "Rate limit exceeded",
            extra={"scope": scope, "limit": limit, "window_seconds": window_seconds},
        )
        raise


def clear_rate_limit_state() -> None:
    """Clear only the local test limiter; never scan or delete shared Redis keys."""
    _memory_limiter.clear()


def set_rate_limiter_for_testing(limiter: RateLimiter | None) -> None:
    global _configured_limiter
    _configured_limiter = limiter
