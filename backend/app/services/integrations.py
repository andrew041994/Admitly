from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.integration_api_key import IntegrationApiKey
from app.models.order import Order
from app.models.ticket import Ticket
from app.models.ticket_transfer_invite import TicketTransferInvite
from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_endpoint import WebhookEndpoint

INTEGRATION_API_VERSION = "v1"
SUPPORTED_WEBHOOK_EVENTS = {
    "order.paid",
    "order.refunded",
    "refund.processed",
    "transfer.accepted",
    "checkin.completed",
}
SCOPE_READ = "integrations:read"
SCOPE_WRITE = "integrations:write"
MAX_RETRIES = 4
RETRY_BACKOFF_SECONDS = [30, 120, 600, 1800]


@dataclass
class DeliveryResult:
    ok: bool
    status_code: int | None
    error: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _scopes_to_csv(scopes: list[str]) -> str:
    normalized = sorted({item.strip() for item in scopes if item.strip()})
    return ",".join(normalized)


def scopes_from_csv(scopes_csv: str) -> set[str]:
    return {item.strip() for item in scopes_csv.split(",") if item.strip()}


def _hash_api_secret(prefix: str, raw_secret: str) -> str:
    return hashlib.sha256(f"{prefix}.{raw_secret}".encode("utf-8")).hexdigest()


def create_api_key(db: Session, *, user_id: int, name: str, scopes: list[str]) -> tuple[IntegrationApiKey, str]:
    prefix = f"adm_{secrets.token_hex(6)}"
    raw_secret = secrets.token_urlsafe(32)
    key = IntegrationApiKey(
        user_id=user_id,
        name=name.strip(),
        key_prefix=prefix,
        secret_hash=_hash_api_secret(prefix, raw_secret),
        scopes_csv=_scopes_to_csv(scopes or [SCOPE_READ]),
    )
    db.add(key)
    db.flush()
    return key, f"{prefix}.{raw_secret}"


def list_api_keys(db: Session, *, user_id: int) -> list[IntegrationApiKey]:
    return db.execute(select(IntegrationApiKey).where(IntegrationApiKey.user_id == user_id).order_by(IntegrationApiKey.id.desc())).scalars().all()


def revoke_api_key(db: Session, *, key_id: int, user_id: int) -> IntegrationApiKey | None:
    key = db.execute(
        select(IntegrationApiKey).where(IntegrationApiKey.id == key_id, IntegrationApiKey.user_id == user_id)
    ).scalar_one_or_none()
    if key is None:
        return None
    key.revoked_at = _utcnow()
    db.flush()
    return key


def authenticate_api_key(db: Session, *, raw_key: str | None) -> IntegrationApiKey | None:
    if not raw_key or "." not in raw_key:
        return None
    prefix, raw_secret = raw_key.split(".", 1)
    key = db.execute(select(IntegrationApiKey).where(IntegrationApiKey.key_prefix == prefix)).scalar_one_or_none()
    if key is None or key.revoked_at is not None:
        return None
    if not hmac.compare_digest(key.secret_hash, _hash_api_secret(prefix, raw_secret)):
        return None
    key.last_used_at = _utcnow()
    db.flush()
    return key


def require_scope(key: IntegrationApiKey, scope: str) -> bool:
    return scope in scopes_from_csv(key.scopes_csv)


def create_webhook_endpoint(
    db: Session,
    *,
    user_id: int,
    name: str,
    target_url: str,
    subscribed_events: list[str],
) -> tuple[WebhookEndpoint, str]:
    events = sorted({item.strip() for item in subscribed_events if item.strip() in SUPPORTED_WEBHOOK_EVENTS})
    secret = f"whsec_{secrets.token_urlsafe(24)}"
    endpoint = WebhookEndpoint(
        user_id=user_id,
        name=name.strip(),
        target_url=target_url.strip(),
        signing_secret=secret,
        schema_version=INTEGRATION_API_VERSION,
        subscribed_events_csv=",".join(events),
        is_active=True,
    )
    db.add(endpoint)
    db.flush()
    return endpoint, secret


