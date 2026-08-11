from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import re
import time
from uuid import uuid4

import sentry_sdk
from fastapi import FastAPI, Request
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from app.core.config import settings


request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        for field in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "scope",
            "user_id",
            "order_id",
            "payment_reference",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root.handlers.clear()
    root.addHandler(handler)


def configure_sentry() -> None:
    if not settings.sentry_dsn:
        if settings.is_production:
            logging.getLogger("admitly.config").warning(
                "Sentry is not configured; production error reporting is disabled",
                extra={"environment": settings.env},
            )
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        release=settings.resolved_sentry_release,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )


def install_request_observability(app: FastAPI) -> None:
    access_logger = logging.getLogger("admitly.access")

    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if _REQUEST_ID_PATTERN.fullmatch(supplied) else uuid4().hex
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        try:
            with sentry_sdk.isolation_scope() as scope:
                scope.set_tag("request_id", request_id)
                response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logging.getLogger("admitly.error").exception(
                "Unhandled request error",
                extra={"method": request.method, "path": request.url.path},
            )
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            status_code = locals().get("response")
            access_logger.info(
                "Request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": getattr(status_code, "status_code", 500),
                    "duration_ms": duration_ms,
                },
            )
            request_id_context.reset(token)
