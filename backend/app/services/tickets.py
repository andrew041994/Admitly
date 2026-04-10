from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload, object_session

from app.core.config import settings
from app.core.security import normalize_email
from app.models.event import Event
from app.models.enums import (
    CheckInStatus,
    EventStatus,
    OrderStatus,
    TicketScanStatus,
    TicketStatus,
    TransferInviteStatus,
)
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.ticket import Ticket
from app.models.ticket_check_in_attempt import TicketCheckInAttempt
from app.models.ticket_scan_log import TicketScanLog
from app.models.ticket_transfer_invite import TicketTransferInvite
from app.models.user import User
from app.services.event_permissions import EventPermissionAction, has_event_permission_by_id
from app.services.notifications import (
    notify_ticket_transfer_invite_accepted as _notify_ticket_transfer_invite_accepted,
    notify_ticket_transfer_invite_created as _notify_ticket_transfer_invite_created,
    notify_ticket_transfer_invite_revoked as _notify_ticket_transfer_invite_revoked,
    notify_ticket_transferred as _notify_ticket_transferred,
    notify_ticket_voided as _notify_ticket_voided,
    notify_tickets_issued,
)
from app.services.ticket_holds import get_guyana_now
from app.services.ticket_qr import (
    ensure_ticket_qr,
    extract_ticket_lookup_value,
    generate_ticket_display_code,
    generate_ticket_qr_token,
    validate_ticket_qr_signature,
)
from app.services.integrations import build_checkin_payload, build_transfer_payload, publish_webhook_event


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


DEFAULT_TRANSFER_INVITE_TTL = timedelta(days=7)
CHECK_IN_METHOD_QR = "qr"
CHECK_IN_METHOD_MANUAL = "manual"

CHECK_IN_STATUS_VALID = "valid"
CHECK_IN_STATUS_ALREADY_CHECKED_IN = "already_checked_in"
CHECK_IN_STATUS_REFUNDED_OR_INVALIDATED = "refunded_or_invalidated"
CHECK_IN_STATUS_WRONG_EVENT = "wrong_event"
CHECK_IN_STATUS_CANCELED_EVENT = "canceled_event"
CHECK_IN_STATUS_NOT_FOUND = "not_found"
CHECK_IN_STATUS_UNAUTHORIZED = "unauthorized"
CHECK_IN_STATUS_ORDER_NOT_ADMITTABLE = "order_not_admittable"
CHECK_IN_STATUS_INVALID = "invalid"
CHECK_IN_STATUS_TRANSFER_PENDING = "transfer_pending"
CHECK_IN_STATUS_MANUAL_OVERRIDE_ADMITTED = "manual_override_admitted"
CHECK_IN_STATUS_MANUAL_OVERRIDE_DENIED = "manual_override_denied"

CHECK_IN_METHOD_OVERRIDE = "override"


@dataclass
class TicketCheckInValidationResult:
    valid: bool
    status: str
    message: str
    event_id: int
    ticket: Ticket | None = None
    checked_in_at: datetime | None = None
    reason_code: str | None = None


@dataclass
class TicketCheckInSummaryResult:
    event_id: int
    total_admittable_tickets: int
    checked_in_tickets: int
    remaining_tickets: int


@dataclass
class TicketCheckInAttemptRow:
    id: int
    ticket_id: int | None
    event_id: int
    actor_user_id: int | None
    attempted_at: datetime
    result_code: str
    reason_code: str | None
    reason_message: str | None
    method: str | None
    source: str | None
    notes: str | None


@dataclass
class TicketScanResult:
    status: str
    ticket_id: int | None = None
    checked_in_at: datetime | None = None
    message: str | None = None


def _generate_ticket_code() -> str:
    return secrets.token_urlsafe(24)


def _issue_ticket_qr_fields(db: Session) -> tuple[str, str, datetime]:
    for _ in range(10):
        qr_token = generate_ticket_qr_token()
        existing = db.execute(select(Ticket.id).where(Ticket.qr_token == qr_token)).scalar_one_or_none()
        if existing is not None:
            continue
        display_code = generate_ticket_display_code(qr_token=qr_token)
        return qr_token, display_code, get_guyana_now()
    raise TicketIssuanceError("Unable to generate a unique QR token for ticket issuance.")


def notify_ticket_issued(ticket: Ticket) -> None:
    db = object_session(ticket)
    if db is None:
        return
    order = ticket.order
    if order is None:
        return
    notify_tickets_issued(db, order, [ticket])


def notify_ticket_transferred(ticket: Ticket, *, from_user_id: int, to_user_id: int) -> None:
    db = object_session(ticket)
    if db is None:
        return
    _notify_ticket_transferred(db, ticket, from_user_id=from_user_id, to_user_id=to_user_id)


def notify_ticket_voided(ticket: Ticket, *, actor_user_id: int) -> None:
    db = object_session(ticket)
    if db is None:
        return
    _notify_ticket_voided(db, ticket, actor_user_id=actor_user_id)


def notify_ticket_transfer_invite_created(invite: TicketTransferInvite) -> None:
    db = object_session(invite)
    if db is None:
        return
    _notify_ticket_transfer_invite_created(db, invite)


def notify_ticket_transfer_invite_accepted(invite: TicketTransferInvite, ticket: Ticket) -> None:
    db = object_session(invite) or object_session(ticket)
    if db is None:
        return
    _notify_ticket_transfer_invite_accepted(db, invite, ticket)