def list_webhook_endpoints(db: Session, *, user_id: int) -> list[WebhookEndpoint]:
    return db.execute(select(WebhookEndpoint).where(WebhookEndpoint.user_id == user_id).order_by(WebhookEndpoint.id.desc())).scalars().all()


def update_webhook_endpoint(
    db: Session,
    *,
    endpoint_id: int,
    user_id: int,
    name: str | None,
    target_url: str | None,
    subscribed_events: list[str] | None,
    is_active: bool | None,
) -> WebhookEndpoint | None:
    endpoint = db.execute(
        select(WebhookEndpoint).where(WebhookEndpoint.id == endpoint_id, WebhookEndpoint.user_id == user_id)
    ).scalar_one_or_none()
    if endpoint is None:
        return None
    if name is not None:
        endpoint.name = name.strip()
    if target_url is not None:
        endpoint.target_url = target_url.strip()
    if subscribed_events is not None:
        events = sorted({item.strip() for item in subscribed_events if item.strip() in SUPPORTED_WEBHOOK_EVENTS})
        endpoint.subscribed_events_csv = ",".join(events)
    if is_active is not None:
        endpoint.is_active = is_active
        endpoint.disabled_at = None if is_active else _utcnow()
    db.flush()
    return endpoint


def _event_envelope(*, event_type: str, payload: dict) -> dict:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": event_type,
        "version": INTEGRATION_API_VERSION,
        "created_at": _utcnow().isoformat(),
        "data": payload,
    }


def _signed_headers(*, secret: str, body: str) -> dict[str, str]:
    ts = str(int(_utcnow().timestamp()))
    base = f"{ts}.{body}"
    digest = hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Admitly-Timestamp": ts,
        "X-Admitly-Signature": f"v1={digest}",
        "User-Agent": "Admitly-Webhooks/1.0",
    }


def verify_webhook_signature(*, secret: str, timestamp: str, body: str, signature_header: str) -> bool:
    expected = hmac.new(secret.encode("utf-8"), f"{timestamp}.{body}".encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header.strip(), f"v1={expected}")


def _http_send(*, endpoint: WebhookEndpoint, body: str) -> DeliveryResult:
    request = urllib.request.Request(endpoint.target_url, data=body.encode("utf-8"), headers=_signed_headers(secret=endpoint.signing_secret, body=body), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status_code = int(response.getcode())
        return DeliveryResult(ok=200 <= status_code < 300, status_code=status_code)
    except urllib.error.HTTPError as exc:
        return DeliveryResult(ok=False, status_code=exc.code, error=f"http_{exc.code}")
    except Exception as exc:  # noqa: BLE001
        return DeliveryResult(ok=False, status_code=None, error=str(exc)[:200])


def _next_retry_for_attempt(attempt_number: int) -> datetime | None:
    if attempt_number > MAX_RETRIES:
        return None
    idx = min(attempt_number - 1, len(RETRY_BACKOFF_SECONDS) - 1)
    return _utcnow() + timedelta(seconds=RETRY_BACKOFF_SECONDS[idx])


def _enqueue_delivery(db: Session, *, endpoint: WebhookEndpoint, envelope: dict) -> None:
    existing = db.execute(
        select(WebhookDelivery).where(
            WebhookDelivery.endpoint_id == endpoint.id,
            WebhookDelivery.event_id == envelope["id"],
            WebhookDelivery.attempt_number == 1,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        WebhookDelivery(
            endpoint_id=endpoint.id,
            event_id=envelope["id"],
            event_type=envelope["type"],
            schema_version=envelope["version"],
            payload_json=json.dumps(envelope, sort_keys=True),
            attempt_number=1,
            status="pending",
            requested_at=_utcnow(),
            next_retry_at=_utcnow(),
        )
    )


def publish_webhook_event(db: Session, *, event_type: str, payload: dict) -> None:
    if event_type not in SUPPORTED_WEBHOOK_EVENTS:
        return
    envelope = _event_envelope(event_type=event_type, payload=payload)
    endpoints = db.execute(select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True))).scalars().all()
    for endpoint in endpoints:
        subscribed = {item.strip() for item in endpoint.subscribed_events_csv.split(",") if item.strip()}
        if event_type in subscribed:
            _enqueue_delivery(db, endpoint=endpoint, envelope=envelope)
    db.flush()


