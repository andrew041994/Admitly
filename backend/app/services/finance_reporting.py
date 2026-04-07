from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.orm import Session

from app.models.enums import OrderStatus, PayoutStatus, ReconciliationStatus, RefundStatus
from app.models.event import Event
from app.models.order import Order
from app.models.organizer_balance_adjustment import OrganizerBalanceAdjustment
from app.models.refund import Refund
from app.models.order_item import OrderItem
from app.models.user import User
from app.services.event_permissions import EventPermissionAction, has_event_permission
from app.services.ticket_holds import get_guyana_now


class FinanceReportingError(ValueError):
    """Base finance reporting error."""


class FinanceReportingNotFoundError(FinanceReportingError):
    """Raised when event/order is not found."""


class FinanceReportingAuthorizationError(FinanceReportingError):
    """Raised when actor cannot view or mutate finance reporting."""


@dataclass(frozen=True)
class EventFinanceSummaryData:
    event_id: int
    event_status: str
    gross_face_value_amount: Decimal
    total_discount_amount: Decimal
    gross_sales_amount: Decimal
    refunded_amount: Decimal
    net_sales_amount: Decimal
    completed_order_count: int
    refunded_order_count: int
    eligible_payout_amount: Decimal
    reconciled_amount: Decimal
    unreconciled_amount: Decimal
    eligible_order_count: int
    reconciled_order_count: int
    unreconciled_order_count: int
    payout_included_amount: Decimal
    payout_paid_amount: Decimal
    comp_order_count: int
    comp_ticket_count: int
    comp_face_value: Decimal
    currency: str
    generated_at: datetime


@dataclass(frozen=True)
class EventFinanceOrderRow:
    order_id: int
    buyer_user_id: int
    status: str
    refund_status: str
    reconciliation_status: str
    payout_status: str
    subtotal_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    is_comp: bool
    pricing_source: str
    refunded_amount: Decimal
    payout_eligible_amount: Decimal
    currency: str
    payment_provider: str | None
    payment_method: str | None
    payment_reference: str | None
    created_at: datetime
    completed_at: datetime | None
    refunded_at: datetime | None
    reconciled_at: datetime | None


@dataclass(frozen=True)
class OrganizerPayoutSummaryData:
    organizer_user_id: int
    total_gross_sales: Decimal
    total_refunded: Decimal
    total_net_sales: Decimal
    total_payout_eligible: Decimal
    total_reconciled: Decimal
    total_unreconciled: Decimal
    total_paid_out: Decimal
    currency: str
    generated_at: datetime


def validate_event_finance_access(db: Session, *, user_id: int, event_id: int) -> Event:
    event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if event is None:
        raise FinanceReportingNotFoundError("Event not found.")
    if not has_event_permission(
        db,
        user_id=user_id,
        event=event,
        action=EventPermissionAction.VIEW_ORDERS,
    ):
        raise FinanceReportingAuthorizationError("Not authorized to view event finance reporting.")
    return event


def validate_organizer_finance_access(db: Session, *, actor_user_id: int, organizer_user_id: int) -> None:
    actor = db.execute(select(User).where(User.id == actor_user_id)).scalar_one_or_none()
    if actor is None:
        raise FinanceReportingAuthorizationError("Not authorized to view organizer finance reporting.")
    if actor.is_admin or actor.id == organizer_user_id:
        return
    raise FinanceReportingAuthorizationError("Not authorized to view organizer finance reporting.")


def _is_verified_paid_order(order: Order) -> bool:
    return order.status == OrderStatus.COMPLETED and order.payment_verification_status == "verified"


def get_order_refunded_amount(order: Order, *, db: Session | None = None) -> Decimal:
    if db is not None:
        total = db.execute(
            select(func.coalesce(func.sum(Refund.amount), 0)).where(
                Refund.order_id == order.id,
                Refund.status == RefundStatus.PROCESSED,
            )
        ).scalar_one()
        refunded = Decimal(total or 0)
        if refunded > Decimal("0.00"):
            return refunded
    if order.refund_status == "refunded":
        return Decimal(order.total_amount)
    return Decimal("0.00")


def get_order_net_amount(order: Order, *, db: Session | None = None) -> Decimal:
    return Decimal(order.total_amount) - get_order_refunded_amount(order, db=db)