def notify_ticket_transfer_invite_revoked(invite: TicketTransferInvite) -> None:
    db = object_session(invite)
    if db is None:
        return
    _notify_ticket_transfer_invite_revoked(db, invite)


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _normalize_phone(value: str | None) -> str | None:
    normalized = _normalize_optional(value)
    if normalized is None:
        return None
    return "".join(ch for ch in normalized if ch.isdigit() or ch == "+")


def build_transfer_claim_url(*, invite_token: str) -> str:
    base_url = settings.ticket_public_base_url.rstrip("/")
    return f"{base_url}/tickets/transfers/{invite_token}"


def _generate_transfer_invite_token() -> str:
    return secrets.token_urlsafe(32)


def _create_unique_transfer_invite_token(db: Session) -> str:
    for _ in range(10):
        token = _generate_transfer_invite_token()
        exists = db.execute(select(TicketTransferInvite.id).where(TicketTransferInvite.invite_token == token)).scalar_one_or_none()
        if exists is None:
            return token
    raise TicketTransferError("Unable to generate transfer invite token.")

def issue_tickets_for_completed_order(db: Session, order: Order) -> list[Ticket]:
    if order is None:
        raise TicketIssuanceError("Order is required.")
    if order.status != OrderStatus.COMPLETED:
        raise TicketIssuanceError("Only completed orders can issue tickets.")
    if order.payment_verification_status != "verified":
        raise TicketIssuanceError("Order payment is not verified.")

    locked_order = (
        db.execute(select(Order).where(Order.id == order.id).with_for_update())
        .scalar_one()
    )
    order_items = (
        db.execute(select(OrderItem).where(OrderItem.order_id == locked_order.id).order_by(OrderItem.id.asc()))
        .scalars()
        .all()
    )

    expected_total = sum(item.quantity for item in order_items)
    existing_tickets = (
        db.execute(select(Ticket).where(Ticket.order_id == locked_order.id).order_by(Ticket.id.asc()))
        .scalars()
        .all()
    )
    existing_count = len(existing_tickets)
    if existing_count == expected_total:
        for ticket in existing_tickets:
            if not ticket.qr_token:
                ensure_ticket_qr(db, ticket)
        db.flush()
        return existing_tickets
    if existing_count != 0:
        raise TicketIssuanceError(
            f"Partial ticket issuance detected for order {locked_order.id}: {existing_count}/{expected_total}."
        )

    now = get_guyana_now()
    tickets_to_create: list[Ticket] = []
    for item in order_items:
        for _ in range(item.quantity):
            ticket_code = _generate_ticket_code()
            qr_token, display_code, qr_generated_at = _issue_ticket_qr_fields(db)
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
                    display_code=display_code,
                    qr_token=qr_token,
                    qr_generated_at=qr_generated_at,
                    qr_payload=qr_token,
                    issued_at=now,
                )
            )

    db.add_all(tickets_to_create)
    db.flush()
    issued_tickets = (
        db.execute(select(Ticket).where(Ticket.order_id == locked_order.id).order_by(Ticket.id.asc()))
        .scalars()
        .all()
    )
    for ticket in issued_tickets:
        notify_ticket_issued(ticket)
    return issued_tickets


def can_void_event_ticket(db: Session, *, user_id: int, event_id: int) -> bool:
    return has_event_permission_by_id(
        db,
        user_id=user_id,
        event_id=event_id,
        action=EventPermissionAction.CANCEL_EVENT,
    )


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
            try:
                notify_ticket_voided(ticket, actor_user_id=actor_user_id)
            except TypeError:
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
            try:
                notify_ticket_voided(ticket, actor_user_id=actor_user_id)
            except TypeError:
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




def get_ticket_for_owner(db: Session, *, ticket_id: int, user_id: int) -> Ticket | None:
    return db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.owner_user_id == user_id)
    ).scalar_one_or_none()


def validate_ticket_transferable(ticket: Ticket, *, current_user_id: int) -> None:
    if ticket.owner_user_id != current_user_id:
        raise TicketAuthorizationError("Only the current ticket owner can transfer this ticket.")
    if ticket.status == TicketStatus.CHECKED_IN:
        raise TicketTransferError("Checked-in tickets cannot be transferred.")
    if ticket.status == TicketStatus.VOIDED:
        raise TicketTransferError("Voided tickets cannot be transferred.")
    if ticket.status != TicketStatus.ISSUED:
        raise TicketTransferError("Ticket is not eligible for transfer.")


def _expire_pending_invite_if_needed(db: Session, invite: TicketTransferInvite, *, now: datetime | None = None) -> bool:
    if invite.status != TransferInviteStatus.PENDING:
        return False
    now_value = now or get_guyana_now()
    if invite.expires_at is None or invite.expires_at > now_value:
        return False
    invite.status = TransferInviteStatus.EXPIRED
    invite.updated_at = now_value
    db.flush()
    return True


def get_active_pending_transfer_for_ticket(
    db: Session,
    *,
    ticket_id: int,
    now: datetime | None = None,
) -> TicketTransferInvite | None:
    invite = (
        db.execute(
            select(TicketTransferInvite)
            .where(
                TicketTransferInvite.ticket_id == ticket_id,
                TicketTransferInvite.status == TransferInviteStatus.PENDING,
            )
            .order_by(TicketTransferInvite.id.desc())
        )
        .scalars()
        .first()
    )
    if invite is None:
        return None
    _expire_pending_invite_if_needed(db, invite, now=now)
    return invite if invite.status == TransferInviteStatus.PENDING else None


