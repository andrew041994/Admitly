from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
import logging

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.admin_action_audit import AdminActionAudit
from app.models.dispute import Dispute
from app.models.enums import OrderStatus, PricingSource, SupportCasePriority, SupportCaseStatus, TransferInviteStatus
from app.models.order import Order
from app.models.promo_code_redemption import PromoCodeRedemption
from app.models.refund import Refund
from app.models.support_case import SupportCase
from app.models.support_case_note import SupportCaseNote
from app.models.ticket import Ticket
from app.models.ticket_transfer_invite import TicketTransferInvite
from app.services.finance_reporting import mark_order_reconciled
from app.services.notifications import notify_order_completed, notify_ticket_transfer_invite_created, notify_tickets_issued


class SupportError(ValueError):
    pass


class SupportNotFoundError(SupportError):
    pass


class SupportConflictError(SupportError):
    pass


ACTIVE_CASE_STATUSES = {
    SupportCaseStatus.OPEN,
    SupportCaseStatus.INVESTIGATING,
    SupportCaseStatus.WAITING_ON_CUSTOMER,
    SupportCaseStatus.WAITING_ON_PAYMENT_PROVIDER,
    SupportCaseStatus.RESOLVED,
}


SENSITIVE_ACTIONS = {"reopen_refund_review", "flag_for_fraud_review", "remove_promo_application"}
logger = logging.getLogger(__name__)


@dataclass
class SupportActionResult:
    action_type: str
    success: bool
    message: str


