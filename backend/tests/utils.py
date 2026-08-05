import uuid
from datetime import timedelta

from app.core.security import create_token


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


def auth_headers(user) -> dict[str, str]:
    """Authenticate API tests through the same signed Bearer path as production."""
    token = create_token(subject=str(user.id), token_type="access", expires_delta=timedelta(minutes=15))
    return {"Authorization": f"Bearer {token}"}


def transfer_ticket_to_user(db, *, ticket_id: int, from_user_id: int, to_user_id: int):
    """Complete the pending/accept lifecycle for legacy ticket test scenarios."""
    from app.models.ticket import Ticket
    from app.models.user import User
    from app.services.ticket_holds import get_guyana_now
    from app.services.tickets import (
        TicketTransferError,
        accept_ticket_transfer,
        create_ticket_transfer_from_resolution,
        resolve_ticket_transfer_recipient,
    )

    sender = db.get(User, from_user_id)
    recipient = db.get(User, to_user_id)
    if recipient is None:
        raise TicketTransferError("Recipient user not found.")
    for user in (sender, recipient):
        if user is not None:
            user.phone = user.phone or f"+882{user.id:09d}"
            user.is_verified = True
            user.phone_verified_at = user.phone_verified_at or get_guyana_now()
    ticket = db.get(Ticket, ticket_id)
    if ticket is not None and ticket.event.end_at <= get_guyana_now():
        duration = ticket.event.end_at - ticket.event.start_at
        ticket.event.start_at = get_guyana_now() + timedelta(days=1)
        ticket.event.end_at = ticket.event.start_at + duration
    db.commit()
    _, _, reference = resolve_ticket_transfer_recipient(
        db,
        ticket_id=ticket_id,
        sender_user_id=from_user_id,
        recipient_email=recipient.email,
    )
    invite = create_ticket_transfer_from_resolution(
        db,
        ticket_id=ticket_id,
        sender_user_id=from_user_id,
        recipient_resolution_reference=reference,
    )
    accept_ticket_transfer(db, transfer_id=invite.id, accepting_user_id=to_user_id)
    return db.get(Ticket, ticket_id)
