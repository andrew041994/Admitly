from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import EventApprovalStatus, EventStatus, OrderStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.ticket_hold import TicketHold
from app.models.ticket_tier import TicketTier

GUYANA_TZ = ZoneInfo("America/Guyana")


class TicketHoldError(ValueError):
    """Base business-rule error for ticket holds."""


class TicketHoldWindowClosedError(TicketHoldError):
    """Raised when event start is inside hold restriction window."""


class InsufficientAvailabilityError(TicketHoldError):
    """Raised when requested ticket quantity exceeds current availability."""


@dataclass(slots=True)
class HoldCreationResult:
    hold: TicketHold
    availability_remaining: int


def _to_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_guyana_now() -> datetime:
    return datetime.now(tz=GUYANA_TZ)


def calculate_ticket_hold_expiry(event_starts_at: datetime, now: datetime | None = None) -> datetime:
    current = _to_aware(now) if now is not None else get_guyana_now()
    current_guyana = current.astimezone(GUYANA_TZ)
    event_start_guyana = _to_aware(event_starts_at).astimezone(GUYANA_TZ)

    if event_start_guyana <= current_guyana + timedelta(hours=8):
        raise TicketHoldWindowClosedError(
            "Ticket holds are not allowed within 8 hours of event start."
        )

    return min(current_guyana + timedelta(hours=48), event_start_guyana - timedelta(hours=8))


def get_ticket_type_availability(db: Session, ticket_tier_id: int, now: datetime | None = None) -> int:
    reference_now = _to_aware(now) if now is not None else get_guyana_now()

    ticket_tier = db.execute(
        select(TicketTier).where(TicketTier.id == ticket_tier_id)
    ).scalar_one_or_none()
    if ticket_tier is None:
        raise TicketHoldError("Ticket tier not found.")

    completed_sold = (
        db.execute(
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .where(OrderItem.ticket_tier_id == ticket_tier_id, Order.status == OrderStatus.COMPLETED)
        ).scalar_one()
        or 0
    )

    active_holds = (
        db.execute(
            select(func.coalesce(func.sum(TicketHold.quantity), 0)).where(
                TicketHold.ticket_tier_id == ticket_tier_id,
                TicketHold.expires_at > reference_now,
            )
        ).scalar_one()
        or 0
    )

    return max(ticket_tier.quantity_total - int(completed_sold) - int(active_holds), 0)


def create_ticket_hold(
    db: Session,
    *,
    user_id: int,
    ticket_tier_id: int,
    quantity: int,
    now: datetime | None = None,
) -> HoldCreationResult:
    if quantity <= 0:
        raise TicketHoldError("Quantity must be greater than 0.")

    reference_now = _to_aware(now) if now is not None else get_guyana_now()

    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        ticket_tier = db.execute(
            select(TicketTier)
            .options(joinedload(TicketTier.event))
            .where(TicketTier.id == ticket_tier_id)
            .with_for_update()
        ).scalar_one_or_none()

        if ticket_tier is None:
            raise TicketHoldError("Ticket tier not found.")

        event = ticket_tier.event
        if not ticket_tier.is_active:
            raise TicketHoldError("Ticket tier is not active.")
        if event.status != EventStatus.PUBLISHED or event.approval_status != EventApprovalStatus.APPROVED:
            raise TicketHoldError("Event is not currently sellable.")

        availability = get_ticket_type_availability(db, ticket_tier_id=ticket_tier_id, now=reference_now)
        if quantity > availability:
            raise InsufficientAvailabilityError("Insufficient availability for requested quantity.")

        expires_at = calculate_ticket_hold_expiry(event.start_at, now=reference_now)

        hold = TicketHold(
            event_id=event.id,
            ticket_tier_id=ticket_tier.id,
            user_id=user_id,
            quantity=quantity,
            expires_at=expires_at,
        )
        db.add(hold)
        db.flush()

    db.refresh(hold)
    return HoldCreationResult(hold=hold, availability_remaining=availability - quantity)
