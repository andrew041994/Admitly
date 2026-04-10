from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EventStaffRole, EventStatus
from app.models.event import Event
from app.models.event_staff import EventStaff
from app.models.organizer_profile import OrganizerProfile
from app.models.user import User
from app.services.event_permissions import (
    EventPermissionAction,
    EventPermissionDeniedError,
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
    event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if event is None:
        raise EventPermissionDeniedError("Not authorized for this event action.")
    organizer_user_id = db.execute(
        select(OrganizerProfile.user_id).where(OrganizerProfile.id == event.organizer_id)
    ).scalar_one_or_none()
    if organizer_user_id != actor_user_id:
        admin_staff = db.execute(
            select(EventStaff.id).where(
                EventStaff.event_id == event_id,
                EventStaff.user_id == actor_user_id,
                EventStaff.is_active.is_(True),
                EventStaff.role == EventStaffRole.ADMIN,
            )
        ).scalar_one_or_none()
        if admin_staff is None:
            raise EventPermissionDeniedError("Not authorized for this event action.")
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

    event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if event is None:
        raise EventStaffValidationError("Event not found.")
    if event.status == EventStatus.CANCELLED:
        raise EventStaffValidationError("Cannot assign staff to cancelled events.")

    existing = db.execute(
        select(EventStaff).where(EventStaff.event_id == event_id, EventStaff.user_id == user_id)
    ).scalar_one_or_none()
    if existing is not None and existing.is_active:
        raise EventStaffConflictError("User is already assigned to this event.")

    if role == EventStaffRole.OWNER:
        raise EventStaffValidationError("Owner role is derived from event ownership.")

    if role not in {EventStaffRole.MANAGER, EventStaffRole.CHECKIN, EventStaffRole.SUPPORT}:
        raise EventStaffValidationError("Only manager, check-in, or support staff can be assigned.")

    if existing is not None:
        existing.role = role
        existing.is_active = True
        existing.invited_by_user_id = actor_user_id
        db.flush()
        return existing

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
    if role not in {EventStaffRole.MANAGER, EventStaffRole.CHECKIN, EventStaffRole.SUPPORT}:
        raise EventStaffValidationError("Only manager, check-in, or support staff can be assigned.")

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
