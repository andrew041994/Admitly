from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.schemas.notification import (
    InAppNotificationResponse,
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdateRequest,
    PushTokenDeleteRequest,
    PushTokenDeleteResponse,
    PushTokenRegisterRequest,
    PushTokenRegisterResponse,
    UnreadCountResponse,
)
from app.services.notification_center import (
    get_or_create_preferences,
    list_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    unread_count,
    utc_now,
)
from app.services.notifications import deactivate_push_token, register_push_token
from app.services.rate_limit import RateLimitExceededError, enforce_rate_limit

router = APIRouter(prefix="/me", tags=["notifications"])


def _notification_response(row) -> InAppNotificationResponse:
    return InAppNotificationResponse(
        id=row.id,
        notification_type=row.notification_type,
        title=row.title,
        body=row.body,
        is_read=row.is_read,
        read_at=row.read_at,
        route_key=row.route_key,
        route_params=row.route_params or {},
        related_entity_type=row.related_entity_type,
        related_entity_id=row.related_entity_id,
        created_at=row.created_at,
    )


def _preferences_response(row) -> NotificationPreferencesResponse:
    return NotificationPreferencesResponse(
        ticket_activity_push_enabled=row.ticket_activity_push_enabled,
        event_reminders_push_enabled=row.event_reminders_push_enabled,
        nearby_events_push_enabled=row.nearby_events_push_enabled,
        location_discovery_enabled=row.location_discovery_enabled,
        has_saved_location=row.latitude is not None and row.longitude is not None,
        location_updated_at=row.location_updated_at,
    )


@router.get("/notifications", response_model=NotificationListResponse)
def list_my_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    before_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> NotificationListResponse:
    rows = list_user_notifications(db, user_id=user_id, limit=limit, before_id=before_id)
    return NotificationListResponse(
        items=[_notification_response(row) for row in rows],
        next_cursor=rows[-1].id if len(rows) == limit else None,
    )


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
def get_my_unread_count(
    db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)
) -> UnreadCountResponse:
    return UnreadCountResponse(unread_count=unread_count(db, user_id=user_id))


@router.post("/notifications/{notification_id}/read", response_model=InAppNotificationResponse)
def mark_my_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> InAppNotificationResponse:
    row = mark_notification_read(db, user_id=user_id, notification_id=notification_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    db.commit()
    db.refresh(row)
    return _notification_response(row)


@router.post("/notifications/read-all", response_model=MarkAllReadResponse)
def mark_all_my_notifications_read(
    db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)
) -> MarkAllReadResponse:
    count = mark_all_notifications_read(db, user_id=user_id)
    db.commit()
    return MarkAllReadResponse(updated_count=count, unread_count=0)


@router.get("/notification-preferences", response_model=NotificationPreferencesResponse)
def get_my_notification_preferences(
    db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)
) -> NotificationPreferencesResponse:
    row = get_or_create_preferences(db, user_id=user_id)
    db.commit()
    db.refresh(row)
    return _preferences_response(row)


@router.patch("/notification-preferences", response_model=NotificationPreferencesResponse)
def update_my_notification_preferences(
    payload: NotificationPreferencesUpdateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> NotificationPreferencesResponse:
    row = get_or_create_preferences(db, user_id=user_id)
    values = payload.model_dump(exclude_unset=True, exclude={"latitude", "longitude"})
    for key, value in values.items():
        setattr(row, key, value)
    if payload.latitude is not None and payload.longitude is not None:
        row.latitude = payload.latitude
        row.longitude = payload.longitude
        row.location_updated_at = utc_now()
    if payload.location_discovery_enabled is False:
        row.nearby_events_push_enabled = False
        row.latitude = None
        row.longitude = None
        row.location_updated_at = None
    if row.nearby_events_push_enabled and (
        not row.location_discovery_enabled or row.latitude is None or row.longitude is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Save a confirmed location before enabling nearby event alerts.",
        )
    db.commit()
    db.refresh(row)
    return _preferences_response(row)


@router.post("/push-tokens", response_model=PushTokenRegisterResponse, status_code=status.HTTP_201_CREATED)
def register_my_push_token(
    payload: PushTokenRegisterRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> PushTokenRegisterResponse:
    try:
        enforce_rate_limit(
            scope="push-token-registration",
            key=str(user_id),
            limit=settings.rate_limit_push_registration_count,
            window_seconds=settings.rate_limit_push_registration_window_seconds,
        )
    except RateLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    register_push_token(
        db,
        user_id=user_id,
        token=payload.token,
        platform=payload.platform,
        installation_id=payload.installation_id,
    )
    db.commit()
    return PushTokenRegisterResponse(success=True, device_registered=True)


@router.delete("/push-tokens", response_model=PushTokenDeleteResponse)
def delete_my_push_token(
    payload: PushTokenDeleteRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> PushTokenDeleteResponse:
    deleted = deactivate_push_token(
        db, user_id=user_id, token=payload.token, installation_id=payload.installation_id
    )
    db.commit()
    return PushTokenDeleteResponse(success=deleted)
