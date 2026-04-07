from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models import Event, OrganizerProfile, Order, OrderItem, TicketHold, TicketTier, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus
from app.services.orders import OrderNotPayableError, validate_order_still_payable
from app.services.payments import (
    PaymentAuthorizationError,
    create_mmg_agent_checkout_for_order,
    create_mmg_checkout_for_order,
    handle_mmg_callback,
    mark_agent_payment_verified,
    submit_mmg_agent_payment,
)
from app.services.ticket_holds import get_ticket_type_availability


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
def mmg_config() -> None:
    settings.mmg_enabled = True
    settings.mmg_provider_mode = "mock"
    settings.mmg_agent_auto_verify_enabled = True


def _seed_order_with_hold(db: Session, *, user_email: str = "u@example.com") -> tuple[Order, TicketTier, User]:
    now = datetime.now(timezone.utc)
    user = User(email=user_email, full_name="User")
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
        slug=f"concert-{user_email}-{int(now.timestamp())}",
        start_at=now + timedelta(days=3),
        end_at=now + timedelta(days=3, hours=3),
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
        tier_code="GEN",
        price_amount=Decimal("100.00"),
        currency="GYD",
        quantity_total=10,
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
        status=OrderStatus.PENDING,
        total_amount=Decimal("200.00"),
        currency="GYD",
    )
    db.add(order)
    db.flush()

    db.add(OrderItem(order_id=order.id, ticket_tier_id=tier.id, quantity=2, unit_price=Decimal("100.00")))
    db.add(
        TicketHold(
            event_id=event.id,
            ticket_tier_id=tier.id,
            user_id=user.id,
            quantity=2,
            expires_at=now + timedelta(hours=2),
            order_id=order.id,
        )
    )
    db.commit()
    db.refresh(order)
    db.refresh(tier)
    db.refresh(user)
    return order, tier, user


def test_validate_order_still_payable_passes_for_pending_with_active_holds(db_session: Session) -> None:
    order, _, _ = _seed_order_with_hold(db_session)
    validate_order_still_payable(order)


def test_validate_order_still_payable_rejects_expired_hold(db_session: Session) -> None:
    order, _, _ = _seed_order_with_hold(db_session)
    order.ticket_holds[0].expires_at = datetime(2026, 4, 6, 8, 0, tzinfo=timezone.utc)
    with pytest.raises(OrderNotPayableError):
        validate_order_still_payable(order, now=datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc))
    assert order.status == OrderStatus.EXPIRED


def test_validate_order_still_payable_rejects_non_pending_statuses(db_session: Session) -> None:
    order, _, _ = _seed_order_with_hold(db_session)
    for status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.EXPIRED):
        order.status = status
        with pytest.raises(OrderNotPayableError):
            validate_order_still_payable(order)


def test_mmg_checkout_initiation_is_idempotent_and_pending_not_sold(db_session: Session) -> None:
    order, tier, user = _seed_order_with_hold(db_session)

    before = get_ticket_type_availability(db_session, tier.id, now=datetime.now(timezone.utc))
    first = create_mmg_checkout_for_order(db_session, order_id=order.id, user_id=user.id)
    second = create_mmg_checkout_for_order(db_session, order_id=order.id, user_id=user.id)
    after = get_ticket_type_availability(db_session, tier.id, now=datetime.now(timezone.utc))

    assert first.checkout_url
    assert first.payment_reference == second.payment_reference
    assert first.checkout_url == second.checkout_url
    assert first.status == "pending"
    assert before == after


def test_mmg_checkout_rejects_wrong_user(db_session: Session) -> None:
    order, _, _ = _seed_order_with_hold(db_session)
    with pytest.raises(PaymentAuthorizationError):
        create_mmg_checkout_for_order(db_session, order_id=order.id, user_id=999)


def test_mmg_agent_initiation_and_submit_outcomes(db_session: Session) -> None:
    order, tier, user = _seed_order_with_hold(db_session)

    initiated = create_mmg_agent_checkout_for_order(db_session, order_id=order.id, user_id=user.id)
    assert initiated.payment_reference.startswith("AGT-")
    assert get_ticket_type_availability(db_session, tier.id, now=datetime.now(timezone.utc)) == 8

    verified = submit_mmg_agent_payment(
        db_session,
        order_id=order.id,
        user_id=user.id,
        submitted_reference_code=initiated.payment_reference,
    )
    assert verified.payment_verification_status == "verified"
    assert verified.status == "completed"
    assert get_ticket_type_availability(db_session, tier.id, now=datetime.now(timezone.utc)) == 8


