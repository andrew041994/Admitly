from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.enums import OrderStatus, TicketStatus
from app.models.event import Event
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.organizer_profile import OrganizerProfile
from app.models.ticket import Ticket
from app.models.ticket_hold import TicketHold
from app.models.ticket_tier import TicketTier
from app.models.user import User
from app.services.ticket_holds import get_guyana_now


class EventReportingError(ValueError):
    """Base reporting error."""


class EventReportingNotFoundError(EventReportingError):
    """Raised when the target event does not exist."""


class EventReportingAuthorizationError(EventReportingError):
    """Raised when actor cannot view organizer reporting."""


@dataclass(frozen=True)
class EventSummaryData:
    event_id: int
    event_title: str
    event_status: str
    starts_at: datetime
    ends_at: datetime | None
    gross_revenue: Decimal
    refunded_amount: Decimal
    net_revenue: Decimal
    completed_order_count: int
    pending_order_count: int
    cancelled_order_count: int
    refunded_order_count: int
    tickets_sold_count: int
    tickets_issued_count: int
    tickets_checked_in_count: int
    tickets_voided_count: int
    tickets_remaining_count: int
    check_in_rate: float
    total_capacity: int
    generated_at: datetime


@dataclass(frozen=True)
class TierSummaryRow:
    ticket_tier_id: int
    name: str
    price: Decimal
    currency: str
    configured_quantity: int
    sold_count: int
    active_hold_count: int
    issued_count: int
    checked_in_count: int
    voided_count: int
    remaining_count: int
    gross_revenue: Decimal


@dataclass(frozen=True)
class OrganizerOrderRow:
    order_id: int
    user_id: int
    status: str
    refund_status: str
    payment_provider: str | None
    payment_method: str | None
    total_amount: Decimal
    currency: str
    item_count: int
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None
    refunded_at: datetime | None


@dataclass(frozen=True)
class OrganizerTicketRow:
    ticket_id: int
    order_id: int
    order_item_id: int
    ticket_tier_id: int
    purchaser_user_id: int
    owner_user_id: int
    status: str
    transfer_count: int
    ticket_code: str
    issued_at: datetime
    checked_in_at: datetime | None
    checked_in_by_user_id: int | None
    voided_at: datetime | None


@dataclass(frozen=True)
class CheckInSummaryData:
    event_id: int
    total_checked_in: int
    total_not_checked_in: int
    first_check_in_at: datetime | None
    last_check_in_at: datetime | None
    check_in_rate: float


@dataclass(frozen=True)
class CheckInRow:
    ticket_id: int
    ticket_tier_id: int
    checked_in_at: datetime
    checked_in_by_user_id: int | None
    purchaser_user_id: int
    owner_user_id: int
    order_id: int


def validate_event_reporting_access(db: Session, *, user_id: int, event_id: int) -> Event:
    event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if event is None:
        raise EventReportingNotFoundError("Event not found.")

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise EventReportingAuthorizationError("Not authorized to view event reporting.")
    if user.is_admin:
        return event

    organizer_user_id = db.execute(
        select(OrganizerProfile.user_id).where(OrganizerProfile.id == event.organizer_id)
    ).scalar_one_or_none()
    if organizer_user_id != user_id:
        raise EventReportingAuthorizationError("Not authorized to view event reporting.")
    return event


def get_event_reporting_summary(db: Session, *, event_id: int) -> EventSummaryData:
    event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if event is None:
        raise EventReportingNotFoundError("Event not found.")

    order_stats = db.execute(
        select(
            func.coalesce(func.sum(case((Order.status == OrderStatus.COMPLETED, Order.total_amount), else_=0)), 0),
            func.count(case((Order.status == OrderStatus.COMPLETED, 1))),
            func.count(case((Order.status == OrderStatus.PENDING, 1))),
            func.count(case((Order.status == OrderStatus.CANCELLED, 1))),
            func.count(case((Order.refund_status == "refunded", 1))),
            func.coalesce(func.sum(case((Order.refund_status == "refunded", Order.total_amount), else_=0)), 0),
        ).where(Order.event_id == event_id)
    ).one()

    sold_count = db.execute(
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.event_id == event_id, Order.status == OrderStatus.COMPLETED)
    ).scalar_one()

    ticket_stats = db.execute(
        select(
            func.count(Ticket.id),
            func.count(case((Ticket.status == TicketStatus.CHECKED_IN, 1))),
            func.count(case((Ticket.status == TicketStatus.VOIDED, 1))),
        ).where(Ticket.event_id == event_id)
    ).one()

    total_capacity = db.execute(
        select(func.coalesce(func.sum(TicketTier.quantity_total), 0)).where(TicketTier.event_id == event_id)
    ).scalar_one()

    active_hold_count = db.execute(
        select(func.coalesce(func.sum(TicketHold.quantity), 0)).where(
            TicketHold.event_id == event_id,
            TicketHold.order_id.is_(None),
            TicketHold.expires_at > get_guyana_now(),
        )
    ).scalar_one()

    gross_revenue = Decimal(order_stats[0] or 0)
    refunded_amount = Decimal(order_stats[5] or 0)
    net_revenue = gross_revenue - refunded_amount
    tickets_issued_count = int(ticket_stats[0] or 0)
    tickets_checked_in_count = int(ticket_stats[1] or 0)
    tickets_voided_count = int(ticket_stats[2] or 0)
    remaining = max(int(total_capacity or 0) - int(sold_count or 0) - int(active_hold_count or 0), 0)

    return EventSummaryData(
        event_id=event.id,
        event_title=event.title,
        event_status=event.status.value,
        starts_at=event.start_at,
        ends_at=event.end_at,
        gross_revenue=gross_revenue,
        refunded_amount=refunded_amount,
        net_revenue=net_revenue,
        completed_order_count=int(order_stats[1] or 0),
        pending_order_count=int(order_stats[2] or 0),
        cancelled_order_count=int(order_stats[3] or 0),
        refunded_order_count=int(order_stats[4] or 0),
        tickets_sold_count=int(sold_count or 0),
        tickets_issued_count=tickets_issued_count,
        tickets_checked_in_count=tickets_checked_in_count,
        tickets_voided_count=tickets_voided_count,
        tickets_remaining_count=remaining,
        check_in_rate=(tickets_checked_in_count / tickets_issued_count) if tickets_issued_count else 0.0,
        total_capacity=int(total_capacity or 0),
        generated_at=get_guyana_now(),
    )