def validate_ticket_transfer_invitable(ticket: Ticket, *, current_user_id: int) -> None:
    validate_ticket_transferable(ticket, current_user_id=current_user_id)
    db = object_session(ticket)
    if db is not None and get_active_pending_transfer_for_ticket(db, ticket_id=ticket.id) is not None:
        raise TicketTransferError("Ticket already has a pending transfer invite.")


def transfer_ticket_to_user(
    db: Session,
    *,
    ticket_id: int,
    from_user_id: int,
    to_user_id: int,
) -> Ticket:
    if from_user_id == to_user_id:
        raise TicketTransferError("Cannot transfer a ticket to yourself.")

    ticket = (
        db.execute(select(Ticket).where(Ticket.id == ticket_id).with_for_update())
        .scalars()
        .first()
    )
    if ticket is None:
        raise TicketNotFoundError("Ticket not found.")

    validate_ticket_transferable(ticket, current_user_id=from_user_id)
    if get_active_pending_transfer_for_ticket(db, ticket_id=ticket.id) is not None:
        raise TicketTransferError("Ticket has a pending transfer invite.")

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
    try:
        notify_ticket_transferred(ticket, from_user_id=from_user_id, to_user_id=to_user_id)
    except TypeError:
        notify_ticket_transferred(db, ticket, from_user_id=from_user_id, to_user_id=to_user_id)
    return ticket


def create_ticket_transfer_invite(
    db: Session,
    *,
    ticket_id: int,
    sender_user_id: int,
    recipient_user_id: int | None = None,
    recipient_email: str | None = None,
    recipient_phone: str | None = None,
    recipient_name: str | None = None,
    expires_at=None,
) -> TicketTransferInvite:
    normalized_email = normalize_email(recipient_email) if _normalize_optional(recipient_email) else None
    normalized_phone = _normalize_phone(recipient_phone)
    normalized_name = _normalize_optional(recipient_name)
    if recipient_user_id is None and normalized_email is None and normalized_phone is None:
        raise TicketTransferError("Provide recipient_user_id, recipient_email, or recipient_phone.")

    ticket = (
        db.execute(
            select(Ticket).where(Ticket.id == ticket_id).with_for_update()
        )
        .scalar_one_or_none()
    )
    if ticket is None:
        raise TicketNotFoundError("Ticket not found.")
    db.refresh(ticket, attribute_names=["transfer_invites", "owner"])

    validate_ticket_transfer_invitable(ticket, current_user_id=sender_user_id)
    if recipient_user_id is not None:
        recipient = db.execute(select(User).where(User.id == recipient_user_id)).scalar_one_or_none()
        if recipient is None:
            raise TicketTransferError("Recipient user not found.")
        if recipient_user_id == sender_user_id:
            raise TicketTransferError("Cannot transfer a ticket to yourself.")
    elif normalized_email is not None:
        matched_user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
        if matched_user is not None:
            recipient_user_id = matched_user.id
    elif normalized_phone is not None:
        matched_user = db.execute(select(User).where(User.phone == normalized_phone)).scalar_one_or_none()
        if matched_user is not None:
            recipient_user_id = matched_user.id

    if normalized_email and normalized_email == normalize_email(ticket.owner.email or ""):
        raise TicketTransferError("Cannot transfer a ticket to yourself.")
    if normalized_phone and _normalize_phone(ticket.owner.phone) and normalized_phone == _normalize_phone(ticket.owner.phone):
        raise TicketTransferError("Cannot transfer a ticket to yourself.")

    now = get_guyana_now()
    invite = TicketTransferInvite(
        ticket_id=ticket.id,
        sender_user_id=sender_user_id,
        recipient_user_id=recipient_user_id,
        recipient_email=normalized_email,
        recipient_phone=normalized_phone,
        recipient_name=normalized_name,
        invite_token=_create_unique_transfer_invite_token(db),
        status=TransferInviteStatus.PENDING,
        expires_at=expires_at or (now + DEFAULT_TRANSFER_INVITE_TTL),
    )
    db.add(invite)
    db.flush()
    notify_ticket_transfer_invite_created(invite)
    return invite


def get_ticket_transfer_invite_by_token(db: Session, *, invite_token: str) -> TicketTransferInvite:
    invite = (
        db.execute(
            select(TicketTransferInvite)
            .options(
                joinedload(TicketTransferInvite.ticket).joinedload(Ticket.event),
                joinedload(TicketTransferInvite.ticket).joinedload(Ticket.ticket_tier),
                joinedload(TicketTransferInvite.sender),
            )
            .where(TicketTransferInvite.invite_token == invite_token)
        )
        .unique()
        .scalar_one_or_none()
    )
    if invite is None:
        raise TicketNotFoundError("Transfer invite not found.")
    _expire_pending_invite_if_needed(db, invite)
    return invite


def list_ticket_transfer_invites_for_user(
    db: Session,
    *,
    user_id: int,
    sent: bool = False,
) -> list[TicketTransferInvite]:
    filters = [TicketTransferInvite.sender_user_id == user_id] if sent else [TicketTransferInvite.recipient_user_id == user_id]
    invites = (
        db.execute(
            select(TicketTransferInvite)
            .where(and_(*filters))
            .order_by(TicketTransferInvite.created_at.desc(), TicketTransferInvite.id.desc())
        )
        .scalars()
        .all()
    )
    now = get_guyana_now()
    for invite in invites:
        _expire_pending_invite_if_needed(db, invite, now=now)
    return invites