def _trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _audit(
    db: Session,
    *,
    actor_user_id: int,
    target_type: str,
    target_id: str,
    action_type: str,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AdminActionAudit:
    row = AdminActionAudit(
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        action_type=action_type,
        reason=_trimmed(reason),
        metadata_json=metadata,
    )
    db.add(row)
    db.flush()
    return row


def get_or_create_support_case_for_order(
    db: Session,
    order_id: int,
    *,
    category: str | None = None,
    created_by_user_id: int | None = None,
) -> SupportCase:
    active = db.execute(
        select(SupportCase)
        .where(SupportCase.order_id == order_id, SupportCase.status.in_(tuple(ACTIVE_CASE_STATUSES)))
        .order_by(SupportCase.created_at.desc(), SupportCase.id.desc())
    ).scalars().first()
    if active is not None:
        return active

    case = SupportCase(order_id=order_id, category=category or "other", created_by_user_id=created_by_user_id)
    db.add(case)
    db.flush()
    return case


def get_relevant_support_case_for_order(db: Session, *, order_id: int) -> SupportCase | None:
    active = db.execute(
        select(SupportCase)
        .where(SupportCase.order_id == order_id, SupportCase.status.in_(tuple(ACTIVE_CASE_STATUSES)))
        .order_by(SupportCase.created_at.desc(), SupportCase.id.desc())
    ).scalars().first()
    if active is not None:
        return active
    return db.execute(
        select(SupportCase).where(SupportCase.order_id == order_id).order_by(SupportCase.created_at.desc(), SupportCase.id.desc())
    ).scalars().first()


def add_support_case_note(
    db: Session,
    *,
    order_id: int,
    author_user_id: int,
    body: str,
    is_system_note: bool = False,
) -> SupportCaseNote:
    normalized = _trimmed(body)
    if not normalized:
        raise SupportError("Note body cannot be blank.")
    case = get_or_create_support_case_for_order(db, order_id, created_by_user_id=author_user_id)
    note = SupportCaseNote(support_case_id=case.id, author_user_id=author_user_id, body=normalized, is_system_note=is_system_note)
    db.add(note)
    db.flush()
    _audit(
        db,
        actor_user_id=author_user_id,
        target_type="support_case",
        target_id=str(case.id),
        action_type="support_note_added",
        metadata={"order_id": order_id, "note_id": note.id, "is_system_note": is_system_note},
    )
    return note


def patch_support_case(
    db: Session,
    *,
    order_id: int,
    actor_user_id: int,
    status: SupportCaseStatus | None,
    priority: SupportCasePriority | None,
    assigned_to_user_id: int | None,
    category: str | None,
) -> SupportCase:
    case = get_or_create_support_case_for_order(db, order_id, created_by_user_id=actor_user_id)

    if status is not None and status != case.status:
        before = case.status.value
        case.status = status
        if status in {SupportCaseStatus.RESOLVED, SupportCaseStatus.CLOSED}:
            case.closed_at = case.closed_at or case.updated_at
        else:
            case.closed_at = None
        db.flush()
        add_support_case_note(
            db,
            order_id=order_id,
            author_user_id=actor_user_id,
            body=f"System: case status changed from {before} to {status.value}.",
            is_system_note=True,
        )
        _audit(
            db,
            actor_user_id=actor_user_id,
            target_type="support_case",
            target_id=str(case.id),
            action_type="support_case_status_changed",
            metadata={"before": before, "after": status.value, "order_id": order_id},
        )

    if priority is not None and priority != case.priority:
        before = case.priority.value
        case.priority = priority
        db.flush()
        _audit(
            db,
            actor_user_id=actor_user_id,
            target_type="support_case",
            target_id=str(case.id),
            action_type="support_case_priority_changed",
            metadata={"before": before, "after": priority.value, "order_id": order_id},
        )

    if assigned_to_user_id is not None and assigned_to_user_id != case.assigned_to_user_id:
        before = case.assigned_to_user_id
        case.assigned_to_user_id = assigned_to_user_id
        db.flush()
        _audit(
            db,
            actor_user_id=actor_user_id,
            target_type="support_case",
            target_id=str(case.id),
            action_type="support_case_assigned",
            metadata={"before": before, "after": assigned_to_user_id, "order_id": order_id},
        )

    if category is not None:
        normalized = _trimmed(category)
        if not normalized:
            raise SupportError("Case category cannot be blank.")
        if normalized != case.category:
            before = case.category
            case.category = normalized
            db.flush()
            _audit(
                db,
                actor_user_id=actor_user_id,
                target_type="support_case",
                target_id=str(case.id),
                action_type="support_case_category_changed",
                metadata={"before": before, "after": normalized, "order_id": order_id},
            )

    db.flush()
    return case


def build_order_support_timeline(db: Session, order_id: int) -> list[dict[str, Any]]:
    order = db.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()
    if order is None:
        raise SupportNotFoundError("Order not found.")

    rows: list[dict[str, Any]] = [
        {
            "timestamp": order.created_at,
            "type": "order",
            "title": "Order created",
            "description": f"Order #{order.id} created with status {order.status.value}.",
            "actor": f"user:{order.user_id}",
            "metadata": {"total_amount": str(order.total_amount), "currency": order.currency},
        }
    ]
    if order.payment_submitted_at:
        rows.append({"timestamp": order.payment_submitted_at, "type": "payment", "title": "Payment submitted", "description": f"Payment reference {order.payment_reference or 'n/a'} submitted.", "actor": None, "metadata": None})
    if order.paid_at:
        rows.append({"timestamp": order.paid_at, "type": "payment", "title": "Payment captured", "description": "Order marked paid.", "actor": None, "metadata": None})
    if order.refunded_at:
        rows.append({"timestamp": order.refunded_at, "type": "refund", "title": "Order refunded", "description": f"Refund status {order.refund_status}.", "actor": f"user:{order.refunded_by_user_id}" if order.refunded_by_user_id else None, "metadata": None})

    refunds = db.execute(select(Refund).where(Refund.order_id == order_id)).scalars().all()
    for refund in refunds:
        rows.append({"timestamp": refund.created_at, "type": "refund", "title": "Refund record", "description": f"Refund #{refund.id} {refund.status.value} for {refund.amount}.", "actor": f"user:{refund.user_id}", "metadata": {"refund_id": refund.id}})

    disputes = db.execute(select(Dispute).where(Dispute.order_id == order_id)).scalars().all()
    for dispute in disputes:
        rows.append({"timestamp": dispute.created_at, "type": "dispute", "title": "Dispute opened", "description": f"Dispute #{dispute.id} status {dispute.status.value}.", "actor": f"user:{dispute.user_id}", "metadata": {"dispute_id": dispute.id}})

    invites = db.execute(
        select(TicketTransferInvite)
        .join(Ticket, Ticket.id == TicketTransferInvite.ticket_id)
        .where(Ticket.order_id == order_id)
    ).scalars().all()
    for invite in invites:
        rows.append({"timestamp": invite.created_at, "type": "transfer", "title": "Transfer invite", "description": f"Invite #{invite.id} status {invite.status.value}.", "actor": f"user:{invite.sender_user_id}", "metadata": {"invite_id": invite.id}})

    case = get_relevant_support_case_for_order(db, order_id=order_id)
    if case is not None:
        rows.append({"timestamp": case.created_at, "type": "support_case", "title": "Support case opened", "description": f"Case #{case.id} {case.status.value} ({case.category}).", "actor": f"user:{case.created_by_user_id}" if case.created_by_user_id else "system", "metadata": {"support_case_id": case.id}})
        notes = db.execute(
            select(SupportCaseNote).where(SupportCaseNote.support_case_id == case.id).order_by(SupportCaseNote.created_at.asc(), SupportCaseNote.id.asc())
        ).scalars().all()
        for note in notes:
            rows.append({"timestamp": note.created_at, "type": "support_note", "title": "Support note", "description": note.body, "actor": f"user:{note.author_user_id}", "metadata": {"note_id": note.id, "is_system_note": note.is_system_note}})

    audits = db.execute(
        select(AdminActionAudit).where(
            or_(
                and_(AdminActionAudit.target_type == "order", AdminActionAudit.target_id == str(order_id)),
                and_(AdminActionAudit.target_type == "support_case", AdminActionAudit.target_id == str(case.id if case else "")),
            )
        )
    ).scalars().all()
    for audit in audits:
        rows.append({"timestamp": audit.created_at, "type": "admin_audit", "title": audit.action_type, "description": audit.reason or "Admin action recorded.", "actor": f"user:{audit.actor_user_id}", "metadata": audit.metadata_json})

    rows.sort(key=lambda item: item["timestamp"])
    return rows


def run_admin_support_action(
    db: Session,
    *,
    order_id: int,
    actor_user_id: int,
    action_type: str,
    reason: str | None,
    payload: dict[str, Any] | None = None,
) -> SupportActionResult:
    normalized_action = _trimmed(action_type)
    if normalized_action is None:
        raise SupportError("action_type is required.")
    normalized_reason = _trimmed(reason)
    if normalized_action in SENSITIVE_ACTIONS and not normalized_reason:
        raise SupportError("reason is required for this action.")

    order = db.execute(select(Order).options(joinedload(Order.tickets)).where(Order.id == order_id)).unique().scalar_one_or_none()
    if order is None:
        raise SupportNotFoundError("Order not found.")

    if normalized_action == "resend_confirmation":
        if order.status != OrderStatus.COMPLETED:
            result = SupportActionResult(action_type=normalized_action, success=True, message="No-op: order not completed.")
        else:
            completed = notify_order_completed(db, order)
            tickets = notify_tickets_issued(db, order, list(order.tickets))
            ok = completed.success and tickets.success
            result = SupportActionResult(action_type=normalized_action, success=ok, message="Confirmation resend attempted.")

    elif normalized_action == "resend_transfer_invite":
        invite = db.execute(
            select(TicketTransferInvite)
            .join(Ticket, Ticket.id == TicketTransferInvite.ticket_id)
            .where(Ticket.order_id == order_id)
            .order_by(TicketTransferInvite.created_at.desc(), TicketTransferInvite.id.desc())
        ).scalars().first()
        if invite is None or invite.status != TransferInviteStatus.PENDING:
            raise SupportConflictError("No pending transfer invite available.")
        notify_ticket_transfer_invite_created(invite)
        result = SupportActionResult(action_type=normalized_action, success=True, message="Transfer invite resent.")

    elif normalized_action == "reopen_refund_review":
        existing_case = get_relevant_support_case_for_order(db, order_id=order_id)
        if (
            existing_case is not None
            and existing_case.status == SupportCaseStatus.INVESTIGATING
            and existing_case.category == "refund_issue"
        ):
            result = SupportActionResult(action_type=normalized_action, success=True, message="No-op: refund review already open.")
            logger.info("Support action no-op", extra={"action": normalized_action, "order_id": order_id})
        else:
            patch_support_case(
                db,
                order_id=order_id,
                actor_user_id=actor_user_id,
                status=SupportCaseStatus.INVESTIGATING,
                priority=None,
                assigned_to_user_id=None,
                category="refund_issue",
            )
            add_support_case_note(
                db,
                order_id=order_id,
                author_user_id=actor_user_id,
                body="System: refund review reopened by admin action.",
                is_system_note=True,
            )
            result = SupportActionResult(action_type=normalized_action, success=True, message="Refund review reopened.")

    elif normalized_action == "flag_for_fraud_review":
        existing_case = get_relevant_support_case_for_order(db, order_id=order_id)
        if (
            existing_case is not None
            and existing_case.status == SupportCaseStatus.INVESTIGATING
            and existing_case.priority == SupportCasePriority.HIGH
            and existing_case.category == "fraud_review"
        ):
            result = SupportActionResult(action_type=normalized_action, success=True, message="No-op: order already flagged for fraud review.")
            logger.info("Support action no-op", extra={"action": normalized_action, "order_id": order_id})
        else:
            patch_support_case(
                db,
                order_id=order_id,
                actor_user_id=actor_user_id,
                status=SupportCaseStatus.INVESTIGATING,
                priority=SupportCasePriority.HIGH,
                assigned_to_user_id=None,
                category="fraud_review",
            )
            add_support_case_note(
                db,
                order_id=order_id,
                author_user_id=actor_user_id,
                body="System: order flagged for fraud review.",
                is_system_note=True,
            )
            result = SupportActionResult(action_type=normalized_action, success=True, message="Order flagged for fraud review.")

    elif normalized_action == "remove_promo_application":
        if order.status != OrderStatus.PENDING:
            raise SupportConflictError("Promo application cannot be removed after order leaves pending status.")
        if order.pricing_source != PricingSource.PROMO_CODE:
            raise SupportConflictError("Order does not have a removable promo application.")
        before_discount = str(order.discount_amount)
        order.discount_amount = Decimal("0.00")
        order.total_amount = Decimal(order.subtotal_amount)
        order.promo_code_id = None
        order.promo_code_text = None
        order.discount_type = None
        order.discount_value_snapshot = None
        order.pricing_source = PricingSource.STANDARD
        redemption = db.execute(select(PromoCodeRedemption).where(PromoCodeRedemption.order_id == order.id)).scalar_one_or_none()
        if redemption is not None:
            db.delete(redemption)
        db.flush()
        result = SupportActionResult(action_type=normalized_action, success=True, message="Promo application removed.")
        _audit(
            db,
            actor_user_id=actor_user_id,
            target_type="order",
            target_id=str(order_id),
            action_type=normalized_action,
            reason=normalized_reason,
            metadata={"before_discount": before_discount, "after_discount": str(order.discount_amount)},
        )
        return result

    elif normalized_action == "re-run_reconciliation":
        mark_order_reconciled(db, order_id=order_id, actor_user_id=actor_user_id, note=normalized_reason)
        result = SupportActionResult(action_type=normalized_action, success=True, message="Reconciliation service executed.")

    else:
        raise SupportError("Unsupported action_type.")

    _audit(
        db,
        actor_user_id=actor_user_id,
        target_type="order",
        target_id=str(order_id),
        action_type=normalized_action,
        reason=normalized_reason,
        metadata={"success": result.success, "message": result.message, "payload": payload or {}},
    )
    return result
