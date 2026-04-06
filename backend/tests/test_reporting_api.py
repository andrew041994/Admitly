from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.db.base import Base
from app.models import Event, OrganizerProfile, Order, OrderItem, TicketHold, TicketTier, Ticket, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus, TicketStatus
from app.services.reporting import (
    get_event_checkin_summary,
    get_event_reporting_summary,
    get_event_tier_summary,
    list_event_checkins,
    list_event_orders_for_organizer,
    list_event_tickets_for_organizer,
    validate_event_reporting_access,
    EventReportingAuthorizationError,
)
from app.services.tickets import issue_tickets_for_completed_order, transfer_ticket_to_user, void_ticket, check_in_ticket_for_event


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


def _seed_reporting_data(db: Session):
    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)

    organizer_user = User(email="organizer@example.com", full_name="Organizer")
    unrelated_user = User(email="viewer@example.com", full_name="Viewer")
    admin_user = User(email="admin@example.com", full_name="Admin", is_admin=True)
    buyer = User(email="buyer@example.com", full_name="Buyer")
    recipient = User(email="recipient@example.com", full_name="Recipient")
    scanner = User(email="scanner@example.com", full_name="Scanner")
    db.add_all([organizer_user, unrelated_user, admin_user, buyer, recipient, scanner])
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
        title="Reporting Event",
        slug="reporting-event",
        start_at=now + timedelta(days=1),
        end_at=now + timedelta(days=1, hours=4),
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        approval_status=EventApprovalStatus.APPROVED,
        timezone="America/Guyana",
        is_location_pinned=False,
    )
    other_event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title="Other Event",
        slug="reporting-other-event",
        start_at=now + timedelta(days=2),
        end_at=now + timedelta(days=2, hours=4),
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        approval_status=EventApprovalStatus.APPROVED,
        timezone="America/Guyana",
        is_location_pinned=False,
    )
    db.add_all([event, other_event])
    db.flush()

    tier_a = TicketTier(
        event_id=event.id,
        name="General",
        tier_code="GEN",
        price_amount=Decimal("100.00"),
        currency="GYD",
        quantity_total=20,
        quantity_sold=0,
        quantity_held=0,
        min_per_order=1,
        max_per_order=10,
        is_active=True,
        sort_order=0,
    )
    tier_b = TicketTier(
        event_id=event.id,
        name="VIP",
        tier_code="VIP",
        price_amount=Decimal("200.00"),
        currency="GYD",
        quantity_total=5,
        quantity_sold=0,
        quantity_held=0,
        min_per_order=1,
        max_per_order=10,
        is_active=True,
        sort_order=1,
    )
    other_tier = TicketTier(
        event_id=other_event.id,
        name="Other",
        tier_code="OTH",
        price_amount=Decimal("50.00"),
        currency="GYD",
        quantity_total=10,
        quantity_sold=0,
        quantity_held=0,
        min_per_order=1,
        max_per_order=10,
        is_active=True,
        sort_order=0,
    )
    db.add_all([tier_a, tier_b, other_tier])
    db.flush()

    completed_order = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        total_amount=Decimal("400.00"),
        currency="GYD",
        payment_verification_status="verified",
    )
    refunded_order = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        total_amount=Decimal("100.00"),
        currency="GYD",
        payment_verification_status="verified",
        refund_status="refunded",
        refunded_by_user_id=organizer_user.id,
        refunded_at=now,
    )
    pending_order = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.PENDING,
        total_amount=Decimal("200.00"),
        currency="GYD",
    )
    cancelled_order = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.CANCELLED,
        total_amount=Decimal("300.00"),
        currency="GYD",
        cancelled_by_user_id=organizer_user.id,
        cancelled_at=now,
    )
    expired_order = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.EXPIRED,
        total_amount=Decimal("300.00"),
        currency="GYD",
    )
    other_event_order = Order(
        user_id=buyer.id,
        event_id=other_event.id,
        status=OrderStatus.COMPLETED,
        total_amount=Decimal("50.00"),
        currency="GYD",
        payment_verification_status="verified",
    )
    db.add_all([completed_order, refunded_order, pending_order, cancelled_order, expired_order, other_event_order])
    db.flush()

    db.add_all(
        [
            OrderItem(order_id=completed_order.id, ticket_tier_id=tier_a.id, quantity=2, unit_price=Decimal("100.00")),
            OrderItem(order_id=completed_order.id, ticket_tier_id=tier_b.id, quantity=1, unit_price=Decimal("200.00")),
            OrderItem(order_id=refunded_order.id, ticket_tier_id=tier_a.id, quantity=1, unit_price=Decimal("100.00")),
            OrderItem(order_id=pending_order.id, ticket_tier_id=tier_a.id, quantity=2, unit_price=Decimal("100.00")),
            OrderItem(order_id=cancelled_order.id, ticket_tier_id=tier_b.id, quantity=1, unit_price=Decimal("300.00")),
            OrderItem(order_id=other_event_order.id, ticket_tier_id=other_tier.id, quantity=1, unit_price=Decimal("50.00")),
        ]
    )
    db.flush()

    db.add(
        TicketHold(
            event_id=event.id,
            ticket_tier_id=tier_b.id,
            user_id=buyer.id,
            quantity=2,
            expires_at=now + timedelta(days=30),
            order_id=None,
        )
    )
    db.flush()

    completed_tickets = issue_tickets_for_completed_order(db, completed_order)
    refunded_tickets = issue_tickets_for_completed_order(db, refunded_order)

    transfer_ticket_to_user(db, ticket_id=completed_tickets[0].id, from_user_id=buyer.id, to_user_id=recipient.id)
    check_in_ticket_for_event(
        db,
        scanner_user_id=organizer_user.id,
        event_id=event.id,
        qr_payload=completed_tickets[0].qr_payload,
        ticket_code=None,
    )
    void_ticket(db, ticket_id=completed_tickets[1].id, actor_user_id=organizer_user.id, reason="test")

    refunded_tickets[0].checked_in_by_user_id = scanner.id
    refunded_tickets[0].status = TicketStatus.CHECKED_IN
    refunded_tickets[0].checked_in_at = now
    db.commit()

    return {
        "organizer_user": organizer_user,
        "unrelated_user": unrelated_user,
        "admin_user": admin_user,
        "event": event,
    }


