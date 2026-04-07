from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Event, OrganizerProfile, Order, TicketHold, TicketTier, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus, PromoCodeDiscountType
from app.models.promo_code import PromoCode
from app.models.promo_code_redemption import PromoCodeRedemption
from app.models.promo_code_ticket_tier import PromoCodeTicketTier
from app.services.orders import create_pending_order_from_holds
from app.services.promo_codes import PromoCodeValidationError


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


def _seed(db: Session):
    now = datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc)
    user = User(email="buyer@example.com", full_name="Buyer")
    db.add(user)
    db.flush()
    organizer = OrganizerProfile(user_id=user.id, business_name="Org", display_name="Org")
    db.add(organizer)
    db.flush()
    venue = Venue(organizer_id=organizer.id, name="Venue")
    db.add(venue)
    db.flush()
    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title="Promo Event",
        slug="promo-event",
        start_at=now + timedelta(days=1),
        end_at=now + timedelta(days=1, hours=2),
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
    hold = TicketHold(
        event_id=event.id,
        ticket_tier_id=tier.id,
        user_id=user.id,
        quantity=2,
        expires_at=now + timedelta(hours=1),
    )
    db.add(hold)
    db.commit()
    return user, event, tier, hold, now


def test_percentage_promo_applies_and_snapshots_on_order(db_session: Session) -> None:
    user, event, tier, hold, now = _seed(db_session)
    promo = PromoCode(
        event_id=event.id,
        code="SAVE10",
        code_normalized="SAVE10",
        discount_type=PromoCodeDiscountType.PERCENTAGE,
        discount_value=Decimal("10.00"),
        applies_to_all_tiers=True,
        is_active=True,
    )
    db_session.add(promo)
    db_session.commit()

    order = create_pending_order_from_holds(
        db_session,
        user_id=user.id,
        hold_ids=[hold.id],
        promo_code_text="save10",
        now=now,
    )

    assert order.subtotal_amount == Decimal("200.00")
    assert order.discount_amount == Decimal("20.00")
    assert order.total_amount == Decimal("180.00")
    assert order.promo_code_id == promo.id
    assert order.promo_code_text == "SAVE10"


def test_fixed_amount_discount_is_capped(db_session: Session) -> None:
    user, event, _, hold, now = _seed(db_session)
    promo = PromoCode(
        event_id=event.id,
        code="BIGOFF",
        code_normalized="BIGOFF",
        discount_type=PromoCodeDiscountType.FIXED_AMOUNT,
        discount_value=Decimal("500.00"),
        applies_to_all_tiers=True,
        is_active=True,
    )
    db_session.add(promo)
    db_session.commit()

    order = create_pending_order_from_holds(
        db_session,
        user_id=user.id,
        hold_ids=[hold.id],
        promo_code_text="BIGOFF",
        now=now,
    )
    assert order.total_amount == Decimal("0.00")
    assert order.discount_amount == Decimal("200.00")


def test_tier_scoped_and_usage_caps_enforced(db_session: Session) -> None:
    user, event, tier, hold, now = _seed(db_session)
    other_tier = TicketTier(
        event_id=event.id,
        name="VIP",
        tier_code="VIP",
        price_amount=Decimal("200.00"),
        currency="GYD",
        quantity_total=10,
        quantity_sold=0,
        quantity_held=0,
        min_per_order=1,
        max_per_order=10,
        is_active=True,
        sort_order=1,
    )
    db_session.add(other_tier)
    db_session.flush()
    promo = PromoCode(
        event_id=event.id,
        code="VIPONLY",
        code_normalized="VIPONLY",
        discount_type=PromoCodeDiscountType.FIXED_AMOUNT,
        discount_value=Decimal("10.00"),
        applies_to_all_tiers=False,
        is_active=True,
        max_redemptions_per_user=1,
    )
    db_session.add(promo)
    db_session.flush()
    db_session.add(PromoCodeTicketTier(promo_code_id=promo.id, ticket_tier_id=other_tier.id))
    prior_order = Order(
        user_id=user.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        subtotal_amount=Decimal("100.00"),
        discount_amount=Decimal("10.00"),
        total_amount=Decimal("90.00"),
        currency="GYD",
        payment_verification_status="verified",
    )
    db_session.add(prior_order)
    db_session.flush()
    db_session.add(
        PromoCodeRedemption(
            promo_code_id=promo.id,
            order_id=prior_order.id,
            user_id=user.id,
            redeemed_at=now,
            discount_amount=Decimal("10.00"),
        )
    )
    db_session.commit()

    with pytest.raises(PromoCodeValidationError):
        create_pending_order_from_holds(
            db_session,
            user_id=user.id,
            hold_ids=[hold.id],
            promo_code_text="VIPONLY",
            now=now,
        )