def accept_ticket_transfer_invite(
    db: Session,
    *,
    invite_token: str,
    accepting_user_id: int,
) -> Ticket:
    invite = (
        db.execute(
            select(TicketTransferInvite).where(TicketTransferInvite.invite_token == invite_token).with_for_update()
        )
        .scalar_one_or_none()
    )
    if invite is None:
        raise TicketNotFoundError("Transfer invite not found.")
    db.refresh(invite, attribute_names=["ticket", "sender"])
    if (
        invite.status == TransferInviteStatus.ACCEPTED
        and invite.recipient_user_id == accepting_user_id
        and invite.ticket.owner_user_id == accepting_user_id
    ):
        return invite.ticket
    _expire_pending_invite_if_needed(db, invite)
    if invite.status != TransferInviteStatus.PENDING:
        raise TicketTransferError("Transfer invite is no longer pending.")
    accepting_user = db.execute(select(User).where(User.id == accepting_user_id)).scalar_one_or_none()
    if accepting_user is None:
        raise TicketTransferError("Accepting user not found.")

    now = get_guyana_now()

    ticket = (
        db.execute(select(Ticket).where(Ticket.id == invite.ticket_id).with_for_update())
        .scalars()
        .first()
    )
    if ticket is None:
        raise TicketNotFoundError("Ticket not found.")
    if ticket.owner_user_id != invite.sender_user_id:
        raise TicketTransferError("Ticket ownership no longer matches invite sender.")
    validate_ticket_transferable(ticket, current_user_id=invite.sender_user_id)

    if invite.recipient_user_id is not None and invite.recipient_user_id != accepting_user_id:
        raise TicketAuthorizationError("This transfer invite is assigned to a different user.")
    if invite.recipient_email is not None and normalize_email(accepting_user.email) != invite.recipient_email:
        raise TicketAuthorizationError("This transfer invite is assigned to a different email.")
    if invite.recipient_phone is not None and _normalize_phone(accepting_user.phone) != invite.recipient_phone:
        raise TicketAuthorizationError("This transfer invite is assigned to a different phone number.")

    ticket.owner_user_id = accepting_user_id
    ticket.user_id = accepting_user_id
    ticket.transferred_at = now
    ticket.transfer_count += 1
    ticket.updated_at = now

    invite.status = TransferInviteStatus.ACCEPTED
    invite.accepted_at = now
    invite.accepted_by_user_id = accepting_user_id
    if invite.recipient_user_id is None:
        invite.recipient_user_id = accepting_user_id
    if invite.recipient_name is None:
        invite.recipient_name = _normalize_optional(accepting_user.full_name)
    invite.updated_at = now

    db.flush()
    notify_ticket_transfer_invite_accepted(invite, ticket)
    publish_webhook_event(db, event_type="transfer.accepted", payload=build_transfer_payload(invite, ticket))
    return ticket


def revoke_ticket_transfer_invite(
    db: Session,
    *,
    invite_token: str,
    actor_user_id: int,
) -> TicketTransferInvite:
    invite = (
        db.execute(
            select(TicketTransferInvite).where(TicketTransferInvite.invite_token == invite_token).with_for_update()
        )
        .scalar_one_or_none()
    )
    if invite is None:
        raise TicketNotFoundError("Transfer invite not found.")
    db.refresh(invite, attribute_names=["ticket"])
    if invite.status != TransferInviteStatus.PENDING:
        raise TicketTransferError("Only pending invites can be revoked.")
    if actor_user_id not in {invite.sender_user_id, invite.ticket.owner_user_id}:
        raise TicketAuthorizationError("Only the sender/current owner can revoke this invite.")

    now = get_guyana_now()
    invite.status = TransferInviteStatus.REVOKED
    invite.revoked_at = now
    invite.revoked_by_user_id = actor_user_id
    invite.updated_at = now
    db.flush()
    notify_ticket_transfer_invite_revoked(invite)
    return invite


def void_ticket(
    db: Session,
    *,
    ticket_id: int,
    actor_user_id: int,
    reason: str | None = None,
) -> Ticket:
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
    try:
        notify_ticket_voided(ticket, actor_user_id=actor_user_id)
    except TypeError:
        notify_ticket_voided(db, ticket, actor_user_id=actor_user_id)
    return ticket


def can_actor_check_in_event(db: Session, *, user_id: int, event_id: int) -> bool:
    return has_event_permission_by_id(
        db,
        user_id=user_id,
        event_id=event_id,
        action=EventPermissionAction.CHECKIN_TICKETS,
    )


def can_actor_override_check_in(db: Session, *, user_id: int, event_id: int) -> bool:
    return has_event_permission_by_id(
        db,
        user_id=user_id,
        event_id=event_id,
        action=EventPermissionAction.CHECKIN_OVERRIDE,
    )


def can_check_in_event_tickets(db: Session, *, user_id: int, event_id: int) -> bool:
    return can_actor_check_in_event(db, user_id=user_id, event_id=event_id)


def can_scan_event(db: Session, *, user: User, event: Event) -> bool:
    return has_event_permission_by_id(
        db,
        user_id=user.id,
        event_id=event.id,
        action=EventPermissionAction.CHECKIN_TICKETS,
    )


def get_ticket_by_qr_payload(db: Session, *, qr_payload: str) -> Ticket | None:
    lookup = extract_ticket_lookup_value(qr_payload)
    if not lookup:
        return None
    ticket = (
        db.execute(select(Ticket).where(or_(Ticket.ticket_code == lookup, Ticket.qr_payload == lookup, Ticket.qr_token == lookup, Ticket.display_code == lookup)))
        .scalars()
        .first()
    )
    if ticket is not None and not ticket.qr_token:
        ensure_ticket_qr(db, ticket)
        db.flush()
    return ticket


