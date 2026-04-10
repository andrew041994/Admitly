from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.event import Event
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


@dataclass(slots=True, frozen=True)
class TicketTierCapacitySummary:
    ticket_tier_id: int
    total_capacity: int
    committed_quantity: int
    active_hold_quantity: int
    available_quantity: int


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


def get_ticket_tier_capacity_summary(
    db: Session,
    *,
    ticket_tier_id: int,
    now: datetime | None = None,
) -> TicketTierCapacitySummary:
    reference_now = _to_aware(now) if now is not None else get_guyana_now()
    if now is None:
        reference_now = datetime.combine(reference_now.date(), time.min, tzinfo=reference_now.tzinfo)

    ticket_tier = db.execute(select(TicketTier).where(TicketTier.id == ticket_tier_id)).scalar_one_or_none()
    if ticket_tier is None:
        raise TicketHoldError("Ticket tier not found.")

    committed_quantity = (
        db.execute(
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .where(OrderItem.ticket_tier_id == ticket_tier_id, Order.status == OrderStatus.COMPLETED)
        ).scalar_one()
        or 0
    )
    active_hold_quantity = (
        db.execute(
            select(func.coalesce(func.sum(TicketHold.quantity), 0))
            .select_from(TicketHold)
            .outerjoin(Order, Order.id == TicketHold.order_id)
            .where(
                TicketHold.ticket_tier_id == ticket_tier_id,
                (
                    (TicketHold.order_id.is_(None))
                    & (TicketHold.expires_at > reference_now)
                )
                | (
                    (TicketHold.order_id.is_not(None))
                    & (TicketHold.expires_at > reference_now)
                    & (Order.status.in_([OrderStatus.PENDING, OrderStatus.AWAITING_PAYMENT, OrderStatus.PAYMENT_SUBMITTED, OrderStatus.FAILED]))
                ),
            )
        ).scalar_one()
        or 0
    )

    available_quantity = max(ticket_tier.quantity_total - int(committed_quantity) - int(active_hold_quantity), 0)
    return TicketTierCapacitySummary(
        ticket_tier_id=ticket_tier.id,
        total_capacity=int(ticket_tier.quantity_total),
        committed_quantity=int(committed_quantity),
        active_hold_quantity=int(active_hold_quantity),
        available_quantity=int(available_quantity),
    )


def get_ticket_type_availability(db: Session, ticket_tier_id: int, now: datetime | None = None) -> int:
    return get_ticket_tier_capacity_summary(db, ticket_tier_id=ticket_tier_id, now=now).available_quantity


def get_event_ticket_tier_capacity_summaries(
    db: Session,
    *,
    event_id: int,
    now: datetime | None = None,
) -> list[TicketTierCapacitySummary]:
    tier_ids = db.execute(
        select(TicketTier.id).where(TicketTier.event_id == event_id).order_by(TicketTier.sort_order.asc(), TicketTier.id.asc())
    ).scalars().all()
    return [get_ticket_tier_capacity_summary(db, ticket_tier_id=tier_id, now=now) for tier_id in tier_ids]


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

    ticket_tier = db.execute(
        select(TicketTier)
        .where(TicketTier.id == ticket_tier_id)
        .with_for_update()
    ).scalar_one_or_none()

    if ticket_tier is None:
        raise TicketHoldError("Ticket tier not found.")

    event = db.execute(select(Event).where(Event.id == ticket_tier.event_id)).scalar_one_or_none()
    if event is None:
        raise TicketHoldError("Event not found.")
    if not ticket_tier.is_active:
        raise TicketHoldError("Ticket tier is not active.")
    if event.status != EventStatus.PUBLISHED or event.approval_status != EventApprovalStatus.APPROVED:
        raise TicketHoldError("Event is not currently sellable.")

    availability_summary = get_ticket_tier_capacity_summary(db, ticket_tier_id=ticket_tier_id, now=reference_now)
    availability = availability_summary.available_quantity
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
