from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os

from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Event, EventStaff, OrganizerProfile, Order, OrderItem, Ticket, TicketScanLog, TicketTier, User, Venue
from app.models.enums import (
    CheckInStatus,
    EventApprovalStatus,
    EventStaffRole,
    EventStatus,
    EventVisibility,
    OrderStatus,
    TicketStatus,
)
from app.api.tickets import check_in_event_ticket, get_ticket_detail, get_ticket_qr_by_ticket_id
from app.schemas.ticket import TicketCheckInRequest
from app.services.orders import complete_paid_order
from app.services.ticket_qr import (
    QR_PAYLOAD_PREFIX,
    build_ticket_qr_payload,
    ensure_ticket_qr,
    generate_qr_png_bytes,
    generate_signed_ticket_qr_payload,
    generate_ticket_qr_payload,
)
from app.services.tickets import (
    CHECK_IN_METHOD_MANUAL,
    CHECK_IN_STATUS_MANUAL_OVERRIDE_ADMITTED,
    CHECK_IN_STATUS_ALREADY_CHECKED_IN,
    CHECK_IN_STATUS_CANCELED_EVENT,
    CHECK_IN_STATUS_NOT_FOUND,
    CHECK_IN_STATUS_ORDER_NOT_ADMITTABLE,
    CHECK_IN_STATUS_VALID,
    CHECK_IN_STATUS_WRONG_EVENT,
    TicketAuthorizationError,
    TicketCheckInConflictError,
    TicketCrossEventError,
    TicketIssuanceError,
    TicketNotFoundError,
    TicketTransferError,
    TicketVoidError,
    check_in_ticket,
    can_check_in_event_tickets,
    can_void_event_ticket,
    check_in_ticket_for_event,
    get_event_check_in_summary,
    issue_tickets_for_completed_order,
    list_recent_check_in_attempts,
    list_tickets_for_order_owner,
    list_tickets_for_user,
    override_ticket_check_in,
    transfer_ticket_to_user,
    validate_ticket_for_check_in,
    void_ticket,
    scan_ticket,
)
from app.services.ticket_wallet import get_wallet_ticket, list_wallet_tickets



def _seed_order(
    db: Session,
    *,
    user_email: str = "buyer@example.com",
    quantity: int = 3,
    status: OrderStatus = OrderStatus.COMPLETED,
    payment_verification_status: str = "verified",
) -> tuple[Order, OrderItem, TicketTier, User, Event]:
    now = datetime.now(timezone.utc)
    user = User(email=user_email, full_name="Buyer")
    db.add(user)
    db.flush()

    organizer_profile = OrganizerProfile(user_id=user.id, business_name="Org", display_name="Org")
    db.add(organizer_profile)
    db.flush()

    venue = Venue(organizer_id=organizer_profile.id, name="Venue")
    db.add(venue)
    db.flush()

    event = Event(
        organizer_id=organizer_profile.id,
        venue_id=venue.id,
        title="Show",
        slug=f"show-{user_email}-{quantity}",
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
        tier_code=f"GEN-{user.id}",
        price_amount=Decimal("150.00"),
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
        user_id=user.id,
        event_id=event.id,
        status=status,
        total_amount=Decimal(quantity) * Decimal("150.00"),
        currency="GYD",
        payment_verification_status=payment_verification_status,
    )
    db.add(order)
    db.flush()

    order_item = OrderItem(order_id=order.id, ticket_tier_id=tier.id, quantity=quantity, unit_price=Decimal("150.00"))
    db.add(order_item)
    db.commit()
    db.refresh(order)
    db.refresh(order_item)
    db.refresh(user)
    db.refresh(event)
    db.refresh(tier)
    return order, order_item, tier, user, event


def test_completed_paid_order_issues_one_ticket_per_quantity(db_session: Session) -> None:
    order, _, _, _, _ = _seed_order(db_session, quantity=3)
    tickets = issue_tickets_for_completed_order(db_session, order)
    assert len(tickets) == 3
    assert all(ticket.status == TicketStatus.ISSUED for ticket in tickets)


def test_issuance_is_idempotent_and_no_duplicates(db_session: Session) -> None:
    order, _, _, _, _ = _seed_order(db_session, quantity=2)
    first = issue_tickets_for_completed_order(db_session, order)
    second = issue_tickets_for_completed_order(db_session, order)
    assert len(first) == 2
    assert [t.id for t in first] == [t.id for t in second]


def test_pending_cancelled_expired_orders_do_not_issue_tickets(db_session: Session) -> None:
    for status in (OrderStatus.PENDING, OrderStatus.CANCELLED, OrderStatus.EXPIRED):
        order, _, _, _, _ = _seed_order(
            db_session,
            user_email=f"{status.value}@example.com",
            status=status,
            payment_verification_status="verified",
        )
        with pytest.raises(TicketIssuanceError):
            issue_tickets_for_completed_order(db_session, order)


def test_issued_ticket_links_match_order_and_item(db_session: Session) -> None:
    order, item, tier, user, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    assert ticket.order_id == order.id
    assert ticket.order_item_id == item.id
    assert ticket.user_id == user.id
    assert ticket.purchaser_user_id == user.id
    assert ticket.owner_user_id == user.id
    assert ticket.event_id == event.id
    assert ticket.ticket_tier_id == tier.id