def test_mmg_agent_submit_pending_and_rejected_paths(db_session: Session) -> None:
    settings.mmg_agent_auto_verify_enabled = False
    order, _, user = _seed_order_with_hold(db_session, user_email="pending@example.com")
    initiated = create_mmg_agent_checkout_for_order(db_session, order_id=order.id, user_id=user.id)

    pending = submit_mmg_agent_payment(
        db_session,
        order_id=order.id,
        user_id=user.id,
        submitted_reference_code=initiated.payment_reference,
    )
    assert pending.payment_verification_status == "pending_verification"
    assert pending.status == "pending"

    settings.mmg_agent_auto_verify_enabled = True
    order2, _, user2 = _seed_order_with_hold(db_session, user_email="reject@example.com")
    initiated2 = create_mmg_agent_checkout_for_order(db_session, order_id=order2.id, user_id=user2.id)
    rejected = submit_mmg_agent_payment(
        db_session,
        order_id=order2.id,
        user_id=user2.id,
        submitted_reference_code=f"{initiated2.payment_reference}-FAIL",
    )
    assert rejected.payment_verification_status == "rejected"
    assert rejected.status == "pending"


def test_manual_agent_verify_hook_and_callback_scaffold(db_session: Session) -> None:
    order, _, user = _seed_order_with_hold(db_session, user_email="manual@example.com")
    initiated = create_mmg_agent_checkout_for_order(db_session, order_id=order.id, user_id=user.id)

    mark_agent_payment_verified(db_session, order_id=order.id, payment_reference=initiated.payment_reference)
    db_session.refresh(order)
    assert order.status == OrderStatus.COMPLETED

    checkout_order, _, checkout_user = _seed_order_with_hold(db_session, user_email="cb@example.com")
    create_mmg_checkout_for_order(db_session, order_id=checkout_order.id, user_id=checkout_user.id)
    callback = handle_mmg_callback(
        db_session,
        payload={"payment_reference": checkout_order.payment_reference, "status": "paid"},
    )
    assert callback.status == "completed"


def test_paid_callback_is_idempotent_and_does_not_double_issue_tickets(db_session: Session) -> None:
    checkout_order, _, checkout_user = _seed_order_with_hold(db_session, user_email="idempotent@example.com")
    create_mmg_checkout_for_order(db_session, order_id=checkout_order.id, user_id=checkout_user.id)

    first = handle_mmg_callback(
        db_session,
        payload={"payment_reference": checkout_order.payment_reference, "status": "paid"},
    )
    second = handle_mmg_callback(
        db_session,
        payload={"payment_reference": checkout_order.payment_reference, "status": "paid"},
    )
    db_session.refresh(checkout_order)
    assert first.status == "completed"
    assert second.status == "completed"
    assert len(checkout_order.tickets) == 2


def test_callback_cannot_complete_order_after_hold_expiration(db_session: Session) -> None:
    checkout_order, _, checkout_user = _seed_order_with_hold(db_session, user_email="expired-callback@example.com")
    create_mmg_checkout_for_order(db_session, order_id=checkout_order.id, user_id=checkout_user.id)
    checkout_order.ticket_holds[0].expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    with pytest.raises(OrderNotPayableError):
        handle_mmg_callback(
            db_session,
            payload={"payment_reference": checkout_order.payment_reference, "status": "paid"},
        )

    db_session.refresh(checkout_order)
    assert checkout_order.status == OrderStatus.PENDING


def test_live_mode_missing_config_fails_clearly(db_session: Session) -> None:
    settings.mmg_provider_mode = "live"
    settings.mmg_base_url = None
    settings.mmg_merchant_id = None
    settings.mmg_api_key = None
    settings.mmg_api_secret = None
    settings.mmg_callback_url = None

    order, _, user = _seed_order_with_hold(db_session, user_email="live@example.com")
    with pytest.raises(Exception) as exc:
        create_mmg_checkout_for_order(db_session, order_id=order.id, user_id=user.id)
    assert "missing required config" in str(exc.value).lower()

def test_mmg_checkout_uses_discounted_total_amount(db_session: Session) -> None:
    order, _, user = _seed_order_with_hold(db_session, user_email="discounted@example.com")
    order.subtotal_amount = Decimal("200.00")
    order.discount_amount = Decimal("50.00")
    order.total_amount = Decimal("150.00")
    db_session.commit()

    snapshot = create_mmg_checkout_for_order(db_session, order_id=order.id, user_id=user.id)
    assert snapshot.amount == Decimal("150.00")