def _is_event_admittable(event: Event | None) -> bool:
    if event is None:
        return False
    return event.status != EventStatus.CANCELLED and event.cancelled_at is None


def _is_order_admittable(order: Order | None) -> bool:
    if order is None:
        return False
    return (
        order.status == OrderStatus.COMPLETED
        and order.payment_verification_status == "verified"
        and order.refund_status != "refunded"
    )


def _record_check_in_attempt(
    db: Session,
    *,
    event_id: int,
    actor_user_id: int | None,
    ticket: Ticket | None,
    result_code: str,
    reason_code: str | None,
    reason_message: str,
    method: str | None,
    source: str | None = None,
    notes: str | None = None,
) -> None:
    db.add(
        TicketCheckInAttempt(
            ticket_id=ticket.id if ticket else None,
            event_id=event_id,
            actor_user_id=actor_user_id,
            attempted_at=get_guyana_now(),
            result_code=result_code,
            reason_code=reason_code,
            reason_message=reason_message,
            method=method,
            source=source,
            notes=_normalize_optional(notes),
        )
    )


def _record_ticket_scan_log(
    db: Session,
    *,
    ticket: Ticket | None,
    scanned_by: int | None,
    status: TicketScanStatus,
    note: str | None = None,
) -> None:
    db.add(
        TicketScanLog(
            ticket_id=ticket.id if ticket else None,
            scanned_by=scanned_by,
            scanned_at=get_guyana_now(),
            status=status,
            note=_normalize_optional(note),
        )
    )


def _evaluate_ticket_for_entry(*, ticket: Ticket, event_id: int) -> TicketCheckInValidationResult:
    if ticket.event_id != event_id:
        return TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_WRONG_EVENT,
            message="Ticket does not belong to this event.",
            event_id=event_id,
            ticket=ticket,
            reason_code=CHECK_IN_STATUS_WRONG_EVENT,
        )
    if not _is_event_admittable(ticket.event):
        return TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_CANCELED_EVENT,
            message="Event is cancelled and not admittable.",
            event_id=event_id,
            ticket=ticket,
            reason_code=CHECK_IN_STATUS_CANCELED_EVENT,
        )
    if ticket.status == TicketStatus.CHECKED_IN:
        return TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_ALREADY_CHECKED_IN,
            message="Ticket has already been checked in.",
            event_id=event_id,
            ticket=ticket,
            checked_in_at=ticket.checked_in_at,
            reason_code=CHECK_IN_STATUS_ALREADY_CHECKED_IN,
        )
    if ticket.status != TicketStatus.ISSUED:
        return TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_REFUNDED_OR_INVALIDATED,
            message="Ticket is refunded or invalidated.",
            event_id=event_id,
            ticket=ticket,
            reason_code=CHECK_IN_STATUS_REFUNDED_OR_INVALIDATED,
        )
    db = object_session(ticket)
    if db is not None and get_active_pending_transfer_for_ticket(db, ticket_id=ticket.id) is not None:
        return TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_TRANSFER_PENDING,
            message="Ticket transfer is pending acceptance.",
            event_id=event_id,
            ticket=ticket,
            reason_code=CHECK_IN_STATUS_TRANSFER_PENDING,
        )
    if not _is_order_admittable(ticket.order):
        return TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_ORDER_NOT_ADMITTABLE,
            message="Order is not in an admittable payment state.",
            event_id=event_id,
            ticket=ticket,
            reason_code=CHECK_IN_STATUS_ORDER_NOT_ADMITTABLE,
        )
    return TicketCheckInValidationResult(
        valid=True,
        status=CHECK_IN_STATUS_VALID,
        message="Ticket is valid for check-in.",
        event_id=event_id,
        ticket=ticket,
        reason_code=CHECK_IN_STATUS_VALID,
    )


def validate_ticket_for_check_in(
    db: Session,
    *,
    actor_user_id: int,
    event_id: int,
    qr_payload: str | None = None,
    ticket_code: str | None = None,
) -> TicketCheckInValidationResult:
    if not can_actor_check_in_event(db, user_id=actor_user_id, event_id=event_id):
        result = TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_UNAUTHORIZED,
            message="Not authorized to check in tickets for this event.",
            event_id=event_id,
            reason_code=CHECK_IN_STATUS_UNAUTHORIZED,
        )
        _record_check_in_attempt(
            db,
            event_id=event_id,
            actor_user_id=actor_user_id,
            ticket=None,
            result_code=result.status,
            reason_code=result.reason_code,
            reason_message=result.message,
            method="validate",
        )
        db.flush()
        return result

    lookup = extract_ticket_lookup_value(ticket_code or qr_payload)
    if not lookup:
        result = TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_INVALID,
            message="A ticket code or QR payload is required.",
            event_id=event_id,
            reason_code=CHECK_IN_STATUS_INVALID,
        )
        _record_check_in_attempt(
            db,
            event_id=event_id,
            actor_user_id=actor_user_id,
            ticket=None,
            result_code=result.status,
            reason_code=result.reason_code,
            reason_message=result.message,
            method="validate",
        )
        db.flush()
        return result

    ticket = (
        db.execute(
            select(Ticket)
            .options(joinedload(Ticket.event), joinedload(Ticket.order))
            .where(or_(Ticket.ticket_code == lookup, Ticket.qr_payload == lookup, Ticket.qr_token == lookup, Ticket.display_code == lookup))
        )
        .unique()
        .scalars()
        .first()
    )
    if ticket is None:
        result = TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_NOT_FOUND,
            message="Ticket not found.",
            event_id=event_id,
            reason_code=CHECK_IN_STATUS_NOT_FOUND,
        )
    else:
        result = _evaluate_ticket_for_entry(ticket=ticket, event_id=event_id)
    _record_check_in_attempt(
        db,
        event_id=event_id,
        actor_user_id=actor_user_id,
        ticket=ticket,
        result_code=result.status,
        reason_code=result.reason_code,
        reason_message=result.message,
        method="validate",
    )
    db.flush()
    return result


