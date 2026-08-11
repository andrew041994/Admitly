from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.services.rate_limit import (
    RateLimitExceededError,
    RateLimitUnavailableError,
    enforce_rate_limit,
)


def request_client_ip(request: Request) -> str:
    """Use the ASGI peer resolved by the server's trusted proxy middleware.

    Reading X-Forwarded-For directly would let an internet client choose a new
    limiter identity on every request unless every hop sanitized the header.
    """
    return request.client.host if request.client else "unknown"


def apply_rate_limit(*, scope: str, key: str, limit: int, window_seconds: int) -> None:
    try:
        enforce_rate_limit(scope=scope, key=key, limit=limit, window_seconds=window_seconds)
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except RateLimitUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Request protection is temporarily unavailable. Please try again.",
            headers={"Retry-After": "5"},
        ) from exc