def get_event_tier_summary(db: Session, *, event_id: int) -> list[TierSummaryRow]:
    active_now = get_guyana_now()

    sold_by_tier = (
        select(
            OrderItem.ticket_tier_id.label("ticket_tier_id"),
            func.coalesce(func.sum(OrderItem.quantity), 0).label("sold_count"),
            func.coalesce(func.sum(OrderItem.quantity * OrderItem.unit_price), 0).label("gross_revenue"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.event_id == event_id, Order.status == OrderStatus.COMPLETED)
        .group_by(OrderItem.ticket_tier_id)
        .subquery()
    )

    holds_by_tier = (
        select(
            TicketHold.ticket_tier_id.label("ticket_tier_id"),
            func.coalesce(func.sum(TicketHold.quantity), 0).label("active_hold_count"),
        )
        .where(
            TicketHold.event_id == event_id,
            TicketHold.order_id.is_(None),
            TicketHold.expires_at > active_now,
        )
        .group_by(TicketHold.ticket_tier_id)
        .subquery()
    )

    tickets_by_tier = (
        select(
            Ticket.ticket_tier_id.label("ticket_tier_id"),
            func.count(Ticket.id).label("issued_count"),
            func.count(case((Ticket.status == TicketStatus.CHECKED_IN, 1))).label("checked_in_count"),
            func.count(case((Ticket.status == TicketStatus.VOIDED, 1))).label("voided_count"),
        )
        .where(Ticket.event_id == event_id)
        .group_by(Ticket.ticket_tier_id)
        .subquery()
    )

    rows = db.execute(
        select(
            TicketTier.id,
            TicketTier.name,
            TicketTier.price_amount,
            TicketTier.currency,
            TicketTier.quantity_total,
            func.coalesce(sold_by_tier.c.sold_count, 0),
            func.coalesce(holds_by_tier.c.active_hold_count, 0),
            func.coalesce(tickets_by_tier.c.issued_count, 0),
            func.coalesce(tickets_by_tier.c.checked_in_count, 0),
            func.coalesce(tickets_by_tier.c.voided_count, 0),
            func.coalesce(sold_by_tier.c.gross_revenue, 0),
        )
        .where(TicketTier.event_id == event_id)
        .outerjoin(sold_by_tier, sold_by_tier.c.ticket_tier_id == TicketTier.id)
        .outerjoin(holds_by_tier, holds_by_tier.c.ticket_tier_id == TicketTier.id)
        .outerjoin(tickets_by_tier, tickets_by_tier.c.ticket_tier_id == TicketTier.id)
        .order_by(TicketTier.sort_order.asc(), TicketTier.id.asc())
    ).all()

    result: list[TierSummaryRow] = []
    for row in rows:
        remaining = max(int(row[4]) - int(row[5]) - int(row[6]), 0)
        result.append(
            TierSummaryRow(
                ticket_tier_id=row[0],
                name=row[1],
                price=Decimal(row[2]),
                currency=row[3],
                configured_quantity=row[4],
                sold_count=int(row[5]),
                active_hold_count=int(row[6]),
                issued_count=int(row[7]),
                checked_in_count=int(row[8]),
                voided_count=int(row[9]),
                remaining_count=remaining,
                gross_revenue=Decimal(row[10] or 0),
            )
        )

    return result


def list_event_orders_for_organizer(
    db: Session,
    *,
    event_id: int,
    status: OrderStatus | None = None,
    refund_status: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[OrganizerOrderRow]:
    item_counts = (
        select(
            OrderItem.order_id.label("order_id"),
            func.coalesce(func.sum(OrderItem.quantity), 0).label("item_count"),
        )
        .group_by(OrderItem.order_id)
        .subquery()
    )

    conditions = [Order.event_id == event_id]
    if status is not None:
        conditions.append(Order.status == status)
    if refund_status is not None:
        conditions.append(Order.refund_status == refund_status)
    if created_after is not None:
        conditions.append(Order.created_at >= created_after)
    if created_before is not None:
        conditions.append(Order.created_at <= created_before)

    rows = db.execute(
        select(
            Order.id,
            Order.user_id,
            Order.status,
            Order.refund_status,
            Order.payment_provider,
            Order.payment_method,
            Order.total_amount,
            Order.currency,
            func.coalesce(item_counts.c.item_count, 0),
            Order.created_at,
            Order.updated_at,
            Order.cancelled_at,
            Order.refunded_at,
        )
        .where(and_(*conditions))
        .outerjoin(item_counts, item_counts.c.order_id == Order.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return [
        OrganizerOrderRow(
            order_id=row[0],
            user_id=row[1],
            status=row[2].value,
            refund_status=row[3],
            payment_provider=row[4],
            payment_method=row[5],
            total_amount=Decimal(row[6]),
            currency=row[7],
            item_count=int(row[8]),
            created_at=row[9],
            updated_at=row[10],
            cancelled_at=row[11],
            refunded_at=row[12],
        )
        for row in rows
    ]


def list_event_tickets_for_organizer(
    db: Session,
    *,
    event_id: int,
    status: TicketStatus | None = None,
    owner_user_id: int | None = None,
    purchaser_user_id: int | None = None,
    ticket_tier_id: int | None = None,
    checked_in: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[OrganizerTicketRow]:
    conditions = [Ticket.event_id == event_id]
    if status is not None:
        conditions.append(Ticket.status == status)
    if owner_user_id is not None:
        conditions.append(Ticket.owner_user_id == owner_user_id)
    if purchaser_user_id is not None:
        conditions.append(Ticket.purchaser_user_id == purchaser_user_id)
    if ticket_tier_id is not None:
        conditions.append(Ticket.ticket_tier_id == ticket_tier_id)
    if checked_in is True:
        conditions.append(Ticket.status == TicketStatus.CHECKED_IN)
    if checked_in is False:
        conditions.append(Ticket.status != TicketStatus.CHECKED_IN)

    rows = db.execute(
        select(
            Ticket.id,
            Ticket.order_id,
            Ticket.order_item_id,
            Ticket.ticket_tier_id,
            Ticket.purchaser_user_id,
            Ticket.owner_user_id,
            Ticket.status,
            Ticket.transfer_count,
            Ticket.ticket_code,
            Ticket.issued_at,
            Ticket.checked_in_at,
            Ticket.checked_in_by_user_id,
            Ticket.voided_at,
        )
        .where(and_(*conditions))
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return [
        OrganizerTicketRow(
            ticket_id=row[0],
            order_id=row[1],
            order_item_id=row[2],
            ticket_tier_id=row[3],
            purchaser_user_id=row[4],
            owner_user_id=row[5],
            status=row[6].value,
            transfer_count=row[7],
            ticket_code=row[8],
            issued_at=row[9],
            checked_in_at=row[10],
            checked_in_by_user_id=row[11],
            voided_at=row[12],
        )
        for row in rows
    ]


def get_event_checkin_summary(db: Session, *, event_id: int) -> CheckInSummaryData:
    totals = db.execute(
        select(
            func.count(Ticket.id),
            func.count(case((Ticket.status == TicketStatus.CHECKED_IN, 1))),
            func.min(Ticket.checked_in_at),
            func.max(Ticket.checked_in_at),
        ).where(Ticket.event_id == event_id)
    ).one()

    total_tickets = int(totals[0] or 0)
    checked_in = int(totals[1] or 0)
    return CheckInSummaryData(
        event_id=event_id,
        total_checked_in=checked_in,
        total_not_checked_in=max(total_tickets - checked_in, 0),
        first_check_in_at=totals[2],
        last_check_in_at=totals[3],
        check_in_rate=(checked_in / total_tickets) if total_tickets else 0.0,
    )


def list_event_checkins(
    db: Session,
    *,
    event_id: int,
    checked_in_by_user_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CheckInRow]:
    conditions = [Ticket.event_id == event_id, Ticket.status == TicketStatus.CHECKED_IN]
    if checked_in_by_user_id is not None:
        conditions.append(Ticket.checked_in_by_user_id == checked_in_by_user_id)
    if since is not None:
        conditions.append(Ticket.checked_in_at >= since)
    if until is not None:
        conditions.append(Ticket.checked_in_at <= until)

    rows = db.execute(
        select(
            Ticket.id,
            Ticket.ticket_tier_id,
            Ticket.checked_in_at,
            Ticket.checked_in_by_user_id,
            Ticket.purchaser_user_id,
            Ticket.owner_user_id,
            Ticket.order_id,
        )
        .where(and_(*conditions))
        .order_by(Ticket.checked_in_at.desc(), Ticket.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return [
        CheckInRow(
            ticket_id=row[0],
            ticket_tier_id=row[1],
            checked_in_at=row[2],
            checked_in_by_user_id=row[3],
            purchaser_user_id=row[4],
            owner_user_id=row[5],
            order_id=row[6],
        )
        for row in rows
    ]
