from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EventStaffRole
from app.models.event_staff import EventStaff
from app.models.user import User
from app.services.event_permissions import (
    EventPermissionAction,
    has_event_permission_by_id,
    require_event_permission,
)


class EventStaffError(ValueError):
    """Base staff management error."""


class EventStaffNotFoundError(EventStaffError):
    """Raised when staff assignment is not found."""


class EventStaffConflictError(EventStaffError):
    """Raised when duplicate assignment exists."""


class EventStaffValidationError(EventStaffError):
    """Raised when staff operation violates business rules."""


def list_event_staff(db: Session, *, actor_user_id: int, event_id: int) -> list[EventStaff]:
    require_event_permission(
        db,
        user_id=actor_user_id,
        event_id=event_id,
        action=EventPermissionAction.VIEW_EVENT_STAFF,
    )
    return db.execute(select(EventStaff).where(EventStaff.event_id == event_id).order_by(EventStaff.created_at.asc())).scalars().all()


def can_manage_event_staff(db: Session, *, actor_user_id: int, event_id: int) -> bool:
    return has_event_permission_by_id(
        db,
        user_id=actor_user_id,
        event_id=event_id,
        action=EventPermissionAction.MANAGE_EVENT_STAFF,
    )


def add_event_staff(
    db: Session,
    *,
    actor_user_id: int,
    event_id: int,
    user_id: int,
    role: EventStaffRole,
) -> EventStaff:
    require_event_permission(
        db,
        user_id=actor_user_id,
        event_id=event_id,
        action=EventPermissionAction.MANAGE_EVENT_STAFF,
    )
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise EventStaffValidationError("User not found.")

    existing = db.execute(
        select(EventStaff).where(EventStaff.event_id == event_id, EventStaff.user_id == user_id)
    ).scalar_one_or_none()
    if existing is not None:
        raise EventStaffConflictError("User is already assigned to this event.")

    if role == EventStaffRole.OWNER:
        raise EventStaffValidationError("Owner role is derived from event ownership.")

    assignment = EventStaff(
        event_id=event_id,
        user_id=user_id,
        role=role,
        is_active=True,
        invited_by_user_id=actor_user_id,
    )
    db.add(assignment)
    db.flush()
    return assignment


def update_event_staff_role(
    db: Session,
    *,
    actor_user_id: int,
    event_id: int,
    staff_id: int,
    role: EventStaffRole,
) -> EventStaff:
    require_event_permission(
        db,
        user_id=actor_user_id,
        event_id=event_id,
        action=EventPermissionAction.MANAGE_EVENT_STAFF,
    )
    assignment = db.execute(
        select(EventStaff).where(EventStaff.id == staff_id, EventStaff.event_id == event_id)
    ).scalar_one_or_none()
    if assignment is None:
        raise EventStaffNotFoundError("Event staff assignment not found.")
    if role == EventStaffRole.OWNER:
        raise EventStaffValidationError("Owner role is derived from event ownership.")

    assignment.role = role
    db.flush()
    return assignment


def remove_event_staff(
    db: Session,
    *,
    actor_user_id: int,
    event_id: int,
    staff_id: int,
) -> None:
    require_event_permission(
        db,
        user_id=actor_user_id,
        event_id=event_id,
        action=EventPermissionAction.MANAGE_EVENT_STAFF,
    )
    assignment = db.execute(
        select(EventStaff).where(EventStaff.id == staff_id, EventStaff.event_id == event_id)
    ).scalar_one_or_none()
    if assignment is None:
        raise EventStaffNotFoundError("Event staff assignment not found.")
    db.delete(assignment)
    db.flush()
