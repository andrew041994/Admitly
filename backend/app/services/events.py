from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.event import Event
from app.models.event_refund_batch import EventRefundBatch
from app.models.enums import EventRefundBatchStatus, EventStatus, OrderStatus, RefundReason
from app.models.order import Order
from app.models.user import User
from app.services.event_permissions import EventPermissionAction, has_event_permission
from app.services.notifications import notify_event_cancelled
from app.services.refunds import (
    RefundValidationError,
    get_order_remaining_refundable,
    process_refund_for_order,
)
from app.services.tickets import invalidate_event_tickets
from app.services.ticket_holds import get_guyana_now

BATCH_CHUNK_SIZE = 50


class EventFlowError(ValueError):
    """Base event flow error."""


class EventNotFoundError(EventFlowError):
    """Raised when event does not exist."""


class EventAuthorizationError(EventFlowError):
    """Raised when actor is not allowed to manage event."""


class EventCancellationError(EventFlowError):
    """Raised when event cancellation request is invalid."""


def enqueue_event_refund_batch(
    db: Session,
    *,
    event_id: int,
    actor_user_id: int,
) -> EventRefundBatch:
    existing = db.execute(
        select(EventRefundBatch)
        .where(
            EventRefundBatch.event_id == event_id,
            EventRefundBatch.status.in_([EventRefundBatchStatus.PENDING, EventRefundBatchStatus.PROCESSING]),
        )
        .order_by(EventRefundBatch.id.desc())
    ).scalars().first()
    if existing is not None:
        return existing

    batch = EventRefundBatch(
        event_id=event_id,
        initiated_by_user_id=actor_user_id,
        status=EventRefundBatchStatus.PENDING,
    )
    db.add(batch)
    db.flush()
    return batch


def get_event_refundable_orders(db: Session, *, event_id: int) -> list[Order]:
    return (
        db.execute(
            select(Order)
            .options(joinedload(Order.event), joinedload(Order.tickets))
            .where(
                Order.event_id == event_id,
                Order.status == OrderStatus.COMPLETED,
                Order.payment_verification_status == "verified",
            )
            .order_by(Order.id.asc())
        )
        .unique()
        .scalars()
        .all()
    )


def process_event_refund_batch_chunk(
    db: Session,
    *,
    batch: EventRefundBatch,
    orders: list[Order],
    actor_user_id: int,
) -> None:
    for order in orders:
        batch.processed_orders += 1
        remaining = get_order_remaining_refundable(db, order=order)
        if order.is_comp or Decimal(order.total_amount) <= Decimal("0.00") or remaining <= Decimal("0.00"):
            batch.skipped_orders += 1
            continue
        try:
            process_refund_for_order(
                db,
                order_id=order.id,
                actor_user_id=actor_user_id,
                reason=RefundReason.EVENT_CANCELED,
                amount=remaining,
                admin_notes=f"Auto-refund for cancelled event #{batch.event_id}",
            )
            batch.successful_refunds += 1
        except RefundValidationError:
            batch.skipped_orders += 1
        except Exception as exc:  # noqa: BLE001
            batch.failed_orders += 1
            batch.last_error = str(exc)


def process_event_refund_batch(
    db: Session,
    *,
    batch_id: int,
    actor_user_id: int,
) -> EventRefundBatch:
    batch = db.execute(select(EventRefundBatch).where(EventRefundBatch.id == batch_id).with_for_update()).scalar_one_or_none()
    if batch is None:
        raise EventNotFoundError("Refund batch not found.")
    if batch.status == EventRefundBatchStatus.COMPLETED:
        return batch

    try:
        if batch.status == EventRefundBatchStatus.PENDING:
            batch.status = EventRefundBatchStatus.PROCESSING
            batch.started_at = get_guyana_now()

        orders = get_event_refundable_orders(db, event_id=batch.event_id)
        batch.total_orders = len(orders)

        for idx in range(0, len(orders), BATCH_CHUNK_SIZE):
            process_event_refund_batch_chunk(
                db,
                batch=batch,
                orders=orders[idx : idx + BATCH_CHUNK_SIZE],
                actor_user_id=actor_user_id,
            )
            db.flush()

        batch.status = EventRefundBatchStatus.COMPLETED
        batch.completed_at = get_guyana_now()
    except Exception as exc:  # noqa: BLE001
        batch.status = EventRefundBatchStatus.FAILED
        batch.last_error = str(exc)
        batch.completed_at = get_guyana_now()

    db.flush()
    return batch


def list_event_refund_batches(
    db: Session,
    *,
    status: EventRefundBatchStatus | None = None,
    event_id: int | None = None,
) -> list[EventRefundBatch]:
    query = select(EventRefundBatch)
    if status is not None:
        query = query.where(EventRefundBatch.status == status)
    if event_id is not None:
        query = query.where(EventRefundBatch.event_id == event_id)
    return db.execute(query.order_by(EventRefundBatch.created_at.desc())).scalars().all()


def get_event_refund_batch(db: Session, *, batch_id: int) -> EventRefundBatch | None:
    return db.execute(select(EventRefundBatch).where(EventRefundBatch.id == batch_id)).scalar_one_or_none()


def cancel_event(
    db: Session,
    *,
    event_id: int,
    actor_user_id: int,
    reason: str | None = None,
) -> tuple[Event, EventRefundBatch]:
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        event = (
            db.execute(select(Event).where(Event.id == event_id).with_for_update())
            .scalars()
            .first()
        )
        if event is None:
            raise EventNotFoundError("Event not found.")
        if not has_event_permission(
            db,
            user_id=actor_user_id,
            event=event,
            action=EventPermissionAction.CANCEL_EVENT,
        ):
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
        batch = enqueue_event_refund_batch(db, event_id=event.id, actor_user_id=actor_user_id)
        try:
            notify_event_cancelled(event, actor_user_id=actor_user_id)
        except TypeError:
            notify_event_cancelled(db, event, actor_user_id=actor_user_id)

    process_event_refund_batch(db, batch_id=batch.id, actor_user_id=actor_user_id)
    return event, batch
