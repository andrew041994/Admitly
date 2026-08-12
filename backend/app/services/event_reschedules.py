from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.admin_action_audit import AdminActionAudit
from app.models.enums import EventApprovalStatus, EventStatus, OrderStatus, TicketStatus
from app.models.event import Event
from app.models.event_reschedule import EventReschedule
from app.models.order import Order
from app.models.push_dispatch import NotificationJob
from app.models.ticket import Ticket
from app.services.event_locations import EventLocationValidationError, validate_event_location
from app.services.event_permissions import EventPermissionAction, has_event_permission


class EventRescheduleError(ValueError):
    pass


class EventRescheduleNotFoundError(EventRescheduleError):
    pass


class EventRescheduleAuthorizationError(EventRescheduleError):
    pass


class EventRescheduleConflictError(EventRescheduleError):
    pass


class EventRescheduleValidationError(EventRescheduleError):
    pass


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _same_instant(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None:
        return left is right
    return _aware(left).astimezone(timezone.utc) == _aware(right).astimezone(timezone.utc)


def _request_matches(row: EventReschedule, payload, location) -> bool:  # noqa: ANN001
    return all((
        _same_instant(row.new_start_at, payload.start_at),
        _same_instant(row.new_end_at, payload.end_at),
        _same_instant(row.new_doors_open_at, payload.doors_open_at),
        _same_instant(row.new_sales_start_at, payload.sales_start_at),
        _same_instant(row.new_sales_end_at, payload.sales_end_at),
        row.new_venue_id == location.venue_id,
        row.new_custom_venue_name == location.custom_venue_name,
        row.new_custom_address_text == location.custom_address_text,
        row.new_latitude == location.latitude,
        row.new_longitude == location.longitude,
        row.new_is_location_pinned == location.is_location_pinned,
        row.reason == payload.reason,
    ))


def _validate(event: Event, payload) -> None:  # noqa: ANN001
    if event.approval_status != EventApprovalStatus.APPROVED:
        raise EventRescheduleValidationError("Only approved events use the Reschedule Event workflow.")
    if event.status == EventStatus.CANCELLED or event.cancelled_at is not None:
        raise EventRescheduleValidationError("Cancelled events cannot be rescheduled.")
    try:
        ZoneInfo(event.timezone or "America/Guyana")
    except ZoneInfoNotFoundError as exc:
        raise EventRescheduleValidationError("Event timezone is invalid and must be corrected before rescheduling.") from exc
    now = datetime.now(timezone.utc)
    if _aware(payload.start_at).astimezone(timezone.utc) <= now:
        raise EventRescheduleValidationError("The new event start must be in the future.")
    if payload.end_at <= payload.start_at:
        raise EventRescheduleValidationError("The new event end must be after its start.")
    if payload.doors_open_at is not None and payload.doors_open_at > payload.start_at:
        raise EventRescheduleValidationError("Doors must open before or at the event start.")
    if payload.sales_start_at is not None and payload.sales_end_at is not None and payload.sales_end_at <= payload.sales_start_at:
        raise EventRescheduleValidationError("Sales must end after they start.")
    if payload.sales_end_at is not None and payload.sales_end_at > payload.start_at:
        raise EventRescheduleValidationError("Sales must end before or at the event start.")


def reschedule_event(db: Session, *, event_id: int, actor_user_id: int, payload) -> tuple[Event, EventReschedule, bool]:  # noqa: ANN001
    event = db.execute(select(Event).where(Event.id == event_id).with_for_update()).scalar_one_or_none()
    if event is None:
        raise EventRescheduleNotFoundError("Event not found.")
    if not has_event_permission(db, user_id=actor_user_id, event=event, action=EventPermissionAction.EDIT_EVENT):
        raise EventRescheduleAuthorizationError("Only the event creator or an administrator may reschedule this event.")
    try:
        location, venue = validate_event_location(
            db,
            venue_id=payload.venue_id,
            custom_venue_name=payload.custom_venue_name,
            custom_address_text=payload.custom_address_text,
            latitude=payload.latitude,
            longitude=payload.longitude,
            is_location_pinned=payload.is_location_pinned,
        )
    except EventLocationValidationError as exc:
        raise EventRescheduleValidationError(str(exc)) from exc

    existing = db.execute(
        select(EventReschedule).where(
            EventReschedule.event_id == event_id,
            EventReschedule.idempotency_key == payload.idempotency_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if not _request_matches(existing, payload, location):
            raise EventRescheduleConflictError("The idempotency key was already used for a different reschedule.")
        notifications_required = db.execute(
            select(NotificationJob.id).where(NotificationJob.dedupe_key == f"event-reschedule:{existing.id}")
        ).scalar_one_or_none() is not None
        return event, existing, notifications_required

    _validate(event, payload)
    schedule_changed = not all((
        _same_instant(event.start_at, payload.start_at),
        _same_instant(event.end_at, payload.end_at),
        _same_instant(event.doors_open_at, payload.doors_open_at),
        _same_instant(event.sales_start_at, payload.sales_start_at),
        _same_instant(event.sales_end_at, payload.sales_end_at),
    ))
    venue_changed = any((
        event.venue_id != location.venue_id,
        event.custom_venue_name != location.custom_venue_name,
        event.custom_address_text != location.custom_address_text,
        event.latitude != location.latitude,
        event.longitude != location.longitude,
        bool(event.is_location_pinned) != location.is_location_pinned,
    ))
    if not schedule_changed and not venue_changed:
        raise EventRescheduleValidationError("The material change must modify the event schedule or venue.")

    now = datetime.now(timezone.utc)
    row = EventReschedule(
        event_id=event.id,
        actor_user_id=actor_user_id,
        idempotency_key=payload.idempotency_key,
        reason=payload.reason,
        previous_start_at=event.start_at,
        previous_end_at=event.end_at,
        previous_doors_open_at=event.doors_open_at,
        previous_sales_start_at=event.sales_start_at,
        previous_sales_end_at=event.sales_end_at,
        new_start_at=payload.start_at,
        new_end_at=payload.end_at,
        new_doors_open_at=payload.doors_open_at,
        new_sales_start_at=payload.sales_start_at,
        new_sales_end_at=payload.sales_end_at,
        previous_venue_id=event.venue_id,
        new_venue_id=location.venue_id,
        previous_custom_venue_name=event.custom_venue_name,
        new_custom_venue_name=location.custom_venue_name,
        previous_custom_address_text=event.custom_address_text,
        new_custom_address_text=location.custom_address_text,
        previous_latitude=event.latitude,
        new_latitude=location.latitude,
        previous_longitude=event.longitude,
        new_longitude=location.longitude,
        previous_is_location_pinned=bool(event.is_location_pinned),
        new_is_location_pinned=location.is_location_pinned,
        rescheduled_at=now,
    )
    db.add(row)
    db.flush()

    event.start_at = payload.start_at
    event.end_at = payload.end_at
    event.doors_open_at = payload.doors_open_at
    event.sales_start_at = payload.sales_start_at
    event.sales_end_at = payload.sales_end_at
    event.venue_id = location.venue_id
    event.venue = venue
    event.custom_venue_name = location.custom_venue_name
    event.custom_address_text = location.custom_address_text
    event.latitude = location.latitude
    event.longitude = location.longitude
    event.is_location_pinned = location.is_location_pinned
    event.updated_at = now
    db.add(AdminActionAudit(
        actor_user_id=actor_user_id,
        target_type="event",
        target_id=str(event.id),
        action_type="reschedule_event",
        reason=payload.reason,
        metadata_json={
            "reschedule_id": row.id,
            "previous_start_at": _aware(row.previous_start_at).isoformat(),
            "previous_end_at": _aware(row.previous_end_at).isoformat(),
            "new_start_at": _aware(row.new_start_at).isoformat(),
            "new_end_at": _aware(row.new_end_at).isoformat(),
            "previous_venue_id": row.previous_venue_id,
            "new_venue_id": row.new_venue_id,
            "previous_custom_venue_name": row.previous_custom_venue_name,
            "new_custom_venue_name": row.new_custom_venue_name,
        },
    ))

    affected = int(db.execute(
        select(func.count(Ticket.id))
        .join(Order, Order.id == Ticket.order_id)
        .where(
            Ticket.event_id == event.id,
            Ticket.status.in_([TicketStatus.ISSUED, TicketStatus.CHECKED_IN]),
            Order.status == OrderStatus.COMPLETED,
            Order.refund_status != "refunded",
        )
    ).scalar_one() or 0)
    notifications_required = affected > 0
    if notifications_required:
        db.execute(
            pg_insert(NotificationJob)
            .values(
                job_type="event_reschedule",
                dedupe_key=f"event-reschedule:{row.id}",
                related_entity_id=row.id,
                status="pending",
                run_at=now,
            )
            .on_conflict_do_nothing(index_elements=[NotificationJob.dedupe_key])
        )
    db.flush()
    return event, row, notifications_required
