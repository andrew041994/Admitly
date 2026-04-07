from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Event, FinancialEntry, OrganizerBalanceAdjustment, OrganizerProfile, Order, Refund, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus, PayoutStatus, RefundReason
from app.services.events import (
    EventAuthorizationError,
    cancel_event,
    enqueue_event_refund_batch,
    process_event_refund_batch,
)
from app.services.refunds import process_refund_for_order


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


def _seed_event_with_orders(db: Session):
    now = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)
    admin = User(email="admin@phase15.test", full_name="Admin", is_admin=True)
    organizer_user = User(email="org@phase15.test", full_name="Organizer")
    buyer = User(email="buyer@phase15.test", full_name="Buyer")
    outsider = User(email="outsider@phase15.test", full_name="Outsider")
    db.add_all([admin, organizer_user, buyer, outsider])
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
        title="Cancelled Event",
        slug=f"phase15-event-{int(now.timestamp())}",
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

    paid = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        total_amount=Decimal("100.00"),
        subtotal_amount=Decimal("100.00"),
        currency="GYD",
        payment_verification_status="verified",
        payout_status=PayoutStatus.ELIGIBLE,
    )
    partial = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        total_amount=Decimal("80.00"),
        subtotal_amount=Decimal("80.00"),
        currency="GYD",
        payment_verification_status="verified",
    )
    comped = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        total_amount=Decimal("0.00"),
        subtotal_amount=Decimal("50.00"),
        discount_amount=Decimal("50.00"),
        currency="GYD",
        payment_verification_status="verified",
        is_comp=True,
    )
    paid_out = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        total_amount=Decimal("60.00"),
        subtotal_amount=Decimal("60.00"),
        currency="GYD",
        payment_verification_status="verified",
        payout_status=PayoutStatus.PAID,
        payout_paid_at=now,
    )
    db.add_all([paid, partial, comped, paid_out])
    db.flush()

    process_refund_for_order(
        db,
        order_id=partial.id,
        actor_user_id=admin.id,
        reason=RefundReason.USER_REQUEST,
        amount=Decimal("30.00"),
        admin_notes="partial",
    )
    process_refund_for_order(
        db,
        order_id=paid.id,
        actor_user_id=admin.id,
        reason=RefundReason.USER_REQUEST,
        amount=Decimal("100.00"),
        admin_notes="full",
    )
    db.commit()

    return {
        "admin": admin,
        "organizer": organizer_user,
        "outsider": outsider,
        "event": event,
        "paid": paid,
        "partial": partial,
        "comped": comped,
        "paid_out": paid_out,
    }


def test_organizer_can_cancel_owned_event_and_outsider_cannot(db_session: Session) -> None:
    data = _seed_event_with_orders(db_session)
    with pytest.raises(EventAuthorizationError):
        cancel_event(db_session, event_id=data["event"].id, actor_user_id=data["outsider"].id)

    event, batch = cancel_event(
        db_session,
        event_id=data["event"].id,
        actor_user_id=data["organizer"].id,
        reason="weather",
    )
    assert event.status == EventStatus.CANCELLED
    assert event.cancellation_reason == "weather"
    assert batch.event_id == event.id


def test_admin_can_cancel_any_event_and_auto_refunds_only_remaining_amounts(db_session: Session) -> None:
    data = _seed_event_with_orders(db_session)
    event, batch = cancel_event(db_session, event_id=data["event"].id, actor_user_id=data["admin"].id)
    assert event.status == EventStatus.CANCELLED
    assert batch.status.value == "completed"

    refunds = db_session.execute(select(Refund).where(Refund.order_id == data["partial"].id)).scalars().all()
    total_partial_refunded = sum(Decimal(ref.amount) for ref in refunds)
    assert total_partial_refunded == Decimal("80.00")

    comp_refunds = db_session.execute(select(Refund).where(Refund.order_id == data["comped"].id)).scalars().all()
    assert comp_refunds == []


def test_cancellation_batch_creates_financial_entries_and_offsets_for_paid_out(db_session: Session) -> None:
    data = _seed_event_with_orders(db_session)
    _, batch = cancel_event(db_session, event_id=data["event"].id, actor_user_id=data["admin"].id)

    paid_out_refunds = db_session.execute(select(Refund).where(Refund.order_id == data["paid_out"].id)).scalars().all()
    assert any(ref.reason == RefundReason.EVENT_CANCELED for ref in paid_out_refunds)

    entries = db_session.execute(
        select(FinancialEntry).where(FinancialEntry.order_id == data["paid_out"].id)
    ).scalars().all()
    assert entries

    adjustments = db_session.execute(
        select(OrganizerBalanceAdjustment).where(OrganizerBalanceAdjustment.order_id == data["paid_out"].id)
    ).scalars().all()
    assert adjustments
    assert batch.successful_refunds >= 1


def test_enqueue_prevents_duplicate_active_batches(db_session: Session) -> None:
    data = _seed_event_with_orders(db_session)
    batch1 = enqueue_event_refund_batch(db_session, event_id=data["event"].id, actor_user_id=data["admin"].id)
    batch2 = enqueue_event_refund_batch(db_session, event_id=data["event"].id, actor_user_id=data["admin"].id)
    assert batch1.id == batch2.id


def test_batch_reprocess_is_idempotent(db_session: Session) -> None:
    data = _seed_event_with_orders(db_session)
    _, batch = cancel_event(db_session, event_id=data["event"].id, actor_user_id=data["admin"].id)
    total_refunds_before = db_session.execute(select(Refund)).scalars().all()

    process_event_refund_batch(db_session, batch_id=batch.id, actor_user_id=data["admin"].id)
    total_refunds_after = db_session.execute(select(Refund)).scalars().all()
    assert len(total_refunds_before) == len(total_refunds_after)
