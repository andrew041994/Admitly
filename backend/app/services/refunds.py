from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.dispute import Dispute
from app.models.enums import (
    BalanceAdjustmentType,
    DisputeStatus,
    FinancialEntryType,
    OrderStatus,
    PayoutStatus,
    RefundReason,
    RefundStatus,
    TicketStatus,
)
from app.models.financial_entry import FinancialEntry
from app.models.order import Order
from app.models.organizer_balance_adjustment import OrganizerBalanceAdjustment
from app.models.refund import Refund
from app.models.user import User
from app.services.tickets import invalidate_order_tickets


class RefundDisputeError(ValueError):
    pass


class RefundNotFoundError(RefundDisputeError):
    pass


class DisputeNotFoundError(RefundDisputeError):
    pass


class RefundAuthorizationError(RefundDisputeError):
    pass


class RefundValidationError(RefundDisputeError):
    pass


class DisputeValidationError(RefundDisputeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _assert_admin(db: Session, *, actor_user_id: int) -> None:
    user = db.execute(select(User).where(User.id == actor_user_id)).scalar_one_or_none()
    if user is None or not user.is_admin:
        raise RefundAuthorizationError("Admin access required.")


def get_order_total_refunded(db: Session, *, order_id: int) -> Decimal:
    total = db.execute(
        select(func.coalesce(func.sum(Refund.amount), 0)).where(
            Refund.order_id == order_id,
            Refund.status == RefundStatus.PROCESSED,
        )
    ).scalar_one()
    return Decimal(total or 0)


def get_order_refundable_amount(order: Order) -> Decimal:
    return Decimal(order.total_amount)


def get_order_remaining_refundable(db: Session, *, order: Order) -> Decimal:
    remaining = get_order_refundable_amount(order) - get_order_total_refunded(db, order_id=order.id)
    if remaining < Decimal("0.00"):
        return Decimal("0.00")
    return remaining


def is_order_refundable(order: Order, now: datetime | None = None) -> bool:
    if order.status != OrderStatus.COMPLETED:
        return False
    if order.payment_verification_status != "verified":
        return False
    if order.is_comp or Decimal(order.total_amount) <= Decimal("0.00"):
        return False
    reference_now = now or _now()
    event_end = order.event.end_at
    if event_end.tzinfo is None:
        event_end = event_end.replace(tzinfo=timezone.utc)
    return event_end > reference_now


def validate_refund_request(
    db: Session,
    *,
    order: Order,
    requested_amount: Decimal,
    reason: RefundReason,
    admin_override: bool = False,
) -> None:
    remaining = get_order_remaining_refundable(db, order=order)
    if requested_amount <= Decimal("0.00"):
        raise RefundValidationError("Refund amount must be greater than zero.")
    if remaining <= Decimal("0.00"):
        raise RefundValidationError("Order is already fully refunded.")
    if requested_amount > remaining:
        raise RefundValidationError("Refund amount exceeds remaining refundable amount.")
    if order.is_comp or Decimal(order.total_amount) <= Decimal("0.00"):
        raise RefundValidationError("Comped/free orders are not refundable.")
    if order.status != OrderStatus.COMPLETED or order.payment_verification_status != "verified":
        raise RefundValidationError("Only completed verified-paid orders are refundable.")

    event_end = order.event.end_at
    if event_end.tzinfo is None:
        event_end = event_end.replace(tzinfo=timezone.utc)
    if event_end <= _now() and reason != RefundReason.EVENT_CANCELED and not admin_override:
        raise RefundValidationError("Refunds after event end require event_canceled reason or admin override.")


def request_refund(
    db: Session,
    *,
    user_id: int,
    order_id: int,
    reason: RefundReason,
    amount: Decimal | None,
    note: str | None,
) -> Refund:
    order = (
        db.execute(select(Order).options(joinedload(Order.event)).where(Order.id == order_id).with_for_update())
        .unique()
        .scalar_one_or_none()
    )
    if order is None:
        raise RefundNotFoundError("Order not found.")
    if order.user_id != user_id:
        raise RefundAuthorizationError("Order does not belong to the authenticated user.")

    requested_amount = amount if amount is not None else get_order_remaining_refundable(db, order=order)
    validate_refund_request(db, order=order, requested_amount=requested_amount, reason=reason)

    refund = Refund(
        order_id=order.id,
        user_id=user_id,
        amount=requested_amount,
        reason=reason,
        status=RefundStatus.PENDING,
        admin_notes=note.strip() if note else None,
    )
    db.add(refund)
    db.flush()
    return refund


def _process_refund_locked(
    db: Session,
    *,
    refund: Refund,
    order: Order,
    actor_user_id: int,
    admin_notes: str | None,
) -> Refund:
    if refund.status not in {RefundStatus.PENDING, RefundStatus.APPROVED}:
        raise RefundValidationError("Only pending/approved refunds can be processed.")

    validate_refund_request(
        db,
        order=order,
        requested_amount=Decimal(refund.amount),
        reason=refund.reason,
        admin_override=True,
    )

    now = _now()
    refund.status = RefundStatus.PROCESSED
    refund.approved_by_user_id = actor_user_id
    refund.admin_notes = admin_notes.strip() if admin_notes else refund.admin_notes
    refund.processed_at = now

    db.add(
        FinancialEntry(
            order_id=order.id,
            refund_id=refund.id,
            organizer_id=order.event.organizer_id,
            amount=-Decimal(refund.amount),
            entry_type=FinancialEntryType.REFUND_REVERSAL,
        )
    )

    if order.payout_status == PayoutStatus.PAID or order.payout_paid_at is not None:
        db.add(
            OrganizerBalanceAdjustment(
                organizer_id=order.event.organizer_id,
                order_id=order.id,
                refund_id=refund.id,
                amount=-Decimal(refund.amount),
                adjustment_type=BalanceAdjustmentType.REFUND_OFFSET,
                note="Refund processed after payout paid",
            )
        )

    total_refunded = get_order_total_refunded(db, order_id=order.id) + Decimal(refund.amount)
    if total_refunded >= Decimal(order.total_amount):
        order.refund_status = "refunded"
        order.refunded_at = now
        order.refunded_by_user_id = actor_user_id
        order.refund_reason = refund.reason.value
        if not any(ticket.status == TicketStatus.CHECKED_IN for ticket in order.tickets):
            invalidate_order_tickets(
                db,
                order_id=order.id,
                actor_user_id=actor_user_id,
                reason=f"Order refunded ({refund.reason.value})",
            )

    db.flush()
    return refund


def approve_refund(
    db: Session,
    *,
    refund_id: int,
    actor_user_id: int,
    amount: Decimal | None,
    admin_notes: str | None,
) -> Refund:
    _assert_admin(db, actor_user_id=actor_user_id)
    refund = db.execute(select(Refund).where(Refund.id == refund_id).with_for_update()).scalar_one_or_none()
    if refund is None:
        raise RefundNotFoundError("Refund not found.")
    if refund.status != RefundStatus.PENDING:
        raise RefundValidationError("Only pending refunds can be approved.")

    order = (
        db.execute(
            select(Order)
            .options(joinedload(Order.event), joinedload(Order.tickets))
            .where(Order.id == refund.order_id)
            .with_for_update()
        )
        .unique()
        .scalar_one()
    )

    if amount is not None:
        validate_refund_request(db, order=order, requested_amount=amount, reason=refund.reason, admin_override=True)
        refund.amount = amount

    refund.status = RefundStatus.APPROVED
    refund.approved_by_user_id = actor_user_id
    refund.admin_notes = admin_notes.strip() if admin_notes else refund.admin_notes
    db.flush()
    return _process_refund_locked(db, refund=refund, order=order, actor_user_id=actor_user_id, admin_notes=admin_notes)


def reject_refund(db: Session, *, refund_id: int, actor_user_id: int, admin_notes: str) -> Refund:
    _assert_admin(db, actor_user_id=actor_user_id)
    refund = db.execute(select(Refund).where(Refund.id == refund_id).with_for_update()).scalar_one_or_none()
    if refund is None:
        raise RefundNotFoundError("Refund not found.")
    if refund.status != RefundStatus.PENDING:
        raise RefundValidationError("Only pending refunds can be rejected.")
    refund.status = RefundStatus.REJECTED
    refund.admin_notes = admin_notes.strip()
    refund.rejection_reason = admin_notes.strip()
    db.flush()
    return refund


def list_user_refunds(db: Session, *, user_id: int) -> list[Refund]:
    return db.execute(select(Refund).where(Refund.user_id == user_id).order_by(Refund.created_at.desc())).scalars().all()


def list_refunds(db: Session, *, status: RefundStatus | None = None) -> list[Refund]:
    query = select(Refund)
    if status is not None:
        query = query.where(Refund.status == status)
    return db.execute(query.order_by(Refund.created_at.desc())).scalars().all()


def submit_dispute(db: Session, *, user_id: int, order_id: int, message: str) -> Dispute:
    order = db.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()
    if order is None:
        raise DisputeNotFoundError("Order not found.")
    if order.user_id != user_id:
        raise RefundAuthorizationError("Order does not belong to the authenticated user.")

    active = db.execute(
        select(Dispute).where(
            Dispute.order_id == order_id,
            Dispute.user_id == user_id,
            Dispute.status.in_([DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW]),
        )
    ).scalar_one_or_none()
    if active is not None:
        raise DisputeValidationError("An active dispute already exists for this order.")

    dispute = Dispute(order_id=order_id, user_id=user_id, message=message.strip(), status=DisputeStatus.OPEN)
    db.add(dispute)
    db.flush()
    return dispute


def list_disputes(db: Session, *, status: DisputeStatus | None = None) -> list[Dispute]:
    query = select(Dispute)
    if status is not None:
        query = query.where(Dispute.status == status)
    return db.execute(query.order_by(Dispute.created_at.desc())).scalars().all()


def resolve_dispute(
    db: Session,
    *,
    dispute_id: int,
    actor_user_id: int,
    resolution: str | None,
    admin_notes: str | None,
    refund_amount: Decimal | None,
    refund_reason: RefundReason | None,
) -> Dispute:
    _assert_admin(db, actor_user_id=actor_user_id)
    dispute = db.execute(select(Dispute).where(Dispute.id == dispute_id).with_for_update()).scalar_one_or_none()
    if dispute is None:
        raise DisputeNotFoundError("Dispute not found.")
    if dispute.status in {DisputeStatus.RESOLVED, DisputeStatus.REJECTED}:
        raise DisputeValidationError("Dispute is already closed.")

    dispute.status = DisputeStatus.RESOLVED
    dispute.resolution = resolution.strip() if resolution else None
    dispute.admin_notes = admin_notes.strip() if admin_notes else None
    dispute.resolved_by_user_id = actor_user_id
    dispute.resolved_at = _now()

    if refund_amount is not None:
        reason = refund_reason or RefundReason.OTHER
        refund = Refund(
            order_id=dispute.order_id,
            user_id=dispute.user_id,
            amount=refund_amount,
            reason=reason,
            status=RefundStatus.APPROVED,
            approved_by_user_id=actor_user_id,
            admin_notes="Dispute resolution refund",
        )
        db.add(refund)
        db.flush()
        order = (
            db.execute(
                select(Order)
                .options(joinedload(Order.event), joinedload(Order.tickets))
                .where(Order.id == dispute.order_id)
                .with_for_update()
            )
            .unique()
            .scalar_one()
        )
        _process_refund_locked(db, refund=refund, order=order, actor_user_id=actor_user_id, admin_notes=admin_notes)

    db.flush()
    return dispute


def reject_dispute(db: Session, *, dispute_id: int, actor_user_id: int, admin_notes: str) -> Dispute:
    _assert_admin(db, actor_user_id=actor_user_id)
    dispute = db.execute(select(Dispute).where(Dispute.id == dispute_id).with_for_update()).scalar_one_or_none()
    if dispute is None:
        raise DisputeNotFoundError("Dispute not found.")
    if dispute.status in {DisputeStatus.RESOLVED, DisputeStatus.REJECTED}:
        raise DisputeValidationError("Dispute is already closed.")
    dispute.status = DisputeStatus.REJECTED
    dispute.admin_notes = admin_notes.strip()
    dispute.resolution = admin_notes.strip()
    dispute.resolved_by_user_id = actor_user_id
    dispute.resolved_at = _now()
    db.flush()
    return dispute