def check_in_ticket(
    db: Session,
    *,
    scanner_user_id: int,
    event_id: int,
    qr_payload: str | None = None,
    ticket_code: str | None = None,
    method: str = CHECK_IN_METHOD_QR,
) -> TicketCheckInValidationResult:
    if method not in {CHECK_IN_METHOD_QR, CHECK_IN_METHOD_MANUAL}:
        method = CHECK_IN_METHOD_QR
    if not can_actor_check_in_event(db, user_id=scanner_user_id, event_id=event_id):
        result = TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_UNAUTHORIZED,
            message="Not authorized to check in tickets for this event.",
            event_id=event_id,
            reason_code=CHECK_IN_STATUS_UNAUTHORIZED,
        )
        _record_check_in_attempt(
            db,
            event_id=event_id,
            actor_user_id=scanner_user_id,
            ticket=None,
            result_code=result.status,
            reason_code=result.reason_code,
            reason_message=result.message,
            method=method,
        )
        db.flush()
        return result

    lookup = extract_ticket_lookup_value(ticket_code or qr_payload)
    if not lookup:
        result = TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_INVALID,
            message="A ticket code or QR payload is required.",
            event_id=event_id,
            reason_code=CHECK_IN_STATUS_INVALID,
        )
        _record_check_in_attempt(
            db,
            event_id=event_id,
            actor_user_id=scanner_user_id,
            ticket=None,
            result_code=result.status,
            reason_code=result.reason_code,
            reason_message=result.message,
            method=method,
        )
        db.flush()
        return result

    ticket = (
        db.execute(
            select(Ticket)
            .where(or_(Ticket.ticket_code == lookup, Ticket.qr_payload == lookup, Ticket.qr_token == lookup, Ticket.display_code == lookup))
            .with_for_update()
        )
        .scalars()
        .first()
    )
    if ticket is None:
        result = TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_NOT_FOUND,
            message="Ticket not found.",
            event_id=event_id,
            reason_code=CHECK_IN_STATUS_NOT_FOUND,
        )
        _record_check_in_attempt(
            db,
            event_id=event_id,
            actor_user_id=scanner_user_id,
            ticket=None,
            result_code=result.status,
            reason_code=result.reason_code,
            reason_message=result.message,
            method=method,
        )
        db.flush()
        return result
    db.refresh(ticket, attribute_names=["event", "order"])
    result = _evaluate_ticket_for_entry(ticket=ticket, event_id=event_id)
    if not result.valid:
        _record_check_in_attempt(
            db,
            event_id=event_id,
            actor_user_id=scanner_user_id,
            ticket=ticket,
            result_code=result.status,
            reason_code=result.reason_code,
            reason_message=result.message,
            method=method,
        )
        db.flush()
        return result

    now = get_guyana_now()
    ticket.status = TicketStatus.CHECKED_IN
    ticket.checked_in_at = now
    ticket.checked_in_by_user_id = scanner_user_id
    ticket.check_in_status = CheckInStatus.CHECKED_IN
    ticket.check_in_method = method
    ticket.updated_at = now
    _record_check_in_attempt(
        db,
        event_id=event_id,
        actor_user_id=scanner_user_id,
        ticket=ticket,
        result_code=CHECK_IN_STATUS_VALID,
        reason_code=CHECK_IN_STATUS_VALID,
        reason_message="Ticket checked in successfully.",
        method=method,
    )
    db.flush()
    publish_webhook_event(db, event_type="checkin.completed", payload=build_checkin_payload(ticket))
    return TicketCheckInValidationResult(
        valid=True,
        status=CHECK_IN_STATUS_VALID,
        message="Ticket checked in successfully.",
        event_id=event_id,
        ticket=ticket,
        checked_in_at=ticket.checked_in_at,
        reason_code=CHECK_IN_STATUS_VALID,
    )


def get_event_check_in_summary(
    db: Session,
    *,
    actor_user_id: int,
    event_id: int,
) -> TicketCheckInSummaryResult:
    if not can_actor_check_in_event(db, user_id=actor_user_id, event_id=event_id):
        raise TicketAuthorizationError("Not authorized to check in tickets for this event.")

    tickets = (
        db.execute(
            select(Ticket)
            .options(joinedload(Ticket.order))
            .where(Ticket.event_id == event_id)
        )
        .unique()
        .scalars()
        .all()
    )
    admittable = [t for t in tickets if t.status in {TicketStatus.ISSUED, TicketStatus.CHECKED_IN} and _is_order_admittable(t.order)]
    checked_in_count = sum(1 for ticket in admittable if ticket.status == TicketStatus.CHECKED_IN)
    return TicketCheckInSummaryResult(
        event_id=event_id,
        total_admittable_tickets=len(admittable),
        checked_in_tickets=checked_in_count,
        remaining_tickets=max(0, len(admittable) - checked_in_count),
    )


