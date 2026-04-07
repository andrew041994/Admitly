from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Event, EventStaff, OrganizerProfile, Order, OrderItem, Ticket, TicketTier, User, Venue
from app.models.enums import (
    EventApprovalStatus,
    EventStaffRole,
    EventStatus,
    EventVisibility,
    OrderStatus,
    TicketStatus,
)
from app.api.tickets import get_ticket_qr_by_ticket_id
from app.services.orders import complete_paid_order
from app.services.ticket_qr import build_ticket_qr_payload, generate_qr_png_bytes, get_ticket_public_url
from app.services.tickets import (
    CHECK_IN_METHOD_MANUAL,
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
    list_tickets_for_order_owner,
    list_tickets_for_user,
    transfer_ticket_to_user,
    validate_ticket_for_check_in,
    void_ticket,
)


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


def _seed_order(
    db: Session,
    *,
    user_email: str = "buyer@example.com",
    quantity: int = 3,
    status: OrderStatus = OrderStatus.COMPLETED,
    payment_verification_status: str = "verified",
) -> tuple[Order, OrderItem, TicketTier, User, Event]:
    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
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
            role=EventStaffRole.SCANNER,
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


def test_concurrent_duplicate_scan_only_one_succeeds(tmp_path: Path) -> None:
    db_path = tmp_path / "tickets-concurrency.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
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
    assert payload == get_ticket_public_url(ticket)
    assert payload.endswith(f"/t/{ticket.qr_payload}")

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


def test_ticket_qr_endpoint_requires_ticket_ownership(db_session: Session) -> None:
    pytest.importorskip("qrcode")
    order, _, _, buyer, _ = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    owner_view = get_ticket_qr_by_ticket_id(ticket.id, db=db_session, user_id=buyer.id)
    assert owner_view.ticket_public_token == ticket.qr_payload
    assert owner_view.qr_data_uri.startswith("data:image/png;base64,")

    outsider = User(email="qr-outsider@example.com", full_name="Outsider")
    db_session.add(outsider)
    db_session.commit()
    db_session.refresh(outsider)

    with pytest.raises(HTTPException) as exc:
        get_ticket_qr_by_ticket_id(ticket.id, db=db_session, user_id=outsider.id)
    assert exc.value.status_code == 404
