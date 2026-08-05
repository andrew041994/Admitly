from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.push_dispatch import PushDispatch
from app.models.push_token import PushToken
from app.models.user_notification import NotificationPreference, UserNotification


ALLOWED_NOTIFICATION_TYPES = {
    "ticket_received",
    "ticket_transfer_accepted",
    "ticket_transfer_declined",
    "ticket_transfer_canceled",
    "ticket_purchase_completed",
    "nearby_event_created",
    "event_starting_soon",
}
ALLOWED_ROUTE_KEYS = {"ticket", "transfers", "wallet", "event"}
TRANSACTIONAL_TYPES = {
    "ticket_received",
    "ticket_transfer_accepted",
    "ticket_transfer_declined",
    "ticket_transfer_canceled",
    "ticket_purchase_completed",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_preferences(db: Session, *, user_id: int) -> NotificationPreference:
    preferences = db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    ).scalar_one_or_none()
    if preferences is None:
        db.execute(
            pg_insert(NotificationPreference)
            .values(user_id=user_id)
            .on_conflict_do_nothing(index_elements=[NotificationPreference.user_id])
        )
        preferences = db.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        ).scalar_one()
    return preferences


def _push_allowed(preferences: NotificationPreference | None, notification_type: str) -> bool:
    if notification_type in TRANSACTIONAL_TYPES:
        return preferences is None or preferences.ticket_activity_push_enabled
    if notification_type == "event_starting_soon":
        return preferences is None or preferences.event_reminders_push_enabled
    if notification_type == "nearby_event_created":
        return bool(preferences and preferences.nearby_events_push_enabled)
    return False


def create_user_notification(
    db: Session,
    *,
    user_id: int,
    notification_type: str,
    title: str,
    body: str,
    dedupe_key: str,
    route_key: str | None = None,
    route_params: dict[str, int | str] | None = None,
    related_entity_type: str | None = None,
    related_entity_id: int | None = None,
) -> tuple[UserNotification, bool]:
    if notification_type not in ALLOWED_NOTIFICATION_TYPES:
        raise ValueError("Unsupported notification type.")
    if route_key is not None and route_key not in ALLOWED_ROUTE_KEYS:
        raise ValueError("Unsupported notification route.")
    safe_title = title.strip()[:120]
    safe_body = body.strip()[:500]
    if not safe_title or not safe_body:
        raise ValueError("Notification title and body are required.")
    safe_params: dict[str, int | str] = {}
    for key, value in (route_params or {}).items():
        if key not in {"ticket_id", "event_id", "transfer_id", "order_id"}:
            raise ValueError("Unsupported notification route parameter.")
        if not isinstance(value, (int, str)):
            raise ValueError("Invalid notification route parameter.")
        safe_params[key] = value

    existing = db.execute(
        select(UserNotification).where(UserNotification.dedupe_key == dedupe_key)
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    preferences = db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    ).scalar_one_or_none()
    tokens = []
    if _push_allowed(preferences, notification_type):
        tokens = db.execute(
            select(PushToken).where(PushToken.user_id == user_id, PushToken.is_active.is_(True))
        ).scalars().all()

    notification_id = db.execute(
        pg_insert(UserNotification)
        .values(
            user_id=user_id,
            notification_type=notification_type,
            title=safe_title,
            body=safe_body,
            route_key=route_key,
            route_params=safe_params,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            dedupe_key=dedupe_key,
            push_status="queued" if tokens else ("no_tokens" if _push_allowed(preferences, notification_type) else "suppressed"),
        )
        .on_conflict_do_nothing(index_elements=[UserNotification.dedupe_key])
        .returning(UserNotification.id)
    ).scalar_one_or_none()
    if notification_id is None:
        existing = db.execute(select(UserNotification).where(UserNotification.dedupe_key == dedupe_key)).scalar_one()
        return existing, False
    for token in tokens:
        db.execute(
            pg_insert(PushDispatch)
            .values(notification_id=notification_id, push_token_id=token.id, status="pending")
            .on_conflict_do_nothing(index_elements=[PushDispatch.notification_id, PushDispatch.push_token_id])
        )
    notification = db.get(UserNotification, notification_id)
    return notification, True


def list_user_notifications(
    db: Session, *, user_id: int, limit: int = 30, before_id: int | None = None
) -> list[UserNotification]:
    query = select(UserNotification).where(UserNotification.user_id == user_id)
    if before_id is not None:
        query = query.where(UserNotification.id < before_id)
    return db.execute(
        query.order_by(UserNotification.created_at.desc(), UserNotification.id.desc()).limit(limit)
    ).scalars().all()


def unread_count(db: Session, *, user_id: int) -> int:
    return int(db.execute(
        select(func.count(UserNotification.id)).where(
            UserNotification.user_id == user_id, UserNotification.is_read.is_(False)
        )
    ).scalar_one())


def mark_notification_read(db: Session, *, user_id: int, notification_id: int) -> UserNotification | None:
    notification = db.execute(
        select(UserNotification).where(
            UserNotification.id == notification_id, UserNotification.user_id == user_id
        )
    ).scalar_one_or_none()
    if notification is None:
        return None
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = utc_now()
        db.flush()
    return notification


def mark_all_notifications_read(db: Session, *, user_id: int) -> int:
    now = utc_now()
    result = db.execute(
        update(UserNotification)
        .where(UserNotification.user_id == user_id, UserNotification.is_read.is_(False))
        .values(is_read=True, read_at=now, updated_at=now)
    )
    return int(result.rowcount or 0)