def test_payment_completion_path_issues_tickets_once(db_session: Session) -> None:
    order, _, _, _, _ = _seed_order(db_session, quantity=2)
    complete_paid_order(db_session, order)
    complete_paid_order(db_session, order)
    tickets = db_session.execute(select(Ticket).where(Ticket.order_id == order.id)).scalars().all()
    assert len(tickets) == 2


def test_payment_initiation_only_state_does_not_issue(db_session: Session) -> None:
    order, _, _, _, _ = _seed_order(
        db_session,
        status=OrderStatus.PENDING,
        payment_verification_status="pending",
    )
    with pytest.raises(TicketIssuanceError):
        issue_tickets_for_completed_order(db_session, order)


def test_user_can_retrieve_own_tickets_only(db_session: Session) -> None:
    order, _, _, buyer, _ = _seed_order(db_session, quantity=2)
    issue_tickets_for_completed_order(db_session, order)

    own_tickets = list_tickets_for_user(db_session, user_id=buyer.id)
    assert len(own_tickets) == 2

    other = User(email="other-buyer@example.com", full_name="Other")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    assert list_tickets_for_user(db_session, user_id=other.id) == []


def test_owner_can_transfer_ticket_and_purchaser_is_immutable(db_session: Session) -> None:
    order, _, _, buyer, _ = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    recipient = User(email="recipient@example.com", full_name="Recipient")
    db_session.add(recipient)
    db_session.commit()
    db_session.refresh(recipient)

    transferred = transfer_ticket_to_user(
        db_session,
        ticket_id=ticket.id,
        from_user_id=buyer.id,
        to_user_id=recipient.id,
    )

    assert transferred.purchaser_user_id == buyer.id
    assert transferred.owner_user_id == recipient.id
    assert transferred.user_id == recipient.id
    assert transferred.transfer_count == 1
    assert transferred.transferred_at is not None


def test_transfer_rejects_non_owner_checked_in_voided_self_and_unknown_user(db_session: Session) -> None:
    order, _, _, buyer, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    unrelated = User(email="unrelated@example.com", full_name="Unrelated")
    recipient = User(email="recipient-2@example.com", full_name="Recipient")
    db_session.add_all([unrelated, recipient])
    db_session.commit()
    db_session.refresh(unrelated)
    db_session.refresh(recipient)

    with pytest.raises(TicketAuthorizationError):
        transfer_ticket_to_user(
            db_session,
            ticket_id=ticket.id,
            from_user_id=unrelated.id,
            to_user_id=recipient.id,
        )

    with pytest.raises(TicketTransferError):
        transfer_ticket_to_user(
            db_session,
            ticket_id=ticket.id,
            from_user_id=buyer.id,
            to_user_id=buyer.id,
        )

    check_in_ticket_for_event(
        db_session,
        scanner_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload=ticket.qr_payload,
        ticket_code=None,
    )
    with pytest.raises(TicketTransferError):
        transfer_ticket_to_user(
            db_session,
            ticket_id=ticket.id,
            from_user_id=buyer.id,
            to_user_id=recipient.id,
        )

    order_2, _, _, buyer_2, _ = _seed_order(db_session, user_email="buyer2@example.com", quantity=1)
    ticket_2 = issue_tickets_for_completed_order(db_session, order_2)[0]
    ticket_2.status = TicketStatus.VOIDED
    db_session.commit()
    with pytest.raises(TicketTransferError):
        transfer_ticket_to_user(
            db_session,
            ticket_id=ticket_2.id,
            from_user_id=buyer_2.id,
            to_user_id=recipient.id,
        )

    with pytest.raises(TicketTransferError):
        transfer_ticket_to_user(
            db_session,
            ticket_id=ticket_2.id,
            from_user_id=buyer_2.id,
            to_user_id=999999,
        )


def test_partial_and_full_transfer_and_order_history_views(db_session: Session) -> None:
    order, _, _, buyer, _ = _seed_order(db_session, quantity=4)
    tickets = issue_tickets_for_completed_order(db_session, order)
    recipient = User(email="recipient-3@example.com", full_name="Recipient")
    db_session.add(recipient)
    db_session.commit()
    db_session.refresh(recipient)

    transfer_ticket_to_user(db_session, ticket_id=tickets[0].id, from_user_id=buyer.id, to_user_id=recipient.id)
    buyer_owned = list_tickets_for_user(db_session, user_id=buyer.id)
    recipient_owned = list_tickets_for_user(db_session, user_id=recipient.id)
    assert len(buyer_owned) == 3
    assert len(recipient_owned) == 1

    for t in tickets[1:]:
        transfer_ticket_to_user(db_session, ticket_id=t.id, from_user_id=buyer.id, to_user_id=recipient.id)

    assert list_tickets_for_user(db_session, user_id=buyer.id) == []
    assert len(list_tickets_for_user(db_session, user_id=recipient.id)) == 4
    assert len(list_tickets_for_order_owner(db_session, order_id=order.id, user_id=buyer.id)) == 4


def test_user_cannot_retrieve_another_users_order_tickets(db_session: Session) -> None:
    order, _, _, _, _ = _seed_order(db_session, quantity=1)
    issue_tickets_for_completed_order(db_session, order)

    other = User(email="forbidden@example.com", full_name="Forbidden")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    with pytest.raises(TicketAuthorizationError):
        list_tickets_for_order_owner(db_session, order_id=order.id, user_id=other.id)


