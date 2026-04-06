from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.event import Event
from app.models.enums import EventStatus, OrderStatus
from app.models.order import Order
from app.models.organizer_profile import OrganizerProfile
from app.models.user import User
from app.services.notifications import notify_event_cancelled
from app.services.tickets import invalidate_event_tickets
from app.services.ticket_holds import get_guyana_now


class EventFlowError(ValueError):
    """Base event flow error."""


class EventNotFoundError(EventFlowError):
    """Raised when event does not exist."""


class EventAuthorizationError(EventFlowError):
    """Raised when actor is not allowed to manage event."""


class EventCancellationError(EventFlowError):
    """Raised when event cancellation request is invalid."""


def _is_event_organizer_or_admin(db: Session, *, event: Event, user_id: int) -> bool:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        return False
    if user.is_admin:
        return True

    organizer_user_id = db.execute(
        select(OrganizerProfile.user_id).where(OrganizerProfile.id == event.organizer_id)
    ).scalar_one_or_none()
    return organizer_user_id == user_id


def cancel_event(
    db: Session,
    *,
    event_id: int,
    actor_user_id: int,
    reason: str | None = None,
) -> Event:
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        event = (
            db.execute(select(Event).where(Event.id == event_id).with_for_update())
            .scalars()
            .first()
        )
        if event is None:
            raise EventNotFoundError("Event not found.")
        if not _is_event_organizer_or_admin(db, event=event, user_id=actor_user_id):
            raise EventAuthorizationError("Not authorized to cancel this event.")
        if event.status == EventStatus.CANCELLED:
            raise EventCancellationError("Event is already cancelled.")

        now = get_guyana_now()
        event.status = EventStatus.CANCELLED
        event.cancelled_at = now
        event.cancelled_by_user_id = actor_user_id
        event.cancellation_reason = reason.strip() if reason else None
        event.updated_at = now

        pending_orders = (
            db.execute(
                select(Order)
                .options(joinedload(Order.ticket_holds))
                .where(Order.event_id == event.id, Order.status == OrderStatus.PENDING)
                .with_for_update()
            )
            .unique()
            .scalars()
            .all()
        )
        for order in pending_orders:
            order.status = OrderStatus.CANCELLED
            order.cancelled_at = now
            order.cancelled_by_user_id = actor_user_id
            order.cancel_reason = f"Event cancelled: {reason.strip()}" if reason else "Event cancelled"
            order.updated_at = now

        db.flush()
        invalidate_event_tickets(
            db,
            event_id=event.id,
            actor_user_id=actor_user_id,
            reason=reason or "Event cancelled",
        )
        try:
            notify_event_cancelled(event, actor_user_id=actor_user_id)
        except TypeError:
            notify_event_cancelled(db, event, actor_user_id=actor_user_id)
        return event