def dispatch_pending_webhook_deliveries(db: Session, *, transport=_http_send) -> int:
    now = _utcnow()
    pending = db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.status.in_(["pending", "retry_scheduled"]), WebhookDelivery.next_retry_at <= now)
        .order_by(WebhookDelivery.id.asc())
        .limit(getattr(settings, "webhook_dispatch_batch_size", 50))
    ).scalars().all()
    processed = 0
    for delivery in pending:
        endpoint = db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == delivery.endpoint_id)).scalar_one_or_none()
        if endpoint is None or not endpoint.is_active:
            delivery.status = "endpoint_disabled"
            delivery.next_retry_at = None
            processed += 1
            continue
        result = transport(endpoint=endpoint, body=delivery.payload_json)
        if result.ok:
            delivery.status = "delivered"
            delivery.response_status_code = result.status_code
            delivery.delivered_at = _utcnow()
            delivery.next_retry_at = None
        else:
            delivery.status = "retry_scheduled"
            delivery.response_status_code = result.status_code
            delivery.failure_reason = (result.error or "delivery_failed")[:255]
            next_retry = _next_retry_for_attempt(delivery.attempt_number + 1)
            if next_retry is None:
                delivery.status = "failed"
                delivery.next_retry_at = None
            else:
                delivery.next_retry_at = next_retry
                db.add(
                    WebhookDelivery(
                        endpoint_id=delivery.endpoint_id,
                        event_id=delivery.event_id,
                        event_type=delivery.event_type,
                        schema_version=delivery.schema_version,
                        payload_json=delivery.payload_json,
                        attempt_number=delivery.attempt_number + 1,
                        status="retry_scheduled",
                        requested_at=_utcnow(),
                        next_retry_at=next_retry,
                    )
                )
        processed += 1
    db.flush()
    return processed


def list_deliveries(db: Session, *, user_id: int, endpoint_id: int | None = None) -> list[WebhookDelivery]:
    endpoint_ids: Select[tuple[int]] = select(WebhookEndpoint.id).where(WebhookEndpoint.user_id == user_id)
    query = select(WebhookDelivery).where(WebhookDelivery.endpoint_id.in_(endpoint_ids))
    if endpoint_id is not None:
        query = query.where(WebhookDelivery.endpoint_id == endpoint_id)
    return db.execute(query.order_by(WebhookDelivery.id.desc()).limit(200)).scalars().all()


def build_order_paid_payload(order: Order) -> dict:
    return {"order_id": order.id, "event_id": order.event_id, "user_id": order.user_id, "total_amount": float(order.total_amount), "currency": order.currency}


def build_refund_payload(order: Order, *, refund_id: int, amount: float) -> dict:
    return {"order_id": order.id, "refund_id": refund_id, "event_id": order.event_id, "amount": amount, "currency": order.currency}


def build_transfer_payload(invite: TicketTransferInvite, ticket: Ticket) -> dict:
    return {"invite_id": invite.id, "ticket_id": ticket.id, "event_id": ticket.event_id, "to_user_id": ticket.owner_user_id}


def build_checkin_payload(ticket: Ticket) -> dict:
    return {"ticket_id": ticket.id, "event_id": ticket.event_id, "order_id": ticket.order_id, "checked_in_at": ticket.checked_in_at.isoformat() if ticket.checked_in_at else None}