def test_organizer_and_staff_authz_for_checkin(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    organizer_user_id = event.organizer.user_id
    assert can_check_in_event_tickets(db_session, user_id=organizer_user_id, event_id=event.id)

    staff_user = User(email="staff@example.com", full_name="Staff")
    db_session.add(staff_user)
    db_session.flush()
    db_session.add(
        EventStaff(
            event_id=event.id,
            user_id=staff_user.id,
            role=EventStaffRole.CHECKIN,
            is_active=True,
            invited_by_user_id=organizer_user_id,
        )
    )
    db_session.commit()

    assert can_check_in_event_tickets(db_session, user_id=staff_user.id, event_id=event.id)
    check_in_ticket_for_event(
        db_session,
        scanner_user_id=staff_user.id,
        event_id=event.id,
        qr_payload=ticket.qr_payload,
        ticket_code=None,
    )


def test_unrelated_user_cannot_check_in(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    outsider = User(email="outsider@example.com", full_name="Outsider")
    db_session.add(outsider)
    db_session.commit()
    db_session.refresh(outsider)

    with pytest.raises(TicketAuthorizationError):
        check_in_ticket_for_event(
            db_session,
            scanner_user_id=outsider.id,
            event_id=event.id,
            qr_payload=ticket.qr_payload,
            ticket_code=None,
        )


def test_checkin_success_and_second_scan_rejected(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    scanned = check_in_ticket_for_event(
        db_session,
        scanner_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload=ticket.qr_payload,
        ticket_code=None,
    )
    assert scanned.status == TicketStatus.CHECKED_IN

    with pytest.raises(TicketCheckInConflictError):
        check_in_ticket_for_event(
            db_session,
            scanner_user_id=event.organizer.user_id,
            event_id=event.id,
            qr_payload=ticket.qr_payload,
            ticket_code=None,
        )


def test_event_scoped_one_step_route_returns_green_on_admit_and_red_on_duplicate(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    first = check_in_event_ticket(
        event_id=event.id,
        payload=TicketCheckInRequest(qr_payload=ticket.qr_payload),
        db=db_session,
        user_id=event.organizer.user_id,
    )
    assert first.success is True
    assert first.code == "admitted"
    assert first.message == "Admitted"
    assert first.ui_signal == "green"
    assert first.ticket_id == ticket.id
    assert first.checked_in_at is not None

    second = check_in_event_ticket(
        event_id=event.id,
        payload=TicketCheckInRequest(qr_payload=ticket.qr_payload),
        db=db_session,
        user_id=event.organizer.user_id,
    )
    assert second.success is False
    assert second.code == "already_used"
    assert second.message == "Ticket already used"
    assert second.ui_signal == "red"
    assert second.ticket_id == ticket.id


def test_event_scoped_one_step_route_returns_red_for_wrong_event_and_unauthorized(db_session: Session) -> None:
    order_1, _, _, _, event_1 = _seed_order(db_session, user_email="route-a@example.com", quantity=1)
    order_2, _, _, _, event_2 = _seed_order(db_session, user_email="route-b@example.com", quantity=1)
    ticket_1 = issue_tickets_for_completed_order(db_session, order_1)[0]
    issue_tickets_for_completed_order(db_session, order_2)

    wrong_event = check_in_event_ticket(
        event_id=event_2.id,
        payload=TicketCheckInRequest(qr_payload=ticket_1.qr_payload),
        db=db_session,
        user_id=event_2.organizer.user_id,
    )
    assert wrong_event.success is False
    assert wrong_event.code == "wrong_event"
    assert wrong_event.message == "Wrong event"
    assert wrong_event.ui_signal == "red"
    assert wrong_event.ticket_id == ticket_1.id

    outsider = User(email="route-outsider@example.com", full_name="Outsider")
    db_session.add(outsider)
    db_session.commit()
    db_session.refresh(outsider)

    unauthorized = check_in_event_ticket(
        event_id=event_1.id,
        payload=TicketCheckInRequest(qr_payload=ticket_1.qr_payload),
        db=db_session,
        user_id=outsider.id,
    )
    assert unauthorized.success is False
    assert unauthorized.code == "unauthorized"
    assert unauthorized.message == "You are not authorized to check in tickets for this event"
    assert unauthorized.ui_signal == "red"
    assert unauthorized.ticket_id is None


def test_event_scoped_one_step_route_returns_red_for_invalid_not_found_and_voided(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    invalid = check_in_event_ticket(
        event_id=event.id,
        payload=TicketCheckInRequest(qr_payload=""),
        db=db_session,
        user_id=event.organizer.user_id,
    )
    assert invalid.success is False
    assert invalid.code == "invalid_qr"
    assert invalid.message == "Invalid ticket"
    assert invalid.ui_signal == "red"

    missing = check_in_event_ticket(
        event_id=event.id,
        payload=TicketCheckInRequest(qr_payload="missing-ticket-token"),
        db=db_session,
        user_id=event.organizer.user_id,
    )
    assert missing.success is False
    assert missing.code == "not_found"
    assert missing.message == "Ticket not found"
    assert missing.ui_signal == "red"

    ticket.status = TicketStatus.VOIDED
    db_session.commit()

    voided = check_in_event_ticket(
        event_id=event.id,
        payload=TicketCheckInRequest(qr_payload=ticket.qr_payload),
        db=db_session,
        user_id=event.organizer.user_id,
    )
    assert voided.success is False
    assert voided.code == "voided"
    assert voided.message == "Ticket voided"
    assert voided.ui_signal == "red"


def test_validate_ticket_statuses_for_qr_flow(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    valid = validate_ticket_for_check_in(
        db_session,
        actor_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload=ticket.qr_payload,
    )
    assert valid.valid
    assert valid.status == CHECK_IN_STATUS_VALID

    unknown = validate_ticket_for_check_in(
        db_session,
        actor_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload="missing-ticket",
    )
    assert not unknown.valid
    assert unknown.status == CHECK_IN_STATUS_NOT_FOUND


def test_transferred_ticket_can_still_be_checked_in(db_session: Session) -> None:
    order, _, _, buyer, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    recipient = User(email="recipient-4@example.com", full_name="Recipient")
    db_session.add(recipient)
    db_session.commit()
    db_session.refresh(recipient)

    transferred = transfer_ticket_to_user(
        db_session,
        ticket_id=ticket.id,
        from_user_id=buyer.id,
        to_user_id=recipient.id,
    )
    assert transferred.owner_user_id == recipient.id

    scanned = check_in_ticket_for_event(
        db_session,
        scanner_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload=ticket.qr_payload,
        ticket_code=None,
    )
    assert scanned.status == TicketStatus.CHECKED_IN


def test_ticket_for_different_event_is_rejected(db_session: Session) -> None:
    order_1, _, _, _, event_1 = _seed_order(db_session, user_email="a@example.com", quantity=1)
    order_2, _, _, _, event_2 = _seed_order(db_session, user_email="b@example.com", quantity=1)
    ticket_1 = issue_tickets_for_completed_order(db_session, order_1)[0]
    issue_tickets_for_completed_order(db_session, order_2)

    with pytest.raises(TicketCrossEventError):
        check_in_ticket_for_event(
            db_session,
            scanner_user_id=event_2.organizer.user_id,
            event_id=event_2.id,
            qr_payload=ticket_1.qr_payload,
            ticket_code=None,
        )

    assert event_1.id != event_2.id

    wrong_event = validate_ticket_for_check_in(
        db_session,
        actor_user_id=event_2.organizer.user_id,
        event_id=event_2.id,
        qr_payload=ticket_1.qr_payload,
    )
    assert not wrong_event.valid
    assert wrong_event.status == CHECK_IN_STATUS_WRONG_EVENT


def test_voided_ticket_and_unknown_payload_are_rejected(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    ticket.status = TicketStatus.VOIDED
    db_session.commit()

    with pytest.raises(TicketCheckInConflictError):
        check_in_ticket_for_event(
            db_session,
            scanner_user_id=event.organizer.user_id,
            event_id=event.id,
            qr_payload=ticket.qr_payload,
            ticket_code=None,
        )

    with pytest.raises(TicketNotFoundError):
        check_in_ticket_for_event(
            db_session,
            scanner_user_id=event.organizer.user_id,
            event_id=event.id,
            qr_payload="unknown-payload",
            ticket_code=None,
        )


def test_refunded_and_cancelled_event_tickets_are_not_admittable(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    order.refund_status = "refunded"
    db_session.commit()

    refunded = validate_ticket_for_check_in(
        db_session,
        actor_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload=ticket.qr_payload,
    )
    assert not refunded.valid
    assert refunded.status == CHECK_IN_STATUS_ORDER_NOT_ADMITTABLE

    order_2, _, _, _, event_2 = _seed_order(db_session, user_email="cancelled-event@example.com", quantity=1)
    ticket_2 = issue_tickets_for_completed_order(db_session, order_2)[0]
    event_2.status = EventStatus.CANCELLED
    db_session.commit()

    cancelled = validate_ticket_for_check_in(
        db_session,
        actor_user_id=event_2.organizer.user_id,
        event_id=event_2.id,
        qr_payload=ticket_2.qr_payload,
    )
    assert not cancelled.valid
    assert cancelled.status == CHECK_IN_STATUS_CANCELED_EVENT


def test_manual_checkin_and_summary_are_ticket_level(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=3)
    tickets = issue_tickets_for_completed_order(db_session, order)
    scanner_id = event.organizer.user_id

    first = check_in_ticket(
        db_session,
        scanner_user_id=scanner_id,
        event_id=event.id,
        ticket_code=tickets[0].ticket_code,
        method=CHECK_IN_METHOD_MANUAL,
    )
    assert first.valid
    assert first.ticket is not None
    assert first.ticket.check_in_method == CHECK_IN_METHOD_MANUAL

    duplicate = check_in_ticket(
        db_session,
        scanner_user_id=scanner_id,
        event_id=event.id,
        ticket_code=tickets[0].ticket_code,
        method=CHECK_IN_METHOD_MANUAL,
    )
    assert not duplicate.valid
    assert duplicate.status == CHECK_IN_STATUS_ALREADY_CHECKED_IN

    summary = get_event_check_in_summary(db_session, actor_user_id=scanner_id, event_id=event.id)
    assert summary.total_admittable_tickets == 3
    assert summary.checked_in_tickets == 1
    assert summary.remaining_tickets == 2


def test_concurrent_duplicate_scan_only_one_succeeds() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL must be configured for concurrent duplicate scan test.")

    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    with SessionLocal() as session:
        order, _, _, _, event = _seed_order(session, quantity=1)
        ticket = issue_tickets_for_completed_order(session, order)[0]
        scanner_user_id = event.organizer.user_id
        event_id = event.id
        qr_payload = ticket.qr_payload

    def _attempt() -> bool:
        with SessionLocal() as local_session:
            try:
                check_in_ticket_for_event(
                    local_session,
                    scanner_user_id=scanner_user_id,
                    event_id=event_id,
                    qr_payload=qr_payload,
                    ticket_code=None,
                )
                local_session.commit()
                return True
            except TicketCheckInConflictError:
                local_session.rollback()
                return False
            except OperationalError:
                local_session.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _attempt(), [1, 2]))

    assert results.count(True) == 1
    assert results.count(False) == 1


def test_organizer_can_void_ticket_and_audit_fields_are_set(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    voided = void_ticket(
        db_session,
        ticket_id=ticket.id,
        actor_user_id=event.organizer.user_id,
        reason="fraud prevention",
    )

    assert voided.status == TicketStatus.VOIDED
    assert voided.voided_at is not None
    assert voided.voided_by_user_id == event.organizer.user_id
    assert voided.void_reason == "fraud prevention"
    assert voided.owner_user_id == order.user_id
    assert voided.purchaser_user_id == order.user_id
    assert len(list_tickets_for_order_owner(db_session, order_id=order.id, user_id=order.user_id)) == 1


def test_unrelated_user_cannot_void_ticket(db_session: Session) -> None:
    order, _, _, _, _ = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    outsider = User(email="void-outsider@example.com", full_name="Outsider")
    db_session.add(outsider)
    db_session.commit()
    db_session.refresh(outsider)

    with pytest.raises(TicketAuthorizationError):
        void_ticket(
            db_session,
            ticket_id=ticket.id,
            actor_user_id=outsider.id,
            reason="not allowed",
        )


def test_checked_in_and_already_voided_tickets_cannot_be_voided(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=2)
    tickets = issue_tickets_for_completed_order(db_session, order)

    check_in_ticket_for_event(
        db_session,
        scanner_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload=tickets[0].qr_payload,
        ticket_code=None,
    )
    with pytest.raises(TicketVoidError):
        void_ticket(
            db_session,
            ticket_id=tickets[0].id,
            actor_user_id=event.organizer.user_id,
        )

    void_ticket(
        db_session,
        ticket_id=tickets[1].id,
        actor_user_id=event.organizer.user_id,
    )
    with pytest.raises(TicketVoidError):
        void_ticket(
            db_session,
            ticket_id=tickets[1].id,
            actor_user_id=event.organizer.user_id,
        )


def test_voided_ticket_cannot_be_transferred_or_checked_in(db_session: Session) -> None:
    order, _, _, buyer, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    recipient = User(email="void-recipient@example.com", full_name="Recipient")
    db_session.add(recipient)
    db_session.commit()
    db_session.refresh(recipient)

    void_ticket(
        db_session,
        ticket_id=ticket.id,
        actor_user_id=event.organizer.user_id,
        reason="duplicate",
    )

    with pytest.raises(TicketTransferError):
        transfer_ticket_to_user(
            db_session,
            ticket_id=ticket.id,
            from_user_id=buyer.id,
            to_user_id=recipient.id,
        )

    with pytest.raises(TicketCheckInConflictError):
        check_in_ticket_for_event(
            db_session,
            scanner_user_id=event.organizer.user_id,
            event_id=event.id,
            qr_payload=ticket.qr_payload,
            ticket_code=None,
        )


def test_void_permissions_are_event_scoped_and_organizer_only(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, user_email="void-scope@example.com", quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    staff_user = User(email="void-staff@example.com", full_name="Staff")
    db_session.add(staff_user)
    db_session.flush()
    db_session.add(
        EventStaff(
            event_id=event.id,
            user_id=staff_user.id,
            role=EventStaffRole.MANAGER,
            is_active=True,
            invited_by_user_id=event.organizer.user_id,
        )
    )
    db_session.commit()

    assert can_void_event_ticket(db_session, user_id=event.organizer.user_id, event_id=event.id)
    assert not can_void_event_ticket(db_session, user_id=staff_user.id, event_id=event.id)

    with pytest.raises(TicketAuthorizationError):
        void_ticket(
            db_session,
            ticket_id=ticket.id,
            actor_user_id=staff_user.id,
        )


def test_ticket_lifecycle_notification_hooks_are_called(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []

    monkeypatch.setattr(
        "app.services.tickets.notify_ticket_issued",
        lambda ticket: calls.append(("issued", ticket.id)),
    )
    monkeypatch.setattr(
        "app.services.tickets.notify_ticket_transferred",
        lambda ticket, **_: calls.append(("transferred", ticket.id)),
    )
    monkeypatch.setattr(
        "app.services.tickets.notify_ticket_voided",
        lambda ticket, **_: calls.append(("voided", ticket.id)),
    )

    order, _, _, buyer, event = _seed_order(db_session, user_email="hooks@example.com", quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    recipient = User(email="hooks-recipient@example.com", full_name="Recipient")
    db_session.add(recipient)
    db_session.commit()
    db_session.refresh(recipient)

    transfer_ticket_to_user(
        db_session,
        ticket_id=ticket.id,
        from_user_id=buyer.id,
        to_user_id=recipient.id,
    )
    void_ticket(
        db_session,
        ticket_id=ticket.id,
        actor_user_id=event.organizer.user_id,
        reason="ops",
    )

    assert [name for name, _ in calls] == ["issued", "transferred", "voided"]


def test_ticket_qr_payload_and_png_generation_are_stable(db_session: Session) -> None:
    pytest.importorskip("qrcode")
    order, _, _, _, _ = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    payload = build_ticket_qr_payload(ticket)
    assert payload.startswith(QR_PAYLOAD_PREFIX)
    assert payload.endswith(ticket.qr_token or ticket.qr_payload)
    assert payload != str(ticket.id)

    png = generate_qr_png_bytes(payload)
    assert png
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_checkin_accepts_ticket_url_payload_and_reuses_phase17_validation(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    url_payload = build_ticket_qr_payload(ticket)
    valid = validate_ticket_for_check_in(
        db_session,
        actor_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload=url_payload,
    )
    assert valid.valid is True

    ticket.status = TicketStatus.VOIDED
    db_session.commit()

    rejected = validate_ticket_for_check_in(
        db_session,
        actor_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload=url_payload,
    )
    assert rejected.valid is False
    assert rejected.status == "refunded_or_invalidated"


def test_checkin_attempts_are_audited_for_validate_and_duplicate(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    validated = validate_ticket_for_check_in(
        db_session,
        actor_user_id=event.organizer.user_id,
        event_id=event.id,
        ticket_code=ticket.ticket_code,
    )
    assert validated.valid is True

    admitted = check_in_ticket(
        db_session,
        scanner_user_id=event.organizer.user_id,
        event_id=event.id,
        ticket_code=ticket.ticket_code,
        method=CHECK_IN_METHOD_MANUAL,
    )
    assert admitted.valid is True

    duplicate = check_in_ticket(
        db_session,
        scanner_user_id=event.organizer.user_id,
        event_id=event.id,
        ticket_code=ticket.ticket_code,
        method=CHECK_IN_METHOD_MANUAL,
    )
    assert duplicate.valid is False
    assert duplicate.status == CHECK_IN_STATUS_ALREADY_CHECKED_IN

    rows = list_recent_check_in_attempts(
        db_session,
        actor_user_id=event.organizer.user_id,
        event_id=event.id,
        limit=10,
    )
    assert len(rows) >= 3
    assert rows[0].result_code in {CHECK_IN_STATUS_ALREADY_CHECKED_IN, CHECK_IN_STATUS_VALID}


def test_manual_override_requires_manager_and_notes(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    support_user = User(email="support-override@example.com", full_name="Support")
    manager_user = User(email="manager-override@example.com", full_name="Manager")
    db_session.add_all([support_user, manager_user])
    db_session.flush()
    db_session.add_all(
        [
            EventStaff(
                event_id=event.id,
                user_id=support_user.id,
                role=EventStaffRole.SUPPORT,
                is_active=True,
                invited_by_user_id=event.organizer.user_id,
            ),
            EventStaff(
                event_id=event.id,
                user_id=manager_user.id,
                role=EventStaffRole.MANAGER,
                is_active=True,
                invited_by_user_id=event.organizer.user_id,
            ),
        ]
    )
    db_session.commit()

    with pytest.raises(TicketAuthorizationError):
        override_ticket_check_in(
            db_session,
            actor_user_id=support_user.id,
            event_id=event.id,
            ticket_code=ticket.ticket_code,
            admit=True,
            notes="allow",
        )

    with pytest.raises(TicketCheckInConflictError):
        override_ticket_check_in(
            db_session,
            actor_user_id=manager_user.id,
            event_id=event.id,
            ticket_code=ticket.ticket_code,
            admit=True,
            notes="   ",
        )

    result = override_ticket_check_in(
        db_session,
        actor_user_id=manager_user.id,
        event_id=event.id,
        ticket_code=ticket.ticket_code,
        admit=True,
        notes="badge mismatch verified at gate",
    )
    assert result.valid is True
    assert result.status == CHECK_IN_STATUS_MANUAL_OVERRIDE_ADMITTED


def test_ticket_qr_endpoint_requires_ticket_ownership(db_session: Session) -> None:
    pytest.importorskip("qrcode")
    order, _, _, buyer, _ = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    owner_view = get_ticket_qr_by_ticket_id(ticket.id, db=db_session, user_id=buyer.id)
    assert owner_view.ticket_public_token == (ticket.qr_token or ticket.qr_payload)
    assert owner_view.qr_data_uri.startswith("data:image/png;base64,")

    outsider = User(email="qr-outsider@example.com", full_name="Outsider")
    db_session.add(outsider)
    db_session.commit()
    db_session.refresh(outsider)

    with pytest.raises(HTTPException) as exc:
        get_ticket_qr_by_ticket_id(ticket.id, db=db_session, user_id=outsider.id)
    assert exc.value.status_code == 404

def test_wallet_list_only_returns_current_owner_tickets(db_session: Session) -> None:
    order, _, _, buyer, _ = _seed_order(db_session, quantity=2)
    issued = issue_tickets_for_completed_order(db_session, order)
    recipient = User(email="wallet-recipient@example.com", full_name="Recipient")
    db_session.add(recipient)
    db_session.commit()
    transfer_ticket_to_user(db_session, ticket_id=issued[0].id, from_user_id=buyer.id, to_user_id=recipient.id)

    buyer_wallet = list_wallet_tickets(db_session, user_id=buyer.id)
    recipient_wallet = list_wallet_tickets(db_session, user_id=recipient.id)

    assert [v.ticket.id for v in buyer_wallet] == [issued[1].id]
    assert [v.ticket.id for v in recipient_wallet] == [issued[0].id]


def test_wallet_list_orders_upcoming_before_past(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    order_upcoming_far, _, _, buyer, event_upcoming_far = _seed_order(db_session, user_email="wallet-sort@example.com", quantity=1)
    issue_tickets_for_completed_order(db_session, order_upcoming_far)

    order_past_recent, _, _, _, event_past_recent = _seed_order(db_session, user_email="wallet-sort-2@example.com", quantity=1)
    order_past_recent.user_id = buyer.id
    issue_tickets_for_completed_order(db_session, order_past_recent)

    order_upcoming_near, _, _, _, event_upcoming_near = _seed_order(db_session, user_email="wallet-sort-3@example.com", quantity=1)
    order_upcoming_near.user_id = buyer.id
    issue_tickets_for_completed_order(db_session, order_upcoming_near)

    event_upcoming_far.start_at = now + timedelta(days=10)
    event_upcoming_far.end_at = now + timedelta(days=10, hours=2)
    event_upcoming_near.start_at = now + timedelta(days=1)
    event_upcoming_near.end_at = now + timedelta(days=1, hours=2)
    event_past_recent.start_at = now - timedelta(days=1)
    event_past_recent.end_at = now - timedelta(days=1, hours=-2)
    db_session.commit()

    wallet = list_wallet_tickets(db_session, user_id=buyer.id)
    assert len(wallet) == 3
    assert wallet[0].ticket.event_id == event_upcoming_near.id
    assert wallet[1].ticket.event_id == event_upcoming_far.id
    assert wallet[2].ticket.event_id == event_past_recent.id


def test_wallet_ticket_detail_owned_vs_non_owned(db_session: Session) -> None:
    order, _, _, buyer, _ = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    owner_detail = get_wallet_ticket(db_session, user_id=buyer.id, ticket_id=ticket.id)
    assert owner_detail is not None
    assert owner_detail.ticket.id == ticket.id
    assert owner_detail.ticket.order is not None
    assert owner_detail.ticket.order.reference_code.startswith("ORD-")

    other = User(email="wallet-other@example.com", full_name="Other")
    db_session.add(other)
    db_session.commit()
    assert get_wallet_ticket(db_session, user_id=other.id, ticket_id=ticket.id) is None


def test_wallet_status_used_and_invalid(db_session: Session) -> None:
    order_used, _, _, buyer, event = _seed_order(db_session, user_email="wallet-used@example.com", quantity=1)
    used_ticket = issue_tickets_for_completed_order(db_session, order_used)[0]
    check_in_ticket_for_event(
        db_session,
        scanner_user_id=event.organizer.user_id,
        event_id=event.id,
        qr_payload=used_ticket.qr_payload,
        ticket_code=None,
    )

    order_invalid, _, _, _, _ = _seed_order(db_session, user_email="wallet-invalid@example.com", quantity=1)
    order_invalid.user_id = buyer.id
    invalid_ticket = issue_tickets_for_completed_order(db_session, order_invalid)[0]
    invalid_ticket.status = TicketStatus.VOIDED
    db_session.commit()

    wallet = {v.ticket.id: v for v in list_wallet_tickets(db_session, user_id=buyer.id)}
    assert wallet[used_ticket.id].display_status == "used"
    assert wallet[invalid_ticket.id].display_status == "invalid"


def test_wallet_transferred_acceptance_behavior(db_session: Session) -> None:
    order, _, _, buyer, _ = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    new_owner = User(email="wallet-new-owner@example.com", full_name="New Owner")
    db_session.add(new_owner)
    db_session.commit()

    transfer_ticket_to_user(db_session, ticket_id=ticket.id, from_user_id=buyer.id, to_user_id=new_owner.id)

    assert list_wallet_tickets(db_session, user_id=buyer.id) == []
    recipient_wallet = list_wallet_tickets(db_session, user_id=new_owner.id)
    assert len(recipient_wallet) == 1
    assert recipient_wallet[0].ticket.id == ticket.id


def test_wallet_entry_payload_exists_and_stable(db_session: Session) -> None:
    order, _, _, buyer, _ = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    first = get_wallet_ticket(db_session, user_id=buyer.id, ticket_id=ticket.id)
    second = get_wallet_ticket(db_session, user_id=buyer.id, ticket_id=ticket.id)
    assert first is not None and second is not None
    assert first.ticket.qr_payload
    assert first.ticket.qr_payload == second.ticket.qr_payload
    assert first.ticket.ticket_code == second.ticket.ticket_code


def test_wallet_uses_issued_tickets_not_only_orders(db_session: Session) -> None:
    order, _, _, buyer, _ = _seed_order(db_session, quantity=2)
    assert list_wallet_tickets(db_session, user_id=buyer.id) == []
    issue_tickets_for_completed_order(db_session, order)
    assert len(list_wallet_tickets(db_session, user_id=buyer.id)) == 2

def _add_checkin_staff(db: Session, *, event: Event, owner_user_id: int, email: str = "scanner@example.com") -> User:
    scanner = User(email=email, full_name="Scanner")
    db.add(scanner)
    db.flush()
    db.add(
        EventStaff(
            event_id=event.id,
            user_id=scanner.id,
            role=EventStaffRole.CHECKIN,
            invited_by_user_id=owner_user_id,
        )
    )
    db.commit()
    db.refresh(scanner)
    return scanner


def test_scan_valid_ticket(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    scanner = _add_checkin_staff(db_session, event=event, owner_user_id=event.organizer.user_id, email="scanner-valid@example.com")

    result = scan_ticket(db_session, payload=generate_ticket_qr_payload(ticket), user_id=scanner.id)

    assert result.status == "SUCCESS"
    assert result.ticket_id == ticket.id
    db_session.refresh(ticket)
    assert ticket.check_in_status == CheckInStatus.CHECKED_IN
    assert ticket.checked_in_by_user_id == scanner.id


def test_scan_already_used_ticket(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    scanner = _add_checkin_staff(db_session, event=event, owner_user_id=event.organizer.user_id, email="scanner-used@example.com")

    first = scan_ticket(db_session, payload=generate_ticket_qr_payload(ticket), user_id=scanner.id)
    second = scan_ticket(db_session, payload=generate_ticket_qr_payload(ticket), user_id=scanner.id)

    assert first.status == "SUCCESS"
    assert second.status == "ALREADY_USED"


def test_scan_invalid_signature(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    scanner = _add_checkin_staff(db_session, event=event, owner_user_id=event.organizer.user_id, email="scanner-invalid@example.com")

    payload = generate_ticket_qr_payload(ticket)
    payload["hash"] = "bad-signature"

    result = scan_ticket(db_session, payload=payload, user_id=scanner.id)

    assert result.status == "INVALID"


def test_scan_wrong_event(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    scanner = _add_checkin_staff(db_session, event=event, owner_user_id=event.organizer.user_id, email="scanner-wrong-event@example.com")

    payload = generate_signed_ticket_qr_payload(ticket_id=ticket.id, event_id=ticket.event_id + 999)

    result = scan_ticket(db_session, payload=payload, user_id=scanner.id)

    assert result.status == "WRONG_EVENT"


def test_only_authorized_can_scan(db_session: Session) -> None:
    order, _, _, _, _ = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    outsider = User(email="outsider-scanner@example.com", full_name="Outsider Scanner")
    db_session.add(outsider)
    db_session.commit()
    db_session.refresh(outsider)

    result = scan_ticket(db_session, payload=generate_ticket_qr_payload(ticket), user_id=outsider.id)

    assert result.status == "INVALID"
    assert result.message == "Not authorized to scan this event."


def test_scan_logs_created(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    scanner = _add_checkin_staff(db_session, event=event, owner_user_id=event.organizer.user_id, email="scanner-logs@example.com")

    scan_ticket(db_session, payload=generate_ticket_qr_payload(ticket), user_id=scanner.id)
    scan_ticket(db_session, payload=generate_ticket_qr_payload(ticket), user_id=scanner.id)

    logs = db_session.execute(select(TicketScanLog).where(TicketScanLog.ticket_id == ticket.id)).scalars().all()
    assert len(logs) == 2
    assert {row.status.value for row in logs} == {"SUCCESS", "ALREADY_USED"}


def test_ticket_issuance_populates_qr_fields_and_unique_tokens(db_session: Session) -> None:
    order, _, _, _, _ = _seed_order(db_session, quantity=3)
    tickets = issue_tickets_for_completed_order(db_session, order)

    assert all(ticket.qr_token for ticket in tickets)
    assert all(ticket.qr_generated_at for ticket in tickets)
    assert all(ticket.display_code and ticket.display_code.startswith("TKT-") for ticket in tickets)
    assert len({ticket.qr_token for ticket in tickets}) == len(tickets)


def test_qr_token_is_unique_across_orders(db_session: Session) -> None:
    order_a, _, _, _, _ = _seed_order(db_session, user_email="uniq-a@example.com", quantity=2)
    order_b, _, _, _, _ = _seed_order(db_session, user_email="uniq-b@example.com", quantity=2)
    issued = issue_tickets_for_completed_order(db_session, order_a) + issue_tickets_for_completed_order(db_session, order_b)
    assert len({ticket.qr_token for ticket in issued}) == len(issued)


def test_legacy_ticket_without_qr_token_can_be_polished(db_session: Session) -> None:
    order, _, _, buyer, _ = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    ticket.qr_token = None
    ticket.qr_generated_at = None
    ticket.display_code = None
    db_session.flush()

    ensure_ticket_qr(db_session, ticket)
    db_session.flush()

    detail = get_ticket_detail(ticket.id, db=db_session, user_id=buyer.id)
    assert detail.qr_payload.startswith(QR_PAYLOAD_PREFIX)
    assert detail.display_code and detail.display_code.startswith("TKT-")


def test_ticket_detail_response_shape_and_auth(db_session: Session) -> None:
    order, _, _, buyer, _ = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    detail = get_ticket_detail(ticket.id, db=db_session, user_id=buyer.id)
    assert detail.ticket_id == ticket.id
    assert detail.ticket_public_id == ticket.display_code
    assert detail.event_title == ticket.event.title
    assert detail.ticket_tier_name == ticket.ticket_tier.name
    assert detail.ticket_status == ticket.status.value
    assert detail.qr_payload == f"{QR_PAYLOAD_PREFIX}{ticket.qr_token}"

    outsider = User(email="ticket-detail-outsider@example.com", full_name="Outsider")
    db_session.add(outsider)
    db_session.commit()
    db_session.refresh(outsider)

    with pytest.raises(HTTPException) as exc:
        get_ticket_detail(ticket.id, db=db_session, user_id=outsider.id)
    assert exc.value.status_code == 404