def is_order_financially_eligible_for_payout(order: Order) -> bool:
    if not _is_verified_paid_order(order):
        return False
    if order.refund_status == "refunded":
        return False
    if order.reconciliation_status in {ReconciliationStatus.DISPUTED, ReconciliationStatus.EXCLUDED}:
        return False
    if order.payout_status != PayoutStatus.ELIGIBLE:
        return False
    return True


def get_order_payout_eligible_amount(order: Order, *, db: Session | None = None) -> Decimal:
    if not is_order_financially_eligible_for_payout(order):
        return Decimal("0.00")
    return max(Decimal("0.00"), Decimal(order.total_amount) - get_order_refunded_amount(order, db=db))


def _event_order_query(event_id: int) -> Select[tuple[Order]]:
    return select(Order).where(Order.event_id == event_id)


def get_event_finance_summary(db: Session, *, event_id: int) -> EventFinanceSummaryData:
    event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if event is None:
        raise FinanceReportingNotFoundError("Event not found.")

    base_paid = and_(Order.status == OrderStatus.COMPLETED, Order.payment_verification_status == "verified")
    refunded = Order.refund_status == "refunded"
    effective_subtotal = case((Order.subtotal_amount > 0, Order.subtotal_amount), else_=Order.total_amount)

    gross_face_value_amount = Decimal(
        db.execute(select(func.coalesce(func.sum(Order.subtotal_amount), 0)).where(Order.event_id == event_id, base_paid)).scalar_one()
        or 0
    )
    total_discount_amount = Decimal(
        db.execute(select(func.coalesce(func.sum(Order.discount_amount), 0)).where(Order.event_id == event_id, base_paid)).scalar_one()
        or 0
    )
    if gross_face_value_amount == Decimal("0"):
        gross_face_value_amount = Decimal(
            db.execute(select(func.coalesce(func.sum(effective_subtotal), 0)).where(Order.event_id == event_id, base_paid)).scalar_one()
            or 0
        )
    gross_sales_amount = Decimal(
        db.execute(select(func.coalesce(func.sum(Order.total_amount), 0)).where(Order.event_id == event_id, base_paid)).scalar_one()
        or 0
    )
    refunded_amount = Decimal(
        db.execute(
            select(func.coalesce(func.sum(Order.total_amount), 0)).where(Order.event_id == event_id, base_paid, refunded)
        ).scalar_one()
        or 0
    )

    counts = db.execute(
        select(
            func.count(case((base_paid, 1))),
            func.count(case((and_(base_paid, refunded), 1))),
            func.count(case((and_(base_paid, Order.payout_status == PayoutStatus.ELIGIBLE), 1))),
            func.count(case((and_(base_paid, Order.reconciliation_status == ReconciliationStatus.RECONCILED), 1))),
            func.count(case((and_(base_paid, Order.reconciliation_status == ReconciliationStatus.UNRECONCILED), 1))),
        ).where(Order.event_id == event_id)
    ).one()

    reconciled_amount = Decimal(
        db.execute(
            select(func.coalesce(func.sum(Order.total_amount), 0)).where(
                Order.event_id == event_id,
                base_paid,
                Order.reconciliation_status == ReconciliationStatus.RECONCILED,
            )
        ).scalar_one()
        or 0
    )
    unreconciled_amount = Decimal(
        db.execute(
            select(func.coalesce(func.sum(Order.total_amount), 0)).where(
                Order.event_id == event_id,
                base_paid,
                Order.reconciliation_status == ReconciliationStatus.UNRECONCILED,
            )
        ).scalar_one()
        or 0
    )

    payout_included_amount = Decimal(
        db.execute(
            select(func.coalesce(func.sum(Order.total_amount), 0)).where(
                Order.event_id == event_id,
                base_paid,
                Order.payout_status == PayoutStatus.INCLUDED,
            )
        ).scalar_one()
        or 0
    )
    payout_paid_amount = Decimal(
        db.execute(
            select(func.coalesce(func.sum(Order.total_amount), 0)).where(
                Order.event_id == event_id,
                base_paid,
                Order.payout_status == PayoutStatus.PAID,
            )
        ).scalar_one()
        or 0
    )

    orders = db.execute(_event_order_query(event_id)).scalars().all()
    refunded_amount = sum((get_order_refunded_amount(order, db=db) for order in orders if _is_verified_paid_order(order)), Decimal("0.00"))
    refunded_order_count = sum(1 for order in orders if _is_verified_paid_order(order) and get_order_refunded_amount(order, db=db) > Decimal("0.00"))
    eligible_payout_amount = sum(get_order_payout_eligible_amount(order, db=db) for order in orders)

    comp_order_count = int(
        db.execute(select(func.count(Order.id)).where(Order.event_id == event_id, Order.is_comp.is_(True))).scalar_one() or 0
    )
    comp_ticket_count = int(
        db.execute(select(func.coalesce(func.sum(OrderItem.quantity), 0)).join(Order, Order.id == OrderItem.order_id).where(
            Order.event_id == event_id,
            Order.is_comp.is_(True),
            Order.status == OrderStatus.COMPLETED,
        )).scalar_one() or 0
    )
    comp_face_value = Decimal(
        db.execute(select(func.coalesce(func.sum(Order.subtotal_amount), 0)).where(
            Order.event_id == event_id,
            Order.is_comp.is_(True),
            Order.status == OrderStatus.COMPLETED,
        )).scalar_one() or 0
    )
    if comp_face_value == Decimal("0"):
        comp_face_value = Decimal(
            db.execute(select(func.coalesce(func.sum(effective_subtotal), 0)).where(
                Order.event_id == event_id,
                Order.is_comp.is_(True),
                Order.status == OrderStatus.COMPLETED,
            )).scalar_one() or 0
        )

    return EventFinanceSummaryData(
        event_id=event.id,
        event_status=event.status.value,
        gross_face_value_amount=gross_face_value_amount,
        total_discount_amount=total_discount_amount,
        gross_sales_amount=gross_sales_amount,
        refunded_amount=refunded_amount,
        net_sales_amount=gross_sales_amount - refunded_amount,
        completed_order_count=int(counts[0] or 0),
        refunded_order_count=int(refunded_order_count),
        eligible_payout_amount=Decimal(eligible_payout_amount),
        reconciled_amount=reconciled_amount,
        unreconciled_amount=unreconciled_amount,
        eligible_order_count=int(counts[2] or 0),
        reconciled_order_count=int(counts[3] or 0),
        unreconciled_order_count=int(counts[4] or 0),
        payout_included_amount=payout_included_amount,
        payout_paid_amount=payout_paid_amount,
        comp_order_count=comp_order_count,
        comp_ticket_count=comp_ticket_count,
        comp_face_value=comp_face_value,
        currency="GYD",
        generated_at=get_guyana_now(),
    )