def override_ticket_check_in(
    db: Session,
    *,
    actor_user_id: int,
    event_id: int,
    qr_payload: str | None = None,
    ticket_code: str | None = None,
    admit: bool,
    notes: str,
) -> TicketCheckInValidationResult:
    if not can_actor_override_check_in(db, user_id=actor_user_id, event_id=event_id):
        raise TicketAuthorizationError("Not authorized to override ticket check-in for this event.")
    if not _normalize_optional(notes):
        raise TicketCheckInConflictError("Manual override notes are required.")

    lookup = extract_ticket_lookup_value(ticket_code or qr_payload)
    if not lookup:
        raise TicketNotFoundError("A ticket code or QR payload is required.")

    ticket = (
        db.execute(
            select(Ticket)
            .where(or_(Ticket.ticket_code == lookup, Ticket.qr_payload == lookup, Ticket.qr_token == lookup, Ticket.display_code == lookup))
            .with_for_update()
        )
        .scalars()
        .first()
    )
    if ticket is None:
        _record_check_in_attempt(
            db,
            event_id=event_id,
            actor_user_id=actor_user_id,
            ticket=None,
            result_code=CHECK_IN_STATUS_NOT_FOUND,
            reason_code=CHECK_IN_STATUS_NOT_FOUND,
            reason_message="Ticket not found for override.",
            method=CHECK_IN_METHOD_OVERRIDE,
            notes=notes,
        )
        db.flush()
        raise TicketNotFoundError("Ticket not found.")
    db.refresh(ticket, attribute_names=["event", "order"])
    if ticket.event_id != event_id:
        raise TicketCrossEventError("Ticket does not belong to this event.")

    now = get_guyana_now()
    if admit:
        if ticket.status == TicketStatus.CHECKED_IN:
            result = TicketCheckInValidationResult(
                valid=False,
                status=CHECK_IN_STATUS_ALREADY_CHECKED_IN,
                message="Ticket has already been checked in.",
                event_id=event_id,
                ticket=ticket,
                checked_in_at=ticket.checked_in_at,
                reason_code=CHECK_IN_STATUS_ALREADY_CHECKED_IN,
            )
        else:
            ticket.status = TicketStatus.CHECKED_IN
            ticket.checked_in_at = now
            ticket.checked_in_by_user_id = actor_user_id
            ticket.check_in_status = CheckInStatus.CHECKED_IN
            ticket.check_in_method = CHECK_IN_METHOD_OVERRIDE
            ticket.updated_at = now
            result = TicketCheckInValidationResult(
                valid=True,
                status=CHECK_IN_STATUS_MANUAL_OVERRIDE_ADMITTED,
                message="Ticket admitted by manual override.",
                event_id=event_id,
                ticket=ticket,
                checked_in_at=ticket.checked_in_at,
                reason_code=CHECK_IN_STATUS_MANUAL_OVERRIDE_ADMITTED,
            )
    else:
        result = TicketCheckInValidationResult(
            valid=False,
            status=CHECK_IN_STATUS_MANUAL_OVERRIDE_DENIED,
            message="Ticket denied by manual override.",
            event_id=event_id,
            ticket=ticket,
            reason_code=CHECK_IN_STATUS_MANUAL_OVERRIDE_DENIED,
        )

    _record_check_in_attempt(
        db,
        event_id=event_id,
        actor_user_id=actor_user_id,
        ticket=ticket,
        result_code=result.status,
        reason_code=result.reason_code,
        reason_message=result.message,
        method=CHECK_IN_METHOD_OVERRIDE,
        notes=notes,
    )
    db.flush()
    return result


