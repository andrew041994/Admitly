from __future__ import annotations

import json
import logging
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.push_dispatch import PushDispatch
from app.models.user_notification import UserNotification
from app.services.notification_center import utc_now

logger = logging.getLogger(__name__)
EXPO_SEND_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
MAX_ATTEMPTS = 5


def _expo_post(url: str, payload: object) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - fixed Expo HTTPS endpoints only
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError("expo_transport_error") from exc


def _retry(dispatch: PushDispatch, *, code: str) -> None:
    dispatch.status = "failed" if dispatch.attempts >= MAX_ATTEMPTS else "pending"
    dispatch.error_code = code[:64]
    dispatch.claimed_at = None
    dispatch.next_attempt_at = utc_now() + timedelta(minutes=min(30, 2 ** max(0, dispatch.attempts - 1)))


def _disable_token(dispatch: PushDispatch, *, reason: str) -> None:
    dispatch.status = "failed"
    dispatch.error_code = reason[:64]
    dispatch.push_token.is_active = False
    dispatch.push_token.disabled_reason = reason[:64]


def process_push_dispatches(db: Session, *, limit: int = 100) -> dict[str, int]:
    now = utc_now()
    stale_before = now - timedelta(minutes=10)
    dispatches = db.execute(
        select(PushDispatch)
        .where(
            or_(
                PushDispatch.status == "pending",
                (PushDispatch.status == "processing") & (PushDispatch.claimed_at < stale_before),
            ),
            or_(PushDispatch.next_attempt_at.is_(None), PushDispatch.next_attempt_at <= now),
        )
        .order_by(PushDispatch.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
    ).scalars().all()
    summary = {"claimed": len(dispatches), "sent": 0, "failed": 0, "skipped": 0}
    for dispatch in dispatches:
        dispatch.status = "processing"
        dispatch.claimed_at = now
        dispatch.attempts += 1
    db.commit()

    for dispatch in dispatches:
        notification = dispatch.notification
        token = dispatch.push_token
        if not token.is_active:
            dispatch.status = "failed"
            dispatch.error_code = "token_inactive"
            summary["skipped"] += 1
        elif not settings.push_notifications_enabled or settings.push_provider == "noop":
            dispatch.status = "pending"
            dispatch.claimed_at = None
            dispatch.next_attempt_at = now + timedelta(hours=1)
            dispatch.provider_status = "disabled"
            summary["skipped"] += 1
        elif settings.push_provider == "mock":
            dispatch.status = "sent"
            dispatch.provider_status = "ok"
            summary["sent"] += 1
        elif settings.push_provider == "expo":
            try:
                response = _expo_post(EXPO_SEND_URL, {
                    "to": token.token,
                    "title": notification.title,
                    "body": notification.body,
                    "data": {
                        "notificationId": notification.id,
                        "type": notification.notification_type,
                        "routeKey": notification.route_key,
                        **(notification.route_params or {}),
                    },
                    "sound": "default",
                })
                ticket = response.get("data") or {}
                if ticket.get("status") == "ok" and ticket.get("id"):
                    dispatch.status = "receipt_pending"
                    dispatch.provider_status = "accepted"
                    dispatch.provider_ticket_id = str(ticket["id"])
                    dispatch.next_attempt_at = now + timedelta(minutes=15)
                    summary["sent"] += 1
                else:
                    details = ticket.get("details") or {}
                    code = str(details.get("error") or "expo_rejected")
                    if code == "DeviceNotRegistered":
                        _disable_token(dispatch, reason=code)
                    else:
                        _retry(dispatch, code=code)
                    summary["failed"] += 1
            except RuntimeError:
                _retry(dispatch, code="expo_transport_error")
                summary["failed"] += 1
        else:
            _retry(dispatch, code="provider_unconfigured")
            summary["failed"] += 1
        db.commit()

    notification_ids = {row.notification_id for row in dispatches}
    for notification_id in notification_ids:
        statuses = set(db.execute(
            select(PushDispatch.status).where(PushDispatch.notification_id == notification_id)
        ).scalars().all())
        notification = db.get(UserNotification, notification_id)
        if notification is not None:
            if statuses <= {"sent"}:
                notification.push_status = "sent"
            elif "pending" in statuses or "processing" in statuses or "receipt_pending" in statuses:
                notification.push_status = "queued"
            elif statuses:
                notification.push_status = "failed"
    db.commit()
    return summary


def process_expo_receipts(db: Session, *, limit: int = 300) -> dict[str, int]:
    due = db.execute(
        select(PushDispatch)
        .where(
            PushDispatch.status == "receipt_pending",
            PushDispatch.provider_ticket_id.is_not(None),
            PushDispatch.next_attempt_at <= utc_now(),
        )
        .order_by(PushDispatch.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
    ).scalars().all()
    if not due or settings.push_provider != "expo" or not settings.push_notifications_enabled:
        return {"checked": 0, "delivered": 0, "failed": 0}
    ids = [row.provider_ticket_id for row in due if row.provider_ticket_id]
    try:
        receipts = (_expo_post(EXPO_RECEIPTS_URL, {"ids": ids}).get("data") or {})
    except RuntimeError:
        return {"checked": 0, "delivered": 0, "failed": 0}
    summary = {"checked": len(due), "delivered": 0, "failed": 0}
    for dispatch in due:
        receipt = receipts.get(dispatch.provider_ticket_id or "")
        if not receipt:
            dispatch.next_attempt_at = utc_now() + timedelta(minutes=15)
            continue
        if receipt.get("status") == "ok":
            dispatch.status = "sent"
            dispatch.provider_status = "delivered"
            summary["delivered"] += 1
        else:
            code = str((receipt.get("details") or {}).get("error") or "expo_receipt_error")
            if code == "DeviceNotRegistered":
                _disable_token(dispatch, reason=code)
            elif code in {"MessageRateExceeded", "expo_receipt_error"}:
                _retry(dispatch, code=code)
            else:
                dispatch.status = "failed"
                dispatch.error_code = code[:64]
            summary["failed"] += 1
    notification_ids = {row.notification_id for row in due}
    for notification_id in notification_ids:
        statuses = set(db.execute(
            select(PushDispatch.status).where(PushDispatch.notification_id == notification_id)
        ).scalars().all())
        notification = db.get(UserNotification, notification_id)
        if notification is not None:
            if statuses <= {"sent"}:
                notification.push_status = "sent"
            elif statuses & {"pending", "processing", "receipt_pending"}:
                notification.push_status = "queued"
            elif statuses:
                notification.push_status = "failed"
    db.commit()
    return summary
