from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Event, OrganizerProfile, Order, TicketHold, TicketTier, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus
from app.services.orders import (
    EmptyHoldSelectionError,
    HoldAlreadyAttachedError,
    HoldEventMismatchError,
    HoldExpiredError,
    HoldOwnershipError,
    OrderAuthorizationError,
    OrderFlowError,
    create_comp_order_for_user,
    create_pending_order_from_holds,
)
from app.lib.order_references import format_order_reference
from app.services.ticket_holds import get_ticket_type_availability



def _seed_event_with_tiers(
    db: Session,
    *,
    owner_email: str,
    start_at: datetime,
    tier_prices: list[Decimal],
    quantity_total: int = 100,
) -> tuple[User, Event, list[TicketTier]]:
    user = User(email=owner_email, full_name="Owner")
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
        slug=f"concert-{owner_email}-{int(start_at.timestamp())}",
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

    tiers: list[TicketTier] = []
    for idx, price in enumerate(tier_prices):
        tier = TicketTier(
            event_id=event.id,
            name=f"Tier {idx + 1}",
            tier_code=f"TIER{idx + 1}",
            price_amount=price,
            currency="GYD",
            quantity_total=quantity_total,
            quantity_sold=0,
            quantity_held=0,
            min_per_order=1,
            max_per_order=10,
            is_active=True,
            sort_order=idx,
        )
        db.add(tier)
        tiers.append(tier)

    db.commit()
    for tier in tiers:
        db.refresh(tier)
    db.refresh(user)
    db.refresh(event)
    return user, event, tiers


def _create_hold(
    db: Session,
    *,
    event_id: int,
    tier_id: int,
    user_id: int,
    quantity: int,
    expires_at: datetime,
    order_id: int | None = None,
) -> TicketHold:
    hold = TicketHold(
        event_id=event_id,
        ticket_tier_id=tier_id,
        user_id=user_id,
        quantity=quantity,
        expires_at=expires_at,
        order_id=order_id,
    )
    db.add(hold)
    db.commit()
    db.refresh(hold)
    return hold