def list_recent_check_in_attempts(
    db: Session,
    *,
    actor_user_id: int,
    event_id: int,
    limit: int = 50,
) -> list[TicketCheckInAttemptRow]:
    if not can_actor_check_in_event(db, user_id=actor_user_id, event_id=event_id):
        raise TicketAuthorizationError("Not authorized to view check-in activity for this event.")

    rows = (
        db.execute(
            select(TicketCheckInAttempt)
            .where(TicketCheckInAttempt.event_id == event_id)
            .order_by(TicketCheckInAttempt.attempted_at.desc(), TicketCheckInAttempt.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        TicketCheckInAttemptRow(
            id=row.id,
            ticket_id=row.ticket_id,
            event_id=row.event_id,
            actor_user_id=row.actor_user_id,
            attempted_at=row.attempted_at,
            result_code=row.result_code,
            reason_code=row.reason_code,
            reason_message=row.reason_message,
            method=row.method,
            source=row.source,
            notes=row.notes,
        )
        for row in rows
    ]


def check_in_ticket_for_event(
    db: Session,
    *,
    scanner_user_id: int,
    event_id: int,
    qr_payload: str | None,
    ticket_code: str | None,
) -> Ticket:
    result = check_in_ticket(
        db,
        scanner_user_id=scanner_user_id,
        event_id=event_id,
        qr_payload=qr_payload,
        ticket_code=ticket_code,
        method=CHECK_IN_METHOD_QR,
    )
    if result.status == CHECK_IN_STATUS_UNAUTHORIZED:
        raise TicketAuthorizationError(result.message)
    if result.status in {CHECK_IN_STATUS_NOT_FOUND, CHECK_IN_STATUS_INVALID}:
        raise TicketNotFoundError(result.message)
    if result.status == CHECK_IN_STATUS_WRONG_EVENT:
        raise TicketCrossEventError(result.message)
    if not result.valid:
        raise TicketCheckInConflictError(result.message)
    if result.ticket is None:
        raise TicketNotFoundError("Ticket not found.")
    return result.ticket


def scan_ticket(
    db: Session,
    *,
    payload: dict[str, object],
    user_id: int,
) -> TicketScanResult:
    if not validate_ticket_qr_signature(payload):
        _record_ticket_scan_log(
            db,
            ticket=None,
            scanned_by=user_id,
            status=TicketScanStatus.INVALID,
            note="Invalid ticket payload signature.",
        )
        db.flush()
        return TicketScanResult(status=TicketScanStatus.INVALID.value, message="Invalid QR payload.")

    ticket_id = payload.get("ticket_id")
    payload_event_id = payload.get("event_id")
    if not isinstance(ticket_id, int) or not isinstance(payload_event_id, int):
        _record_ticket_scan_log(
            db,
            ticket=None,
            scanned_by=user_id,
            status=TicketScanStatus.INVALID,
            note="QR payload is missing required identifiers.",
        )
        db.flush()
        return TicketScanResult(status=TicketScanStatus.INVALID.value, message="Invalid QR payload.")

    ticket = (
        db.execute(
            select(Ticket).where(Ticket.id == ticket_id).with_for_update()
        )
        .scalars()
        .first()
    )
    if ticket is None:
        _record_ticket_scan_log(
            db,
            ticket=None,
            scanned_by=user_id,
            status=TicketScanStatus.INVALID,
            note="Ticket not found.",
        )
        db.flush()
        return TicketScanResult(status=TicketScanStatus.INVALID.value, message="Invalid ticket.")
    db.refresh(ticket, attribute_names=["event", "order"])

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not can_scan_event(db, user=user, event=ticket.event):
        _record_ticket_scan_log(
            db,
            ticket=ticket,
            scanned_by=user_id,
            status=TicketScanStatus.INVALID,
            note="Unauthorized scan attempt.",
        )
        db.flush()
        return TicketScanResult(status=TicketScanStatus.INVALID.value, message="Not authorized to scan this event.")

    if ticket.event_id != payload_event_id:
        _record_ticket_scan_log(
            db,
            ticket=ticket,
            scanned_by=user_id,
            status=TicketScanStatus.WRONG_EVENT,
            note="Payload event does not match ticket event.",
        )
        db.flush()
        return TicketScanResult(status=TicketScanStatus.WRONG_EVENT.value, message="Ticket is for a different event.")

    now = get_guyana_now()
    event_end_at = ticket.event.end_at if ticket.event else None
    compare_now = now
    if event_end_at is not None and event_end_at.tzinfo is None:
        compare_now = now.replace(tzinfo=None)
    if event_end_at is not None and event_end_at < compare_now:
        _record_ticket_scan_log(
            db,
            ticket=ticket,
            scanned_by=user_id,
            status=TicketScanStatus.INVALID,
            note="Event has already ended.",
        )
        db.flush()
        return TicketScanResult(status=TicketScanStatus.INVALID.value, message="Ticket is expired.")

    if ticket.check_in_status == CheckInStatus.CHECKED_IN or ticket.status == TicketStatus.CHECKED_IN:
        _record_ticket_scan_log(
            db,
            ticket=ticket,
            scanned_by=user_id,
            status=TicketScanStatus.ALREADY_USED,
            note="Ticket already checked in.",
        )
        db.flush()
        return TicketScanResult(
            status=TicketScanStatus.ALREADY_USED.value,
            ticket_id=ticket.id,
            checked_in_at=ticket.checked_in_at,
            message="Ticket already used.",
        )

    if ticket.status != TicketStatus.ISSUED or not _is_order_admittable(ticket.order):
        _record_ticket_scan_log(
            db,
            ticket=ticket,
            scanned_by=user_id,
            status=TicketScanStatus.INVALID,
            note="Ticket is cancelled, refunded, or otherwise not admittable.",
        )
        db.flush()
        return TicketScanResult(status=TicketScanStatus.INVALID.value, message="Ticket is not valid for entry.")

    ticket.checked_in_at = now
    ticket.checked_in_by_user_id = user_id
    ticket.check_in_status = CheckInStatus.CHECKED_IN
    ticket.check_in_method = CHECK_IN_METHOD_QR
    ticket.status = TicketStatus.CHECKED_IN
    ticket.updated_at = now

    _record_ticket_scan_log(
        db,
        ticket=ticket,
        scanned_by=user_id,
        status=TicketScanStatus.SUCCESS,
        note="Ticket checked in successfully.",
    )
    db.flush()
    return TicketScanResult(
        status=TicketScanStatus.SUCCESS.value,
        ticket_id=ticket.id,
        checked_in_at=ticket.checked_in_at,
        message="Ticket checked in successfully.",
    )


def check_in_ticket_manually(
    db: Session,
    *,
    ticket_id: int,
    user_id: int,
) -> TicketScanResult:
    ticket = db.execute(select(Ticket).where(Ticket.id == ticket_id)).scalar_one_or_none()
    if ticket is None:
        return TicketScanResult(status=TicketScanStatus.INVALID.value, message="Invalid ticket.")
    payload = {
        "ticket_id": ticket.id,
        "event_id": ticket.event_id,
        "hash": "",
    }
    # Reuse scan flow for all validation + logging while bypassing QR transport details.
    from app.services.ticket_qr import generate_ticket_qr_payload

    payload["hash"] = str(generate_ticket_qr_payload(ticket)["hash"])
    return scan_ticket(db, payload=payload, user_id=user_id)


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