def test_organizer_reporting_routes_registered() -> None:
    route_paths = {route.path for route in app.routes}
    assert "/organizer/events/{event_id}/summary" in route_paths
    assert "/organizer/events/{event_id}/tiers" in route_paths
    assert "/organizer/events/{event_id}/orders" in route_paths
    assert "/organizer/events/{event_id}/tickets" in route_paths
    assert "/organizer/events/{event_id}/checkins/summary" in route_paths
    assert "/organizer/events/{event_id}/checkins" in route_paths


def test_reporting_authorization_for_organizer_admin_and_unrelated(db_session: Session) -> None:
    data = _seed_reporting_data(db_session)
    event_id = data["event"].id

    assert validate_event_reporting_access(db_session, user_id=data["organizer_user"].id, event_id=event_id).id == event_id
    assert validate_event_reporting_access(db_session, user_id=data["admin_user"].id, event_id=event_id).id == event_id
    with pytest.raises(EventReportingAuthorizationError):
        validate_event_reporting_access(db_session, user_id=data["unrelated_user"].id, event_id=event_id)


def test_event_summary_reflects_revenue_and_ticket_counts(db_session: Session) -> None:
    data = _seed_reporting_data(db_session)
    summary = get_event_reporting_summary(db_session, event_id=data["event"].id)

    assert summary.gross_revenue == Decimal("500.00")
    assert summary.refunded_amount == Decimal("100.00")
    assert summary.net_revenue == Decimal("400.00")
    assert summary.completed_order_count == 2
    assert summary.pending_order_count == 1
    assert summary.cancelled_order_count == 1
    assert summary.refunded_order_count == 1
    assert summary.tickets_sold_count == 4
    assert summary.tickets_issued_count == 4
    assert summary.tickets_checked_in_count == 2
    assert summary.tickets_voided_count == 1
    assert summary.tickets_remaining_count == 19


def test_tier_summary_reflects_sold_holds_checkins_and_remaining(db_session: Session) -> None:
    data = _seed_reporting_data(db_session)
    tiers = {item.name: item for item in get_event_tier_summary(db_session, event_id=data["event"].id)}

    assert tiers["General"].sold_count == 3
    assert tiers["General"].checked_in_count == 2
    assert tiers["General"].voided_count == 1
    assert tiers["General"].active_hold_count == 0
    assert tiers["General"].remaining_count == 17

    assert tiers["VIP"].sold_count == 1
    assert tiers["VIP"].active_hold_count == 2
    assert tiers["VIP"].remaining_count == 2


def test_order_listing_is_event_scoped_and_filterable(db_session: Session) -> None:
    data = _seed_reporting_data(db_session)
    event_id = data["event"].id

    orders = list_event_orders_for_organizer(db_session, event_id=event_id)
    assert len(orders) == 5
    assert all(order.status in {"completed", "pending", "cancelled", "expired"} for order in orders)

    completed_only = list_event_orders_for_organizer(db_session, event_id=event_id, status=OrderStatus.COMPLETED)
    assert len(completed_only) == 2

    refunded_only = list_event_orders_for_organizer(db_session, event_id=event_id, refund_status="refunded")
    assert len(refunded_only) == 1


def test_ticket_and_checkin_reporting_show_operational_state(db_session: Session) -> None:
    data = _seed_reporting_data(db_session)
    event_id = data["event"].id

    tickets = list_event_tickets_for_organizer(db_session, event_id=event_id)
    assert len(tickets) == 4
    assert any(t.transfer_count == 1 for t in tickets)
    assert any(t.status == "voided" for t in tickets)
    assert any(t.status == "checked_in" and t.checked_in_by_user_id is not None for t in tickets)

    summary = get_event_checkin_summary(db_session, event_id=event_id)
    assert summary.total_checked_in == 2

    checkins = list_event_checkins(db_session, event_id=event_id)
    assert len(checkins) == 2
    assert all(row.checked_in_by_user_id is not None for row in checkins)


def test_reporting_service_is_read_only(db_session: Session) -> None:
    data = _seed_reporting_data(db_session)
    event_id = data["event"].id

    before = db_session.execute(select(Ticket.status).where(Ticket.event_id == event_id)).scalars().all()

    get_event_reporting_summary(db_session, event_id=event_id)
    get_event_tier_summary(db_session, event_id=event_id)
    list_event_orders_for_organizer(db_session, event_id=event_id)
    list_event_tickets_for_organizer(db_session, event_id=event_id)
    get_event_checkin_summary(db_session, event_id=event_id)
    list_event_checkins(db_session, event_id=event_id)

    after = db_session.execute(select(Ticket.status).where(Ticket.event_id == event_id)).scalars().all()
    assert before == after