def test_create_pending_order_from_single_active_hold(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    user, event, tiers = _seed_event_with_tiers(
        db_session,
        owner_email="owner1@example.com",
        start_at=now + timedelta(days=3),
        tier_prices=[Decimal("150.00")],
    )
    hold = _create_hold(
        db_session,
        event_id=event.id,
        tier_id=tiers[0].id,
        user_id=user.id,
        quantity=2,
        expires_at=now + timedelta(hours=2),
    )

    order = create_pending_order_from_holds(db_session, user_id=user.id, hold_ids=[hold.id], now=now)

    assert order.status == OrderStatus.AWAITING_PAYMENT
    assert order.total_amount == Decimal("300.00")
    assert len(order.order_items) == 1
    assert order.order_items[0].quantity == 2
    assert order.order_items[0].unit_price == Decimal("150.00")

    db_session.refresh(hold)
    assert hold.order_id == order.id
    assert order.reference_code == format_order_reference(order.id)


def test_create_pending_order_from_multiple_holds_same_event(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    user, event, tiers = _seed_event_with_tiers(
        db_session,
        owner_email="owner2@example.com",
        start_at=now + timedelta(days=3),
        tier_prices=[Decimal("100.00"), Decimal("250.00")],
    )
    hold_1 = _create_hold(
        db_session,
        event_id=event.id,
        tier_id=tiers[0].id,
        user_id=user.id,
        quantity=1,
        expires_at=now + timedelta(hours=2),
    )
    hold_2 = _create_hold(
        db_session,
        event_id=event.id,
        tier_id=tiers[1].id,
        user_id=user.id,
        quantity=2,
        expires_at=now + timedelta(hours=2),
    )

    order = create_pending_order_from_holds(
        db_session,
        user_id=user.id,
        hold_ids=[hold_1.id, hold_2.id],
        now=now,
    )

    assert order.status == OrderStatus.AWAITING_PAYMENT
    assert order.total_amount == Decimal("600.00")
    assert len(order.order_items) == 2
    assert order.reference_code == format_order_reference(order.id)


def test_manual_order_insert_gets_reference_code_after_flush(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    user, event, _ = _seed_event_with_tiers(
        db_session,
        owner_email="manual-ref@example.com",
        start_at=now + timedelta(days=3),
        tier_prices=[Decimal("100.00")],
    )
    order = Order(
        user_id=user.id,
        event_id=event.id,
        status=OrderStatus.AWAITING_PAYMENT,
        subtotal_amount=Decimal("100.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        currency="GYD",
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    assert order.reference_code == format_order_reference(order.id)


def test_order_reference_codes_are_unique_for_multiple_orders(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    user, event, _ = _seed_event_with_tiers(
        db_session,
        owner_email="unique-ref@example.com",
        start_at=now + timedelta(days=3),
        tier_prices=[Decimal("100.00")],
    )
    first = Order(
        user_id=user.id,
        event_id=event.id,
        status=OrderStatus.AWAITING_PAYMENT,
        subtotal_amount=Decimal("100.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        currency="GYD",
    )
    second = Order(
        user_id=user.id,
        event_id=event.id,
        status=OrderStatus.AWAITING_PAYMENT,
        subtotal_amount=Decimal("100.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        currency="GYD",
    )
    db_session.add_all([first, second])
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(second)

    assert first.reference_code == format_order_reference(first.id)
    assert second.reference_code == format_order_reference(second.id)
    assert first.reference_code != second.reference_code


def test_create_pending_order_rejects_empty_hold_ids(db_session: Session) -> None:
    with pytest.raises(EmptyHoldSelectionError):
        create_pending_order_from_holds(db_session, user_id=1, hold_ids=[])


def test_create_pending_order_rejects_hold_belonging_to_another_user(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    user, event, tiers = _seed_event_with_tiers(
        db_session,
        owner_email="owner3@example.com",
        start_at=now + timedelta(days=3),
        tier_prices=[Decimal("100.00")],
    )
    other_user = User(email="other@example.com", full_name="Other")
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    hold = _create_hold(
        db_session,
        event_id=event.id,
        tier_id=tiers[0].id,
        user_id=other_user.id,
        quantity=1,
        expires_at=now + timedelta(hours=2),
    )

    with pytest.raises(HoldOwnershipError):
        create_pending_order_from_holds(db_session, user_id=user.id, hold_ids=[hold.id], now=now)


def test_create_pending_order_rejects_expired_hold(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    user, event, tiers = _seed_event_with_tiers(
        db_session,
        owner_email="owner4@example.com",
        start_at=now + timedelta(days=3),
        tier_prices=[Decimal("100.00")],
    )
    hold = _create_hold(
        db_session,
        event_id=event.id,
        tier_id=tiers[0].id,
        user_id=user.id,
        quantity=1,
        expires_at=now - timedelta(minutes=1),
    )

    with pytest.raises(HoldExpiredError):
        create_pending_order_from_holds(db_session, user_id=user.id, hold_ids=[hold.id], now=now)


def test_create_pending_order_rejects_already_attached_hold(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    user, event, tiers = _seed_event_with_tiers(
        db_session,
        owner_email="owner5@example.com",
        start_at=now + timedelta(days=3),
        tier_prices=[Decimal("100.00")],
    )
    existing_order = Order(
        user_id=user.id,
        event_id=event.id,
        status=OrderStatus.AWAITING_PAYMENT,
        total_amount=Decimal("100.00"),
        currency="GYD",
    )
    db_session.add(existing_order)
    db_session.commit()
    db_session.refresh(existing_order)

    hold = _create_hold(
        db_session,
        event_id=event.id,
        tier_id=tiers[0].id,
        user_id=user.id,
        quantity=1,
        expires_at=now + timedelta(hours=1),
        order_id=existing_order.id,
    )

    with pytest.raises(HoldAlreadyAttachedError):
        create_pending_order_from_holds(db_session, user_id=user.id, hold_ids=[hold.id], now=now)


def test_create_pending_order_rejects_holds_from_multiple_events(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    user_1, event_1, tiers_1 = _seed_event_with_tiers(
        db_session,
        owner_email="owner6a@example.com",
        start_at=now + timedelta(days=3),
        tier_prices=[Decimal("100.00")],
    )
    user_2, event_2, tiers_2 = _seed_event_with_tiers(
        db_session,
        owner_email="owner6b@example.com",
        start_at=now + timedelta(days=4),
        tier_prices=[Decimal("120.00")],
    )

    hold_1 = _create_hold(
        db_session,
        event_id=event_1.id,
        tier_id=tiers_1[0].id,
        user_id=user_1.id,
        quantity=1,
        expires_at=now + timedelta(hours=2),
    )
    hold_2 = _create_hold(
        db_session,
        event_id=event_2.id,
        tier_id=tiers_2[0].id,
        user_id=user_1.id,
        quantity=1,
        expires_at=now + timedelta(hours=2),
    )

    assert user_1.id != user_2.id

    with pytest.raises(HoldEventMismatchError):
        create_pending_order_from_holds(
            db_session,
            user_id=user_1.id,
            hold_ids=[hold_1.id, hold_2.id],
            now=now,
        )


def test_pending_orders_do_not_count_as_sold_and_no_double_count_after_conversion(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    user, event, tiers = _seed_event_with_tiers(
        db_session,
        owner_email="owner7@example.com",
        start_at=now + timedelta(days=3),
        tier_prices=[Decimal("100.00")],
        quantity_total=10,
    )
    hold = _create_hold(
        db_session,
        event_id=event.id,
        tier_id=tiers[0].id,
        user_id=user.id,
        quantity=3,
        expires_at=now + timedelta(hours=2),
    )

    availability_before = get_ticket_type_availability(db_session, ticket_tier_id=tiers[0].id, now=now)
    assert availability_before == 7

    create_pending_order_from_holds(db_session, user_id=user.id, hold_ids=[hold.id], now=now)

    availability_after = get_ticket_type_availability(db_session, ticket_tier_id=tiers[0].id, now=now)
    assert availability_after == 7


def test_create_comp_order_marks_zero_total_and_comp_flags(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    user, event, tiers = _seed_event_with_tiers(
        db_session,
        owner_email="compowner@example.com",
        start_at=now + timedelta(days=3),
        tier_prices=[Decimal("100.00")],
        quantity_total=10,
    )

    order = create_comp_order_for_user(
        db_session,
        event_id=event.id,
        purchaser_user_id=user.id,
        actor_user_id=user.id,
        ticket_requests=[{"ticket_tier_id": tiers[0].id, "quantity": 2}],
        reason="VIP guest",
    )

    assert order.total_amount == Decimal("0.00")
    assert order.subtotal_amount == Decimal("200.00")
    assert order.discount_amount == Decimal("200.00")
    assert order.is_comp is True


def test_unrelated_user_cannot_create_comp_order(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    user, event, tiers = _seed_event_with_tiers(
        db_session,
        owner_email="compowner2@example.com",
        start_at=now + timedelta(days=3),
        tier_prices=[Decimal("100.00")],
        quantity_total=10,
    )
    outsider = User(email="outsider@example.com", full_name="Out")
    db_session.add(outsider)
    db_session.commit()

    with pytest.raises(OrderAuthorizationError):
        create_comp_order_for_user(
            db_session,
            event_id=event.id,
            purchaser_user_id=user.id,
            actor_user_id=outsider.id,
            ticket_requests=[{"ticket_tier_id": tiers[0].id, "quantity": 1}],
        )


def test_comp_order_respects_active_hold_capacity(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    user, event, tiers = _seed_event_with_tiers(
        db_session,
        owner_email="compowner3@example.com",
        start_at=now + timedelta(days=3),
        tier_prices=[Decimal("100.00")],
        quantity_total=2,
    )
    _create_hold(
        db_session,
        event_id=event.id,
        tier_id=tiers[0].id,
        user_id=user.id,
        quantity=2,
        expires_at=now + timedelta(hours=1),
    )

    with pytest.raises(OrderFlowError):
        create_comp_order_for_user(
            db_session,
            event_id=event.id,
            purchaser_user_id=user.id,
            actor_user_id=user.id,
            ticket_requests=[{"ticket_tier_id": tiers[0].id, "quantity": 1}],
        )