def list_event_finance_orders(
    db: Session,
    *,
    event_id: int,
    reconciliation_status: ReconciliationStatus | None = None,
    payout_status: PayoutStatus | None = None,
    refund_status: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[EventFinanceOrderRow]:
    query = select(Order).where(Order.event_id == event_id)

    if reconciliation_status is not None:
        query = query.where(Order.reconciliation_status == reconciliation_status)
    if payout_status is not None:
        query = query.where(Order.payout_status == payout_status)
    if refund_status is not None:
        query = query.where(Order.refund_status == refund_status)
    if created_after is not None:
        query = query.where(Order.created_at >= created_after)
    if created_before is not None:
        query = query.where(Order.created_at <= created_before)

    orders = db.execute(query.order_by(Order.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return [
        EventFinanceOrderRow(
            order_id=order.id,
            buyer_user_id=order.user_id,
            status=order.status.value,
            refund_status=order.refund_status,
            reconciliation_status=order.reconciliation_status.value,
            payout_status=order.payout_status.value,
            subtotal_amount=Decimal(order.subtotal_amount or order.total_amount),
            discount_amount=Decimal(order.discount_amount),
            total_amount=Decimal(order.total_amount),
            is_comp=bool(order.is_comp),
            pricing_source=order.pricing_source.value,
            refunded_amount=get_order_refunded_amount(order, db=db),
            payout_eligible_amount=get_order_payout_eligible_amount(order, db=db),
            currency=order.currency,
            payment_provider=order.payment_provider,
            payment_method=order.payment_method,
            payment_reference=order.payment_reference,
            created_at=order.created_at,
            completed_at=order.paid_at,
            refunded_at=order.refunded_at,
            reconciled_at=order.reconciled_at,
        )
        for order in orders
    ]


def get_organizer_payout_summary(db: Session, *, organizer_user_id: int) -> OrganizerPayoutSummaryData:
    event_ids = db.execute(
        select(Event.id)
        .join(OrganizerProfile, OrganizerProfile.id == Event.organizer_id)
        .where(OrganizerProfile.user_id == organizer_user_id)
    ).scalars().all()

    if not event_ids:
        return OrganizerPayoutSummaryData(
            organizer_user_id=organizer_user_id,
            total_gross_sales=Decimal("0.00"),
            total_refunded=Decimal("0.00"),
            total_net_sales=Decimal("0.00"),
            total_payout_eligible=Decimal("0.00"),
            total_reconciled=Decimal("0.00"),
            total_unreconciled=Decimal("0.00"),
            total_paid_out=Decimal("0.00"),
            currency="GYD",
            generated_at=get_guyana_now(),
        )

    orders = db.execute(select(Order).where(Order.event_id.in_(event_ids))).scalars().all()
    paid_orders = [o for o in orders if _is_verified_paid_order(o)]

    total_gross_sales = sum((Decimal(o.total_amount) for o in paid_orders), Decimal("0.00"))
    total_refunded = sum((get_order_refunded_amount(o, db=db) for o in paid_orders), Decimal("0.00"))
    total_reconciled = sum(
        (Decimal(o.total_amount) for o in paid_orders if o.reconciliation_status == ReconciliationStatus.RECONCILED),
        Decimal("0.00"),
    )
    total_unreconciled = sum(
        (Decimal(o.total_amount) for o in paid_orders if o.reconciliation_status == ReconciliationStatus.UNRECONCILED),
        Decimal("0.00"),
    )
    total_paid_out = sum(
        (Decimal(o.total_amount) for o in paid_orders if o.payout_status == PayoutStatus.PAID),
        Decimal("0.00"),
    )

    return OrganizerPayoutSummaryData(
        organizer_user_id=organizer_user_id,
        total_gross_sales=total_gross_sales,
        total_refunded=total_refunded,
        total_net_sales=total_gross_sales - total_refunded,
        total_payout_eligible=sum((get_order_payout_eligible_amount(o, db=db) for o in orders), Decimal("0.00"))
        + Decimal(db.execute(select(func.coalesce(func.sum(OrganizerBalanceAdjustment.amount), 0)).where(OrganizerBalanceAdjustment.organizer_id.in_(select(OrganizerProfile.id).where(OrganizerProfile.user_id == organizer_user_id)))).scalar_one() or 0),
        total_reconciled=total_reconciled,
        total_unreconciled=total_unreconciled,
        total_paid_out=total_paid_out,
        currency="GYD",
        generated_at=get_guyana_now(),
    )


def mark_order_reconciled(
    db: Session,
    *,
    order_id: int,
    actor_user_id: int,
    note: str | None = None,
) -> Order:
    order = db.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()
    if order is None:
        raise FinanceReportingNotFoundError("Order not found.")

    actor = db.execute(select(User).where(User.id == actor_user_id)).scalar_one_or_none()
    if actor is None or not actor.is_admin:
        raise FinanceReportingAuthorizationError("Only admins can mark orders reconciled.")

    order.reconciliation_status = ReconciliationStatus.RECONCILED
    order.reconciled_at = get_guyana_now()
    order.reconciled_by_user_id = actor_user_id
    order.reconciliation_note = note.strip() if note else None
    db.flush()
    return order


def mark_order_payout_status(
    db: Session,
    *,
    order_id: int,
    actor_user_id: int,
    payout_status: PayoutStatus,
    note: str | None = None,
) -> Order:
    order = db.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()
    if order is None:
        raise FinanceReportingNotFoundError("Order not found.")

    actor = db.execute(select(User).where(User.id == actor_user_id)).scalar_one_or_none()
    if actor is None or not actor.is_admin:
        raise FinanceReportingAuthorizationError("Only admins can update payout status.")

    now = get_guyana_now()
    order.payout_status = payout_status
    order.payout_note = note.strip() if note else None
    if payout_status == PayoutStatus.INCLUDED:
        order.payout_included_at = now
    if payout_status == PayoutStatus.PAID:
        order.payout_paid_at = now
    db.flush()
    return order
    comp_order_count: int
    comp_ticket_count: int
    comp_face_value: Decimal
