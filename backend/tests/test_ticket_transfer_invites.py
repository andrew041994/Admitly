from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Event, OrganizerProfile, Order, OrderItem, Ticket, TicketTier, TicketTransferInvite, TicketTransferRecipientResolution, User, Venue
from app.models.enums import (
    EventApprovalStatus,
    EventStatus,
    EventVisibility,
    OrderStatus,
    TicketStatus,
    TransferInviteStatus,
)
from app.services.ticket_qr import generate_ticket_qr_payload
from app.services.ticket_wallet import list_wallet_tickets
from app.services.tickets import (
    CHECK_IN_STATUS_TRANSFER_PENDING,
    TicketAuthorizationError,
    TicketNotFoundError,
    TicketTransferConflictError,
    TicketTransferError,
    TicketTransferResolutionExpiredError,
    accept_ticket_transfer,
    cancel_ticket_transfer,
    check_in_ticket,
    create_ticket_transfer_from_resolution,
    decline_ticket_transfer,
    issue_tickets_for_completed_order,
    resolve_ticket_transfer_recipient,
    scan_ticket,
    validate_ticket_for_check_in,
)
from tests.conftest import engine
from tests.utils import unique_email
from app.api.ticket_transfer_invites import (
    resolve_transfer_recipient as resolve_transfer_recipient_endpoint,
    router as transfer_router,
)
from app.schemas.ticket_transfer_invite import CreateTicketTransferRequest, ResolveTicketTransferRecipientRequest


def _phone(seed: int) -> str:
    return f"+5926{seed:06d}"


def _user(db: Session, name: str, *, verified_email: bool = True, verified_phone: bool = False, with_phone: bool = True) -> User:
    user = User(
        email=unique_email(name),
        full_name=name.title(),
        phone=None,
        is_active=True,
        is_verified=verified_email,
        phone_verified_at=datetime.now(timezone.utc) if verified_phone else None,
    )
    db.add(user)
    db.flush()
    if with_phone:
        user.phone = f"+592{user.id:07d}"
    return user


def _seed_ticket(db: Session, *, suffix: str = "secure"):
    now = datetime.now(timezone.utc)
    owner = _user(db, f"owner-{suffix}")
    organizer_user = _user(db, f"organizer-{suffix}")
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
        slug=f"event-{suffix}-{abs(hash(unique_email(suffix)))}",
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
        tier_code=f"GEN-{suffix}-{event.id}",
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
        user_id=owner.id,
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
    ticket = issue_tickets_for_completed_order(db, order)[0]
    return ticket, owner, event, order


