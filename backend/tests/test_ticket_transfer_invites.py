from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Event, OrganizerProfile, Order, OrderItem, TicketTier, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus, TicketStatus, TransferInviteStatus
from app.services.tickets import (
    CHECK_IN_STATUS_TRANSFER_PENDING,
    TicketAuthorizationError,
    TicketTransferError,
    accept_ticket_transfer_invite,
    create_ticket_transfer_invite,
    get_active_pending_transfer_for_ticket,
    issue_tickets_for_completed_order,
    revoke_ticket_transfer_invite,
    transfer_ticket_to_user,
    validate_ticket_for_check_in,
)
from tests.utils import unique_email



def _seed_order(db: Session, *, suffix: str) -> tuple[Order, User, Event]:
    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    buyer = User(email=unique_email("buyer"), full_name="Buyer", phone=f"+592700{suffix[-2:]}")
    organizer_user = User(email=unique_email("organizer"), full_name="Organizer")
    db.add_all([buyer, organizer_user])
    db.flush()

    organizer = OrganizerProfile(user_id=organizer_user.id, business_name="Org", display_name="Org")
    db.add(organizer)
    db.flush()
    venue = Venue(organizer_id=organizer.id, name="Venue")
    db.add(venue)
    db.flush()

    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title=f"Event {suffix}",
        slug=f"event-{suffix}",
        start_at=now + timedelta(days=2),
        end_at=now + timedelta(days=2, hours=2),
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        approval_status=EventApprovalStatus.APPROVED,
        timezone="America/Guyana",
        is_location_pinned=False,
    )
    db.add(event)
    db.flush()
    tier = TicketTier(
        event_id=event.id,
        name="General",
        tier_code=f"GEN-{suffix}",
        price_amount=Decimal("100.00"),
        currency="GYD",
        quantity_total=100,
        quantity_sold=0,
        quantity_held=0,
        min_per_order=1,
        max_per_order=10,
        is_active=True,
        sort_order=0,
    )
    db.add(tier)
    db.flush()
    order = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        total_amount=Decimal("100.00"),
        currency="GYD",
        payment_verification_status="verified",
    )
    db.add(order)
    db.flush()
    db.add(OrderItem(order_id=order.id, ticket_tier_id=tier.id, quantity=1, unit_price=Decimal("100.00")))
    db.commit()
    return order, buyer, event


