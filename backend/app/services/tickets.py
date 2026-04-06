from __future__ import annotations

import secrets

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.event import Event
from app.models.event_staff import EventStaff
from app.models.enums import OrderStatus, TicketStatus
from app.models.order import Order
from app.models.ticket import Ticket
from app.models.user import User
from app.services.notifications import notify_ticket_transferred, notify_ticket_voided, notify_tickets_issued
from app.services.ticket_holds import get_guyana_now


class TicketError(ValueError):
    """Base ticket error."""


class TicketIssuanceError(TicketError):
    """Raised when tickets cannot be safely issued."""


class TicketNotFoundError(TicketError):
    """Raised when ticket cannot be found."""


class TicketAuthorizationError(TicketError):
    """Raised when actor lacks permission."""


class TicketCheckInConflictError(TicketError):
    """Raised when ticket cannot transition during check-in."""


class TicketCrossEventError(TicketError):
    """Raised when ticket does not belong to route event."""


class TicketTransferError(TicketError):
    """Raised when a transfer request is invalid."""


class TicketVoidError(TicketError):
    """Raised when a void request is invalid."""


def _generate_ticket_code() -> str:
    return secrets.token_urlsafe(24)

def issue_tickets_for_completed_order(db: Session, order: Order) -> list[Ticket]:
    if order is None:
        raise TicketIssuanceError("Order is required.")
    if order.status != OrderStatus.COMPLETED:
        raise TicketIssuanceError("Only completed orders can issue tickets.")
    if order.payment_verification_status != "verified":
        raise TicketIssuanceError("Order payment is not verified.")

    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        locked_order = (
            db.execute(
                select(Order)
                .options(joinedload(Order.order_items))
                .where(Order.id == order.id)
                .with_for_update()
            )
            .unique()
            .scalar_one()
        )

        expected_total = sum(item.quantity for item in locked_order.order_items)
        existing_tickets = (
            db.execute(select(Ticket).where(Ticket.order_id == locked_order.id).order_by(Ticket.id.asc()))
            .scalars()
            .all()
        )
        existing_count = len(existing_tickets)
        if existing_count == expected_total:
            return existing_tickets
        if existing_count != 0:
            raise TicketIssuanceError(
                f"Partial ticket issuance detected for order {locked_order.id}: {existing_count}/{expected_total}."
            )

        now = get_guyana_now()
        tickets_to_create: list[Ticket] = []
        for item in locked_order.order_items:
            for _ in range(item.quantity):
                ticket_code = _generate_ticket_code()
                tickets_to_create.append(
                    Ticket(
                        order_id=locked_order.id,
                        order_item_id=item.id,
                        event_id=locked_order.event_id,
                        user_id=locked_order.user_id,
                        purchaser_user_id=locked_order.user_id,
                        owner_user_id=locked_order.user_id,
                        ticket_tier_id=item.ticket_tier_id,
                        status=TicketStatus.ISSUED,
                        ticket_code=ticket_code,
                        qr_payload=ticket_code,
                        issued_at=now,
                    )
                )

        db.add_all(tickets_to_create)
        db.flush()
        return (
            db.execute(select(Ticket).where(Ticket.order_id == locked_order.id).order_by(Ticket.id.asc()))
            .scalars()
            .all()
        )


def can_void_event_ticket(db: Session, *, user_id: int, event_id: int) -> bool:
    event = (
        db.execute(select(Event).options(joinedload(Event.organizer)).where(Event.id == event_id))
        .unique()
        .scalar_one_or_none()
    )
    if event is None:
        return False
    return event.organizer is not None and event.organizer.user_id == user_id


def validate_ticket_voidable(ticket: Ticket) -> None:
    if ticket.status == TicketStatus.CHECKED_IN:
        raise TicketVoidError("Checked-in tickets cannot be voided.")
    if ticket.status == TicketStatus.VOIDED:
        raise TicketVoidError("Ticket is already voided.")
    if ticket.status != TicketStatus.ISSUED:
        raise TicketVoidError("Ticket is not eligible to be voided.")