@pytest.fixture(autouse=True)
def _disable_transfer_notifications(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.tickets.notify_ticket_transfer_invite_created", lambda invite: None)
    monkeypatch.setattr("app.services.tickets.notify_ticket_transfer_invite_accepted", lambda invite, ticket: None)
    monkeypatch.setattr("app.services.tickets.notify_ticket_transfer_canceled", lambda invite: None)
    monkeypatch.setattr("app.services.tickets.publish_webhook_event", lambda *args, **kwargs: None)


def create_ticket_transfer(
    db: Session,
    *,
    ticket_id: int,
    sender_user_id: int,
    recipient_type: str,
    recipient_identifier: str,
):
    """Test helper that exercises the same two-step email flow as the API."""
    if recipient_type != "email":
        raise TicketTransferError("Phone transfers are unavailable until phone verification is supported.")
    try:
        _, _, reference = resolve_ticket_transfer_recipient(
            db,
            ticket_id=ticket_id,
            sender_user_id=sender_user_id,
            recipient_email=recipient_identifier,
        )
    except TicketNotFoundError as exc:
        if "eligible verified Admitly account" in str(exc):
            return None
        raise
    return create_ticket_transfer_from_resolution(
        db,
        ticket_id=ticket_id,
        sender_user_id=sender_user_id,
        recipient_resolution_reference=reference,
    )


def test_owner_creates_pending_email_transfer_and_unknown_lookup_is_neutral(db_session: Session) -> None:
    ticket, owner, _, _ = _seed_ticket(db_session, suffix="create")
    recipient = _user(db_session, "recipient-create")
    db_session.commit()

    invite = create_ticket_transfer(
        db_session,
        ticket_id=ticket.id,
        sender_user_id=owner.id,
        recipient_type="email",
        recipient_identifier=recipient.email.upper(),
    )
    assert invite is not None
    assert invite.status == TransferInviteStatus.PENDING
    assert invite.recipient_user_id == recipient.id
    assert db_session.get(type(ticket), ticket.id).owner_user_id == owner.id

    other_ticket, other_owner, _, _ = _seed_ticket(db_session, suffix="unknown")
    assert create_ticket_transfer(
        db_session,
        ticket_id=other_ticket.id,
        sender_user_id=other_owner.id,
        recipient_type="email",
        recipient_identifier="missing@example.com",
    ) is None


def test_lookup_returns_confirmation_without_creating_or_reserving_transfer(db_session: Session) -> None:
    ticket, owner, _, _ = _seed_ticket(db_session, suffix="resolve")
    recipient = _user(db_session, "recipient-resolve", with_phone=False)
    owner.phone = None
    db_session.commit()

    resolution, resolved_user, reference = resolve_ticket_transfer_recipient(
        db_session,
        ticket_id=ticket.id,
        sender_user_id=owner.id,
        recipient_email=f"  {recipient.email.upper()}  ",
    )

    assert resolved_user.id == recipient.id
    assert resolution.recipient_email_hash != recipient.email
    assert len(reference) >= 32
    assert reference != resolution.token_hash
    assert db_session.scalar(select(func.count(TicketTransferInvite.id)).where(TicketTransferInvite.ticket_id == ticket.id)) == 0
    assert db_session.get(Ticket, ticket.id).owner_user_id == owner.id
    assert validate_ticket_for_check_in(
        db_session,
        actor_user_id=ticket.event.organizer.user_id,
        event_id=ticket.event_id,
        qr_payload=ticket.qr_token,
    ).valid is True


@pytest.mark.parametrize("recipient_state", ["unknown", "unverified", "inactive", "partial", "wildcard"])
def test_unavailable_recipient_lookup_is_truthful_and_creates_no_history(
    db_session: Session,
    recipient_state: str,
) -> None:
    ticket, owner, _, _ = _seed_ticket(db_session, suffix=f"unavailable-{recipient_state}")
    recipient = _user(db_session, f"recipient-{recipient_state}")
    if recipient_state == "unverified":
        recipient.is_verified = False
    elif recipient_state == "inactive":
        recipient.is_active = False
    db_session.commit()
    email = {
        "unknown": "missing@example.com",
        "partial": recipient.email.split("@", 1)[0],
        "wildcard": f"%{recipient.email}",
    }.get(recipient_state, recipient.email)

    if recipient_state == "partial":
        with pytest.raises(TicketTransferError, match="valid email"):
            resolve_ticket_transfer_recipient(
                db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_email=email
            )
    else:
        with pytest.raises(TicketNotFoundError, match="eligible verified Admitly account"):
            resolve_ticket_transfer_recipient(
                db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_email=email
            )
    assert db_session.scalar(select(func.count(TicketTransferInvite.id)).where(TicketTransferInvite.ticket_id == ticket.id)) == 0
    assert db_session.scalar(select(func.count(TicketTransferRecipientResolution.id)).where(TicketTransferRecipientResolution.ticket_id == ticket.id)) == 0
    assert db_session.get(Ticket, ticket.id).owner_user_id == owner.id


def test_resolution_reference_is_sender_ticket_expiry_and_replay_bound(db_session: Session) -> None:
    ticket, owner, _, _ = _seed_ticket(db_session, suffix="reference")
    recipient = _user(db_session, "recipient-reference", with_phone=False)
    outsider = _user(db_session, "outsider-reference", with_phone=False)
    other_ticket, _, _, _ = _seed_ticket(db_session, suffix="reference-other")
    db_session.commit()
    resolution, _, reference = resolve_ticket_transfer_recipient(
        db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_email=recipient.email
    )

    with pytest.raises(TicketAuthorizationError):
        create_ticket_transfer_from_resolution(
            db_session, ticket_id=ticket.id, sender_user_id=outsider.id,
            recipient_resolution_reference=reference,
        )
    with pytest.raises(TicketAuthorizationError):
        create_ticket_transfer_from_resolution(
            db_session, ticket_id=other_ticket.id, sender_user_id=owner.id,
            recipient_resolution_reference=reference,
        )

    invite = create_ticket_transfer_from_resolution(
        db_session, ticket_id=ticket.id, sender_user_id=owner.id,
        recipient_resolution_reference=reference,
    )
    assert invite.status == TransferInviteStatus.PENDING
    with pytest.raises(TicketTransferResolutionExpiredError):
        create_ticket_transfer_from_resolution(
            db_session, ticket_id=ticket.id, sender_user_id=owner.id,
            recipient_resolution_reference=reference,
        )
    assert db_session.scalar(select(func.count(TicketTransferInvite.id)).where(TicketTransferInvite.ticket_id == ticket.id)) == 1

    ticket_2, owner_2, _, _ = _seed_ticket(db_session, suffix="reference-expired")
    resolution_2, _, reference_2 = resolve_ticket_transfer_recipient(
        db_session, ticket_id=ticket_2.id, sender_user_id=owner_2.id, recipient_email=recipient.email
    )
    resolution_2.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(TicketTransferResolutionExpiredError):
        create_ticket_transfer_from_resolution(
            db_session, ticket_id=ticket_2.id, sender_user_id=owner_2.id,
            recipient_resolution_reference=reference_2,
        )


def test_missing_phone_does_not_block_email_creation_or_acceptance(db_session: Session) -> None:
    ticket, owner, _, _ = _seed_ticket(db_session, suffix="no-phone")
    recipient = _user(db_session, "recipient-no-phone", with_phone=False)
    owner.phone = None
    db_session.commit()
    resolution, _, reference = resolve_ticket_transfer_recipient(
        db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_email=recipient.email
    )
    assert resolution.recipient_user_id == recipient.id
    invite = create_ticket_transfer_from_resolution(
        db_session, ticket_id=ticket.id, sender_user_id=owner.id,
        recipient_resolution_reference=reference,
    )
    assert accept_ticket_transfer(
        db_session, transfer_id=invite.id, accepting_user_id=recipient.id
    ).status == TransferInviteStatus.ACCEPTED


def test_transfer_api_contract_is_authenticated_ticket_scoped_and_rejects_raw_recipient_ids() -> None:
    paths = {route.path for route in transfer_router.routes}
    assert "/tickets/{ticket_id}/transfer-recipient-resolutions" in paths
    assert not any("users" in path or "search" in path for path in paths)
    for route in transfer_router.routes:
        assert route.path.startswith("/tickets/") or route.path.startswith("/ticket-transfers/") or route.path == "/me/ticket-transfers"
        dependency_names = {dependency.call.__name__ for dependency in route.dependant.dependencies if dependency.call}
        assert "get_current_user_id" in dependency_names
    with pytest.raises(ValidationError):
        CreateTicketTransferRequest(
            recipient_resolution_reference="x" * 43,
            recipient_user_id=123,
        )
    assert ResolveTicketTransferRecipientRequest(email=" Person@Example.COM ").email == "person@example.com"


def test_resolution_endpoint_returns_only_confirmation_fields_and_is_rate_limited(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticket, owner, _, _ = _seed_ticket(db_session, suffix="endpoint")
    recipient = _user(db_session, "recipient-endpoint", with_phone=False)
    owner.phone = None
    db_session.commit()
    rate_limit_calls: list[dict] = []
    monkeypatch.setattr(
        "app.api.ticket_transfer_invites.apply_rate_limit",
        lambda **kwargs: rate_limit_calls.append(kwargs),
    )

    response = resolve_transfer_recipient_endpoint(
        ticket_id=ticket.id,
        payload=ResolveTicketTransferRecipientRequest(email=recipient.email.upper()),
        db=db_session,
        user_id=owner.id,
        client_ip="192.0.2.1",
    )

    assert set(response.model_dump()) == {
        "recipient_display_name",
        "recipient_email",
        "masked_email",
        "recipient_resolution_reference",
        "resolution_expires_at",
    }
    assert response.recipient_display_name == recipient.full_name
    assert response.recipient_email == recipient.email
    assert rate_limit_calls[0]["scope"] == "ticket_transfer_recipient_resolve"


def test_phone_transfer_is_not_accepted_by_active_transfer_schema() -> None:
    with pytest.raises(ValidationError):
        ResolveTicketTransferRecipientRequest(email="+5926001234")
    with pytest.raises(ValidationError):
        CreateTicketTransferRequest(
            recipient_resolution_reference="x" * 43,
            recipient_type="phone",
        )


def test_non_owner_self_invalid_and_second_pending_are_rejected(db_session: Session) -> None:
    ticket, owner, _, _ = _seed_ticket(db_session, suffix="reject")
    recipient = _user(db_session, "recipient-reject")
    outsider = _user(db_session, "outsider-reject")
    db_session.commit()
    with pytest.raises(TicketAuthorizationError):
        create_ticket_transfer(db_session, ticket_id=ticket.id, sender_user_id=outsider.id, recipient_type="email", recipient_identifier=recipient.email)
    with pytest.raises(TicketTransferError, match="yourself"):
        create_ticket_transfer(db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_type="email", recipient_identifier=owner.email)
    with pytest.raises(TicketTransferError):
        create_ticket_transfer(db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_type="not-a-mode", recipient_identifier="x")
    assert create_ticket_transfer(db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_type="email", recipient_identifier=recipient.email)
    with pytest.raises(TicketTransferConflictError):
        create_ticket_transfer(db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_type="email", recipient_identifier=outsider.email)


@pytest.mark.parametrize("state", ["checked_in", "voided", "refunded", "canceled", "ended"])
def test_ineligible_ticket_states_are_rejected(db_session: Session, state: str) -> None:
    ticket, owner, event, order = _seed_ticket(db_session, suffix=f"state-{state}")
    recipient = _user(db_session, f"recipient-{state}")
    if state == "checked_in":
        ticket.status = TicketStatus.CHECKED_IN
    elif state == "voided":
        ticket.status = TicketStatus.VOIDED
    elif state == "refunded":
        order.refund_status = "refunded"
    elif state == "canceled":
        order.status = OrderStatus.CANCELLED
    else:
        event.end_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    with pytest.raises(TicketTransferError):
        create_ticket_transfer(db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_type="email", recipient_identifier=recipient.email)


def test_accept_is_atomic_idempotent_and_rotates_all_entry_credentials(db_session: Session) -> None:
    ticket, owner, event, _ = _seed_ticket(db_session, suffix="accept")
    recipient = _user(db_session, "recipient-accept")
    wrong = _user(db_session, "wrong-accept")
    db_session.commit()
    old_qr = generate_ticket_qr_payload(ticket)
    old_manual = ticket.manual_code
    old_code = ticket.ticket_code
    invite = create_ticket_transfer(db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_type="email", recipient_identifier=recipient.email)
    assert invite is not None
    with pytest.raises(TicketAuthorizationError):
        accept_ticket_transfer(db_session, transfer_id=invite.id, accepting_user_id=wrong.id)

    accepted = accept_ticket_transfer(db_session, transfer_id=invite.id, accepting_user_id=recipient.id)
    refreshed = db_session.get(type(ticket), ticket.id)
    assert accepted.status == TransferInviteStatus.ACCEPTED
    assert refreshed.owner_user_id == recipient.id
    assert refreshed.ticket_code != old_code
    assert refreshed.manual_code != old_manual
    assert refreshed.qr_token != old_qr["qr_token"]
    assert accept_ticket_transfer(db_session, transfer_id=invite.id, accepting_user_id=recipient.id).status == TransferInviteStatus.ACCEPTED
    assert db_session.get(type(ticket), ticket.id).transfer_count == 1

    old_scan = scan_ticket(db_session, payload=old_qr, user_id=event.organizer.user_id)
    assert old_scan.status == "INVALID"


def test_sender_cancel_recipient_decline_and_stale_actions_conflict(db_session: Session) -> None:
    ticket, owner, _, _ = _seed_ticket(db_session, suffix="cancel")
    recipient = _user(db_session, "recipient-cancel")
    db_session.commit()
    invite = create_ticket_transfer(db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_type="email", recipient_identifier=recipient.email)
    assert invite is not None
    assert cancel_ticket_transfer(db_session, transfer_id=invite.id, sender_user_id=owner.id).status == TransferInviteStatus.CANCELED
    with pytest.raises(TicketTransferConflictError):
        accept_ticket_transfer(db_session, transfer_id=invite.id, accepting_user_id=recipient.id)

    ticket_2, owner_2, _, _ = _seed_ticket(db_session, suffix="decline")
    recipient_2 = _user(db_session, "recipient-decline")
    db_session.commit()
    invite_2 = create_ticket_transfer(db_session, ticket_id=ticket_2.id, sender_user_id=owner_2.id, recipient_type="email", recipient_identifier=recipient_2.email)
    assert invite_2 is not None
    assert decline_ticket_transfer(db_session, transfer_id=invite_2.id, recipient_user_id=recipient_2.id).status == TransferInviteStatus.DECLINED
    with pytest.raises(TicketTransferConflictError):
        cancel_ticket_transfer(db_session, transfer_id=invite_2.id, sender_user_id=owner_2.id)


def test_pending_blocks_checkin_and_wallet_moves_only_after_acceptance(db_session: Session) -> None:
    ticket, owner, event, _ = _seed_ticket(db_session, suffix="wallet")
    recipient = _user(db_session, "recipient-wallet")
    db_session.commit()
    invite = create_ticket_transfer(db_session, ticket_id=ticket.id, sender_user_id=owner.id, recipient_type="email", recipient_identifier=recipient.email)
    assert invite is not None
    assert [view.ticket.id for view in list_wallet_tickets(db_session, user_id=owner.id)] == [ticket.id]
    assert list_wallet_tickets(db_session, user_id=recipient.id) == []
    blocked = validate_ticket_for_check_in(
        db_session,
        actor_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload=ticket.qr_token,
    )
    assert blocked.status == CHECK_IN_STATUS_TRANSFER_PENDING
    accept_ticket_transfer(db_session, transfer_id=invite.id, accepting_user_id=recipient.id)
    assert list_wallet_tickets(db_session, user_id=owner.id) == []
    assert [view.ticket.id for view in list_wallet_tickets(db_session, user_id=recipient.id)] == [ticket.id]


def test_acceptance_and_cancellation_race_has_one_terminal_result() -> None:
    with Session(engine) as setup:
        ticket, owner, _, _ = _seed_ticket(setup, suffix=f"race-cancel-{datetime.now().timestamp()}")
        recipient = _user(setup, "recipient-race-cancel")
        setup.commit()
        invite = create_ticket_transfer(setup, ticket_id=ticket.id, sender_user_id=owner.id, recipient_type="email", recipient_identifier=recipient.email)
        assert invite is not None
        transfer_id, owner_id, recipient_id = invite.id, owner.id, recipient.id

    barrier = Barrier(2)

    def accept():
        with Session(engine) as session:
            barrier.wait()
            try:
                return accept_ticket_transfer(session, transfer_id=transfer_id, accepting_user_id=recipient_id).status.value
            except TicketTransferConflictError:
                return "conflict"

    def cancel():
        with Session(engine) as session:
            barrier.wait()
            try:
                return cancel_ticket_transfer(session, transfer_id=transfer_id, sender_user_id=owner_id).status.value
            except TicketTransferConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        accept_future = pool.submit(accept)
        cancel_future = pool.submit(cancel)
        results = {accept_future.result(), cancel_future.result()}
    assert "conflict" in results
    assert results & {"accepted", "canceled"}
    with Session(engine) as verify:
        final = verify.get(TicketTransferInvite, transfer_id)
        assert final.status in {TransferInviteStatus.ACCEPTED, TransferInviteStatus.CANCELED}


def test_checkin_and_acceptance_race_cannot_use_sender_credential() -> None:
    with Session(engine) as setup:
        ticket, owner, event, _ = _seed_ticket(setup, suffix=f"race-checkin-{datetime.now().timestamp()}")
        recipient = _user(setup, "recipient-race-checkin")
        setup.commit()
        old_qr_token = ticket.qr_token
        invite = create_ticket_transfer(setup, ticket_id=ticket.id, sender_user_id=owner.id, recipient_type="email", recipient_identifier=recipient.email)
        assert invite is not None
        transfer_id, recipient_id, event_id, scanner_id, ticket_id = invite.id, recipient.id, event.id, event.organizer.user_id, ticket.id

    barrier = Barrier(2)

    def accept():
        with Session(engine) as session:
            barrier.wait()
            return accept_ticket_transfer(session, transfer_id=transfer_id, accepting_user_id=recipient_id).status.value

    def checkin():
        with Session(engine) as session:
            barrier.wait()
            result = check_in_ticket(
                session,
                scanner_user_id=scanner_id,
                event_id=event_id,
                qr_payload=old_qr_token,
            )
            return result.valid, result.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        accept_future = pool.submit(accept)
        checkin_future = pool.submit(checkin)
        assert accept_future.result() == "accepted"
        assert checkin_future.result()[0] is False
    with Session(engine) as verify:
        refreshed = verify.get(Ticket, ticket_id)
        assert refreshed.owner_user_id == recipient_id
        assert refreshed.status == TicketStatus.ISSUED
