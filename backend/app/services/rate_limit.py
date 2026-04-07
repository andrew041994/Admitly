from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
import logging


logger = logging.getLogger(__name__)


class RateLimitExceededError(ValueError):
    """Raised when too many requests are made for a key/scope."""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int | None


_BUCKETS: dict[tuple[str, str], deque[datetime]] = {}
_LOCK = Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enforce_rate_limit(*, scope: str, key: str, limit: int, window_seconds: int) -> None:
    if limit <= 0:
        return

    now = _now()
    window_start = now - timedelta(seconds=window_seconds)
    bucket_key = (scope, key)

    with _LOCK:
        bucket = _BUCKETS.setdefault(bucket_key, deque())
        while bucket and bucket[0] <= window_start:
            bucket.popleft()

        if len(bucket) >= limit:
            retry_after = int(max(1, (bucket[0] + timedelta(seconds=window_seconds) - now).total_seconds()))
            logger.warning(
                "Rate limit exceeded",
                extra={"scope": scope, "key": key, "limit": limit, "window_seconds": window_seconds},
            )
            raise RateLimitExceededError(f"Too many requests. Retry in {retry_after} seconds.")

        bucket.append(now)


def clear_rate_limit_state() -> None:
    with _LOCK:
        _BUCKETS.clear()
