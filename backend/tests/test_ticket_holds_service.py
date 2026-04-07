from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Event, OrganizerProfile, Order, OrderItem, TicketHold, TicketTier, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus
from app.services.ticket_holds import (
    InsufficientAvailabilityError,
    TicketHoldWindowClosedError,
    calculate_ticket_hold_expiry,
    create_ticket_hold,
    get_ticket_tier_capacity_summary,
    get_ticket_type_availability,
)


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


def _seed_ticket_tier(db: Session, start_at: datetime, quantity_total: int = 100) -> TicketTier:
    user = User(email="owner@example.com", full_name="Owner")
    db.add(user)
    db.flush()

    organizer = OrganizerProfile(user_id=user.id, business_name="Biz", display_name="Biz")
    db.add(organizer)
    db.flush()

    venue = Venue(organizer_id=organizer.id, name="Venue")
    db.add(venue)
    db.flush()

    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title="Concert",
        slug=f"concert-{int(start_at.timestamp())}",
        start_at=start_at,
        end_at=start_at + timedelta(hours=4),
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
        tier_code="GENERAL",
        price_amount=100,
        currency="GYD",
        quantity_total=quantity_total,
        quantity_sold=0,
        quantity_held=0,
        min_per_order=1,
        max_per_order=10,
        is_active=True,
        sort_order=0,
    )
    db.add(tier)
    db.commit()
    db.refresh(tier)
    return tier


def test_hold_expiry_defaults_to_48_hours_when_event_far_away() -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    event_start = now + timedelta(days=4)

    expires = calculate_ticket_hold_expiry(event_start, now=now)

    assert expires == now.astimezone(expires.tzinfo) + timedelta(hours=48)


def test_hold_expiry_truncates_to_8_hours_before_event() -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    event_start = now + timedelta(hours=30)

    expires = calculate_ticket_hold_expiry(event_start, now=now)

    assert expires == event_start.astimezone(expires.tzinfo) - timedelta(hours=8)


def test_hold_rejected_when_event_starts_within_8_hours(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    tier = _seed_ticket_tier(db_session, start_at=now + timedelta(hours=8))

    with pytest.raises(TicketHoldWindowClosedError):
        create_ticket_hold(db_session, user_id=1, ticket_tier_id=tier.id, quantity=1, now=now)


def test_expired_holds_do_not_count_against_availability(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    tier = _seed_ticket_tier(db_session, start_at=now + timedelta(days=3), quantity_total=10)

    expired = TicketHold(
        event_id=tier.event_id,
        ticket_tier_id=tier.id,
        user_id=1,
        quantity=3,
        expires_at=now - timedelta(minutes=1),
    )
    db_session.add(expired)
    db_session.commit()

    availability = get_ticket_type_availability(db_session, ticket_tier_id=tier.id, now=now)
    assert availability == 10


def test_completed_orders_count_pending_do_not(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    tier = _seed_ticket_tier(db_session, start_at=now + timedelta(days=3), quantity_total=10)

    completed_order = Order(
        user_id=1,
        event_id=tier.event_id,
        status=OrderStatus.COMPLETED,
        total_amount=200,
        currency="GYD",
    )
    pending_order = Order(
        user_id=1,
        event_id=tier.event_id,
        status=OrderStatus.PENDING,
        total_amount=100,
        currency="GYD",
    )
    db_session.add_all([completed_order, pending_order])
    db_session.flush()

    db_session.add_all(
        [
            OrderItem(order_id=completed_order.id, ticket_tier_id=tier.id, quantity=2, unit_price=100),
            OrderItem(order_id=pending_order.id, ticket_tier_id=tier.id, quantity=1, unit_price=100),
        ]
    )
    db_session.commit()

    availability = get_ticket_type_availability(db_session, ticket_tier_id=tier.id, now=now)
    assert availability == 8


def test_expired_attached_pending_hold_does_not_reduce_availability(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    tier = _seed_ticket_tier(db_session, start_at=now + timedelta(days=3), quantity_total=10)
    pending_order = Order(user_id=1, event_id=tier.event_id, status=OrderStatus.PENDING, total_amount=100, currency="GYD")
    db_session.add(pending_order)
    db_session.flush()
    db_session.add(
        TicketHold(
            event_id=tier.event_id,
            ticket_tier_id=tier.id,
            user_id=1,
            quantity=4,
            expires_at=now - timedelta(minutes=1),
            order_id=pending_order.id,
        )
    )
    db_session.commit()

    summary = get_ticket_tier_capacity_summary(db_session, ticket_tier_id=tier.id, now=now)
    assert summary.active_hold_quantity == 0
    assert summary.available_quantity == 10


def test_hold_creation_rejects_quantity_over_availability(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    tier = _seed_ticket_tier(db_session, start_at=now + timedelta(days=3), quantity_total=2)

    with pytest.raises(InsufficientAvailabilityError):
        create_ticket_hold(db_session, user_id=1, ticket_tier_id=tier.id, quantity=3, now=now)


def test_sequential_holds_prevent_oversell(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    tier = _seed_ticket_tier(db_session, start_at=now + timedelta(days=3), quantity_total=2)

    result = create_ticket_hold(db_session, user_id=1, ticket_tier_id=tier.id, quantity=2, now=now)
    assert result.availability_remaining == 0

    with pytest.raises(InsufficientAvailabilityError):
        create_ticket_hold(db_session, user_id=1, ticket_tier_id=tier.id, quantity=1, now=now)