def invalidate_order_tickets(
    db: Session,
    *,
    order_id: int,
    actor_user_id: int,
    reason: str | None = None,
) -> list[Ticket]:
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        tickets = (
            db.execute(select(Ticket).where(Ticket.order_id == order_id).with_for_update())
            .scalars()
            .all()
        )

        now = get_guyana_now()
        for ticket in tickets:
            if ticket.status == TicketStatus.ISSUED:
                ticket.status = TicketStatus.VOIDED
                ticket.voided_at = now
                ticket.voided_by_user_id = actor_user_id
                ticket.void_reason = reason.strip() if reason else None
                ticket.updated_at = now
                notify_ticket_voided(db, ticket, actor_user_id=actor_user_id)

        db.flush()
        return tickets


def invalidate_event_tickets(
    db: Session,
    *,
    event_id: int,
    actor_user_id: int,
    reason: str | None = None,
) -> list[Ticket]:
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        tickets = (
            db.execute(select(Ticket).where(Ticket.event_id == event_id).with_for_update())
            .scalars()
            .all()
        )
        now = get_guyana_now()
        for ticket in tickets:
            if ticket.status == TicketStatus.ISSUED:
                ticket.status = TicketStatus.VOIDED
                ticket.voided_at = now
                ticket.voided_by_user_id = actor_user_id
                ticket.void_reason = reason.strip() if reason else None
                ticket.updated_at = now
                notify_ticket_voided(db, ticket, actor_user_id=actor_user_id)

        db.flush()
        return tickets


def list_tickets_for_user(db: Session, *, user_id: int, event_id: int | None = None) -> list[Ticket]:
    conditions = [Ticket.owner_user_id == user_id]
    if event_id is not None:
        conditions.append(Ticket.event_id == event_id)

    return (
        db.execute(select(Ticket).where(and_(*conditions)).order_by(Ticket.created_at.desc(), Ticket.id.desc()))
        .scalars()
        .all()
    )


def list_tickets_for_order_owner(db: Session, *, order_id: int, user_id: int) -> list[Ticket]:
    order = db.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()
    if order is None:
        raise TicketNotFoundError("Order not found.")
    if order.user_id != user_id:
        raise TicketAuthorizationError("Order does not belong to the authenticated user.")

    return (
        db.execute(select(Ticket).where(Ticket.order_id == order_id).order_by(Ticket.id.asc()))
        .scalars()
        .all()
    )


def validate_ticket_transferable(ticket: Ticket, *, current_user_id: int) -> None:
    if ticket.owner_user_id != current_user_id:
        raise TicketAuthorizationError("Only the current ticket owner can transfer this ticket.")
    if ticket.status == TicketStatus.CHECKED_IN:
        raise TicketTransferError("Checked-in tickets cannot be transferred.")
    if ticket.status == TicketStatus.VOIDED:
        raise TicketTransferError("Voided tickets cannot be transferred.")
    if ticket.status != TicketStatus.ISSUED:
        raise TicketTransferError("Ticket is not eligible for transfer.")


def transfer_ticket_to_user(
    db: Session,
    *,
    ticket_id: int,
    from_user_id: int,
    to_user_id: int,
) -> Ticket:
    if from_user_id == to_user_id:
        raise TicketTransferError("Cannot transfer a ticket to yourself.")

    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        ticket = (
            db.execute(select(Ticket).where(Ticket.id == ticket_id).with_for_update())
            .scalars()
            .first()
        )
        if ticket is None:
            raise TicketNotFoundError("Ticket not found.")

        validate_ticket_transferable(ticket, current_user_id=from_user_id)

        user = db.execute(select(User.id).where(User.id == to_user_id)).scalar_one_or_none()
        if user is None:
            raise TicketTransferError("Recipient user not found.")

        now = get_guyana_now()
        ticket.owner_user_id = to_user_id
        ticket.user_id = to_user_id
        ticket.transferred_at = now
        ticket.transfer_count += 1
        ticket.updated_at = now
        db.flush()
        notify_ticket_transferred(db, ticket, from_user_id=from_user_id, to_user_id=to_user_id)
        return ticket