def test_invite_creation_and_acceptance_and_revocation_flow(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    order, owner, _ = _seed_order(db_session, suffix="01")
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    recipient = User(email=unique_email("recipient"), full_name="Recipient", phone="+59270099")
    other = User(email=unique_email("other"), full_name="Other")
    db_session.add_all([recipient, other])
    db_session.commit()
    db_session.refresh(recipient)
    db_session.refresh(other)

    calls: list[str] = []
    monkeypatch.setattr("app.services.tickets.notify_ticket_transfer_invite_created", lambda invite: calls.append("created"))
    monkeypatch.setattr("app.services.tickets.notify_ticket_transfer_invite_accepted", lambda invite, ticket: calls.append("accepted"))
    monkeypatch.setattr("app.services.tickets.notify_ticket_transfer_invite_revoked", lambda invite: calls.append("revoked"))

    invite = create_ticket_transfer_invite(
        db_session,
        ticket_id=ticket.id,
        sender_user_id=owner.id,
        recipient_user_id=recipient.id,
        recipient_name="Recipient Name",
    )
    assert invite.status == TransferInviteStatus.PENDING
    assert invite.recipient_name == "Recipient Name"
    assert ticket.owner_user_id == owner.id
    assert calls == ["created"]

    with pytest.raises(TicketTransferError):
        create_ticket_transfer_invite(
            db_session,
            ticket_id=ticket.id,
            sender_user_id=owner.id,
            recipient_email=unique_email("next"),
        )

    with pytest.raises(TicketAuthorizationError):
        accept_ticket_transfer_invite(db_session, invite_token=invite.invite_token, accepting_user_id=other.id)

    accepted_ticket = accept_ticket_transfer_invite(
        db_session,
        invite_token=invite.invite_token,
        accepting_user_id=recipient.id,
    )
    assert accepted_ticket.owner_user_id == recipient.id
    assert accepted_ticket.purchaser_user_id == owner.id
    assert accepted_ticket.transfer_count == 1
    assert calls == ["created", "accepted"]

    repeated_accept = accept_ticket_transfer_invite(db_session, invite_token=invite.invite_token, accepting_user_id=recipient.id)
    assert repeated_accept.id == accepted_ticket.id

    invite_2 = create_ticket_transfer_invite(
        db_session,
        ticket_id=ticket.id,
        sender_user_id=recipient.id,
        recipient_email=unique_email("newperson"),
    )
    revoked = revoke_ticket_transfer_invite(db_session, invite_token=invite_2.invite_token, actor_user_id=recipient.id)
    assert revoked.status == TransferInviteStatus.REVOKED
    assert calls == ["created", "accepted", "created", "revoked"]
    with pytest.raises(TicketTransferError):
        accept_ticket_transfer_invite(db_session, invite_token=invite_2.invite_token, accepting_user_id=other.id)


def test_invite_rejects_checked_in_voided_and_expired_and_self(db_session: Session) -> None:
    order, owner, event = _seed_order(db_session, suffix="02")
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    with pytest.raises(TicketTransferError):
        create_ticket_transfer_invite(db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_user_id=owner.id)

    checked_in_ticket = ticket
    checked_in_ticket.status = TicketStatus.CHECKED_IN
    db_session.commit()
    with pytest.raises(TicketTransferError):
        create_ticket_transfer_invite(db_session, ticket_id=checked_in_ticket.id, sender_user_id=owner.id, recipient_email=unique_email("a"))

    order_2, owner_2, _ = _seed_order(db_session, suffix="03")
    ticket_2 = issue_tickets_for_completed_order(db_session, order_2)[0]
    ticket_2.status = TicketStatus.VOIDED
    db_session.commit()
    with pytest.raises(TicketTransferError):
        create_ticket_transfer_invite(db_session, ticket_id=ticket_2.id, sender_user_id=owner_2.id, recipient_email=unique_email("a"))

    order_3, owner_3, _ = _seed_order(db_session, suffix="04")
    ticket_3 = issue_tickets_for_completed_order(db_session, order_3)[0]
    invite = create_ticket_transfer_invite(
        db_session,
        ticket_id=ticket_3.id,
        sender_user_id=owner_3.id,
        recipient_email=unique_email("late"),
        expires_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(TicketTransferError):
        accept_ticket_transfer_invite(db_session, invite_token=invite.invite_token, accepting_user_id=owner_3.id + 999)

    invite = db_session.get(type(invite), invite.id)
    assert invite.status == TransferInviteStatus.EXPIRED
    _ = event


def test_acceptance_requires_matching_email_or_phone(db_session: Session) -> None:
    order, owner, _ = _seed_order(db_session, suffix="06")
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    correct = User(email=unique_email("claim"), full_name="Claim User", phone="+59270066")
    wrong_email = User(email=unique_email("wrong"), full_name="Wrong Email", phone="+59270066")
    wrong_phone = User(email=unique_email("claim2"), full_name="Wrong Phone", phone="+59212345")
    db_session.add_all([correct, wrong_email, wrong_phone])
    db_session.commit()
    db_session.refresh(correct)
    db_session.refresh(wrong_email)
    db_session.refresh(wrong_phone)

    invite = create_ticket_transfer_invite(
        db_session,
        ticket_id=ticket.id,
        sender_user_id=owner.id,
        recipient_email=unique_email("claim"),
        recipient_phone="+59270066",
    )

    with pytest.raises(TicketAuthorizationError):
        accept_ticket_transfer_invite(db_session, invite_token=invite.invite_token, accepting_user_id=wrong_email.id)
    with pytest.raises(TicketAuthorizationError):
        accept_ticket_transfer_invite(db_session, invite_token=invite.invite_token, accepting_user_id=wrong_phone.id)

    accepted = accept_ticket_transfer_invite(db_session, invite_token=invite.invite_token, accepting_user_id=correct.id)
    assert accepted.owner_user_id == correct.id


def test_pending_transfer_blocks_checkin_and_allows_after_cancel(db_session: Session) -> None:
    order, owner, event = _seed_order(db_session, suffix="07")
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    invite = create_ticket_transfer_invite(
        db_session,
        ticket_id=ticket.id,
        sender_user_id=owner.id,
        recipient_email=unique_email("pending"),
    )

    pending = get_active_pending_transfer_for_ticket(db_session, ticket_id=ticket.id)
    assert pending is not None

    blocked = validate_ticket_for_check_in(
        db_session,
        actor_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload=ticket.qr_payload,
        ticket_code=None,
    )
    assert blocked.status == CHECK_IN_STATUS_TRANSFER_PENDING

    revoke_ticket_transfer_invite(db_session, invite_token=invite.invite_token, actor_user_id=owner.id)
    allowed = validate_ticket_for_check_in(
        db_session,
        actor_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload=ticket.qr_payload,
        ticket_code=None,
    )
    assert allowed.status == "valid"


def test_transfer_invite_auto_binds_existing_user_by_email(db_session: Session) -> None:
    order, owner, _ = _seed_order(db_session, suffix="08")
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    recipient = User(email=unique_email("known"), full_name="Known User")
    db_session.add(recipient)
    db_session.commit()
    db_session.refresh(recipient)

    invite = create_ticket_transfer_invite(
        db_session,
        ticket_id=ticket.id,
        sender_user_id=owner.id,
        recipient_email=unique_email("KNOWN"),
    )
    assert invite.recipient_user_id == recipient.id


def test_direct_transfer_compatibility(db_session: Session) -> None:
    order, owner, _ = _seed_order(db_session, suffix="05")
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    recipient = User(email=unique_email("direct"), full_name="Direct Recipient")
    db_session.add(recipient)
    db_session.commit()
    db_session.refresh(recipient)

    transferred = transfer_ticket_to_user(db_session, ticket_id=ticket.id, from_user_id=owner.id, to_user_id=recipient.id)
    assert transferred.owner_user_id == recipient.id
