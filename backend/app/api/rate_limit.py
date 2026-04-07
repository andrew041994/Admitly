from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.services.rate_limit import RateLimitExceededError, enforce_rate_limit


def request_client_ip(x_forwarded_for: str | None = Header(default=None)) -> str:
    if not x_forwarded_for:
        return "unknown"
    return x_forwarded_for.split(",", 1)[0].strip() or "unknown"


def apply_rate_limit(*, scope: str, key: str, limit: int, window_seconds: int) -> None:
    try:
        enforce_rate_limit(scope=scope, key=key, limit=limit, window_seconds=window_seconds)
    except RateLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