def void_ticket(
    db: Session,
    *,
    ticket_id: int,
    actor_user_id: int,
    reason: str | None = None,
) -> Ticket:
    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        ticket = (
            db.execute(select(Ticket).where(Ticket.id == ticket_id).with_for_update())
            .scalars()
            .first()
        )
        if ticket is None:
            raise TicketNotFoundError("Ticket not found.")
        if not can_void_event_ticket(db, user_id=actor_user_id, event_id=ticket.event_id):
            raise TicketAuthorizationError("Not authorized to void tickets for this event.")

        validate_ticket_voidable(ticket)

        now = get_guyana_now()
        ticket.status = TicketStatus.VOIDED
        ticket.voided_at = now
        ticket.voided_by_user_id = actor_user_id
        ticket.void_reason = reason.strip() if reason else None
        ticket.updated_at = now
        db.flush()
        notify_ticket_voided(db, ticket, actor_user_id=actor_user_id)
        return ticket


def can_check_in_event_tickets(db: Session, *, user_id: int, event_id: int) -> bool:
    event = (
        db.execute(select(Event).options(joinedload(Event.organizer)).where(Event.id == event_id))
        .unique()
        .scalar_one_or_none()
    )
    if event is None:
        return False
    if event.organizer and event.organizer.user_id == user_id:
        return True

    staff_assignment = db.execute(
        select(EventStaff.id).where(
            EventStaff.event_id == event_id,
            EventStaff.user_id == user_id,
            EventStaff.is_active.is_(True),
        )
    ).scalar_one_or_none()
    return staff_assignment is not None


def check_in_ticket_for_event(
    db: Session,
    *,
    scanner_user_id: int,
    event_id: int,
    qr_payload: str | None,
    ticket_code: str | None,
) -> Ticket:
    if not can_check_in_event_tickets(db, user_id=scanner_user_id, event_id=event_id):
        raise TicketAuthorizationError("Not authorized to check in tickets for this event.")

    raw_lookup = (ticket_code or qr_payload or "").strip()
    if not raw_lookup:
        raise TicketNotFoundError("A ticket code or QR payload is required.")

    tx_ctx = db.begin_nested() if db.in_transaction() else db.begin()
    with tx_ctx:
        ticket = (
            db.execute(
                select(Ticket)
                .where(or_(Ticket.ticket_code == raw_lookup, Ticket.qr_payload == raw_lookup))
                .with_for_update()
            )
            .scalars()
            .first()
        )

        if ticket is None:
            raise TicketNotFoundError("Ticket not found.")
        if ticket.event_id != event_id:
            raise TicketCrossEventError("Ticket does not belong to this event.")
        if ticket.status == TicketStatus.VOIDED:
            raise TicketCheckInConflictError("Ticket is voided and cannot be checked in.")
        if ticket.status == TicketStatus.CHECKED_IN:
            raise TicketCheckInConflictError("Ticket has already been checked in.")
        if ticket.status != TicketStatus.ISSUED:
            raise TicketCheckInConflictError("Ticket is not eligible for check-in.")

        now = get_guyana_now()
        ticket.status = TicketStatus.CHECKED_IN
        ticket.checked_in_at = now
        ticket.checked_in_by_user_id = scanner_user_id
        ticket.updated_at = now
        db.flush()
        return ticket


def resend_ticket_notification(
    db: Session,
    *,
    ticket_id: int,
    actor_user_id: int,
):
    ticket = db.execute(select(Ticket).where(Ticket.id == ticket_id)).scalar_one_or_none()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found.")
    if ticket.owner_user_id != actor_user_id:
        raise TicketAuthorizationError("Only the current ticket owner can resend ticket notifications.")

    return notify_tickets_issued(db, ticket.order, [ticket])
