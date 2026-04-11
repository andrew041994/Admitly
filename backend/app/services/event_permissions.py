from __future__ import annotations

from enum import Enum
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.enums import EventStaffRole
from app.models.event import Event
from app.models.event_staff import EventStaff
from app.models.organizer_profile import OrganizerProfile
from app.models.user import User
from app.services.ticket_holds import get_guyana_now

class EventPermissionAction(str, Enum):
    VIEW_EVENT_STAFF = "view_event_staff"
    MANAGE_EVENT_STAFF = "manage_event_staff"
    EDIT_EVENT = "edit_event"
    CANCEL_EVENT = "cancel_event"
    VIEW_ORDERS = "view_orders"
    MANAGE_REFUNDS = "manage_refunds"
    # CHECK_IN = "checkin_tickets"
    CHECKIN_TICKETS = "checkin_tickets"
    VIEW_CHECKIN_SUMMARY = "view_checkin_summary"
    CHECKIN_OVERRIDE = "checkin_override"


class EventPermissionError(ValueError):
    """Base event permission error."""


class EventPermissionDeniedError(EventPermissionError):
    """Raised when user lacks a required event permission."""


class EventPermissionNotFoundError(EventPermissionError):
    """Raised when event does not exist."""


def _is_event_owner(db: Session, *, event: Event, user_id: int) -> bool:
    organizer_user_id = db.execute(
        select(OrganizerProfile.user_id).where(OrganizerProfile.id == event.organizer_id)
    ).scalar_one_or_none()
    return organizer_user_id == user_id


def _get_staff_role(db: Session, *, event_id: int, user_id: int) -> EventStaffRole | None:
    staff = db.execute(
        select(EventStaff)
        .where(
            EventStaff.event_id == event_id,
            EventStaff.user_id == user_id,
            or_(
                EventStaff.is_active.is_(True),
                EventStaff.is_active.is_(None),
            ),
        )
    ).scalar_one_or_none()

    if staff is None:
        return None
    return staff.role


def _role_permissions(role: EventStaffRole) -> set[EventPermissionAction]:
    if role == EventStaffRole.OWNER:
        return set(EventPermissionAction)
    if role == EventStaffRole.MANAGER:
        return {
            EventPermissionAction.VIEW_EVENT_STAFF,
            EventPermissionAction.VIEW_ORDERS,
            EventPermissionAction.VIEW_CHECKIN_SUMMARY,
            EventPermissionAction.MANAGE_REFUNDS,
            EventPermissionAction.CHECKIN_OVERRIDE,
        }
    if role == EventStaffRole.CHECKIN:
        return {
            EventPermissionAction.CHECKIN_TICKETS,
        }
    if role == EventStaffRole.SUPPORT:
        return set()
    return set()


def has_event_permission(
    db: Session,
    *,
    user_id: int,
    event: Event,
    action: EventPermissionAction,
) -> bool:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        return False
    if user.is_admin:
        return True
    if _is_event_owner(db, event=event, user_id=user_id):
        return True

    role = _get_staff_role(db, event_id=event.id, user_id=user_id)
    if role is None:
        return False
    return action in _role_permissions(role)


def has_event_permission_by_id(
    db: Session,
    *,
    user_id: int,
    event_id: int,
    action: EventPermissionAction,
) -> bool:
    event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if event is None:
        return False

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        return False

    if user.is_admin:
        return True

    if _is_event_owner(db, event=event, user_id=user_id):
        return True

    role = _get_staff_role(db, event_id=event_id, user_id=user_id)
    if role is None:
        return False

    permissions = _role_permissions(role)
    if action not in permissions:
        return False

    if action == EventPermissionAction.CHECKIN_TICKETS:
        if event.end_at is not None:
            now = get_guyana_now()
            end_at = event.end_at
            if end_at.tzinfo is None:
                end_at = end_at.replace(tzinfo=now.tzinfo)
            if end_at < now:
                return False
        return True

    return True


def require_event_permission(
    db: Session,
    *,
    user_id: int,
    event_id: int,
    action: EventPermissionAction,
) -> Event:
    event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if event is None:
        raise EventPermissionNotFoundError("Event not found.")
    if not has_event_permission(db, user_id=user_id, event=event, action=action):
        raise EventPermissionDeniedError("Not authorized for this event action.")
    return event


def get_event_staff_role(
    db: Session,
    *,
    user_id: int,
    event_id: int,
) -> EventStaffRole | None:
    event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if event is None:
        return None
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        return None
    if user.is_admin or _is_event_owner(db, event=event, user_id=user_id):
        return EventStaffRole.OWNER
    return _get_staff_role(db, event_id=event_id, user_id=user_id)
