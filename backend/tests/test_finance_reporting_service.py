from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.db.base import Base
from app.models import Event, OrganizerProfile, Order, User, Venue
from app.models.enums import (
    EventApprovalStatus,
    EventStatus,
    EventVisibility,
    OrderStatus,
    PayoutStatus,
    ReconciliationStatus,
)
from app.services.finance_reporting import (
    FinanceReportingAuthorizationError,
    get_event_finance_summary,
    get_order_payout_eligible_amount,
    get_organizer_payout_summary,
    is_order_financially_eligible_for_payout,
    list_event_finance_orders,
    mark_order_payout_status,
    mark_order_reconciled,
    validate_organizer_finance_access,
)
from app.services.orders import complete_paid_order


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


def _seed_finance_data(db: Session):
    now = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)

    organizer_user = User(email="organizer-finance@example.com", full_name="Organizer")
    unrelated_user = User(email="unrelated-finance@example.com", full_name="Unrelated")
    admin_user = User(email="admin-finance@example.com", full_name="Admin", is_admin=True)
    buyer = User(email="buyer-finance@example.com", full_name="Buyer")
    db.add_all([organizer_user, unrelated_user, admin_user, buyer])
    db.flush()

    organizer = OrganizerProfile(user_id=organizer_user.id, business_name="Biz", display_name="Biz")
    db.add(organizer)
    db.flush()

    venue = Venue(organizer_id=organizer.id, name="Main Venue")
    db.add(venue)
    db.flush()

    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title="Finance Event",
        slug="finance-event",
        start_at=now + timedelta(days=7),
        end_at=now + timedelta(days=7, hours=3),
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        approval_status=EventApprovalStatus.APPROVED,
        timezone="America/Guyana",
        is_location_pinned=False,
    )
    other_event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title="Finance Event 2",
        slug="finance-event-2",
        start_at=now + timedelta(days=8),
        end_at=now + timedelta(days=8, hours=3),
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        approval_status=EventApprovalStatus.APPROVED,
        timezone="America/Guyana",
        is_location_pinned=False,
    )
    db.add_all([event, other_event])
    db.flush()

    completed_eligible = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        total_amount=Decimal("100.00"),
        currency="GYD",
        payment_verification_status="verified",
        reconciliation_status=ReconciliationStatus.UNRECONCILED,
        payout_status=PayoutStatus.ELIGIBLE,
        subtotal_amount=Decimal("120.00"),
        discount_amount=Decimal("20.00"),
    )
    completed_reconciled = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        total_amount=Decimal("50.00"),
        currency="GYD",
        payment_verification_status="verified",
        reconciliation_status=ReconciliationStatus.RECONCILED,
        payout_status=PayoutStatus.ELIGIBLE,
        subtotal_amount=Decimal("50.00"),
        discount_amount=Decimal("0.00"),
    )
    refunded_order = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        total_amount=Decimal("30.00"),
        currency="GYD",
        payment_verification_status="verified",
        refund_status="refunded",
        refunded_at=now,
        reconciliation_status=ReconciliationStatus.UNRECONCILED,
        payout_status=PayoutStatus.ELIGIBLE,
        subtotal_amount=Decimal("30.00"),
        discount_amount=Decimal("0.00"),
    )
    comp_order = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        subtotal_amount=Decimal("40.00"),
        discount_amount=Decimal("40.00"),
        total_amount=Decimal("0.00"),
        currency="GYD",
        payment_verification_status="verified",
        is_comp=True,
    )
    pending_order = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.PENDING,
        total_amount=Decimal("70.00"),
        currency="GYD",
        payment_verification_status="pending",
    )
    cancelled_order = Order(
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.CANCELLED,
        total_amount=Decimal("90.00"),
        currency="GYD",
        payment_verification_status="not_started",
    )
    other_event_order = Order(
        user_id=buyer.id,
        event_id=other_event.id,
        status=OrderStatus.COMPLETED,
        total_amount=Decimal("40.00"),
        currency="GYD",
        payment_verification_status="verified",
        reconciliation_status=ReconciliationStatus.UNRECONCILED,
        payout_status=PayoutStatus.PAID,
    )
    db.add_all(
        [completed_eligible, completed_reconciled, refunded_order, pending_order, cancelled_order, other_event_order, comp_order]
    )
    db.commit()

    return {
        "organizer_user": organizer_user,
        "unrelated_user": unrelated_user,
        "admin_user": admin_user,
        "event": event,
        "other_event": other_event,
        "completed_eligible": completed_eligible,
        "pending_order": pending_order,
        "cancelled_order": cancelled_order,
        "refunded_order": refunded_order,
    }


def test_payout_eligibility_helper_rules(db_session: Session) -> None:
    data = _seed_finance_data(db_session)
    completed = data["completed_eligible"]
    pending = data["pending_order"]
    cancelled = data["cancelled_order"]
    refunded = data["refunded_order"]

    assert is_order_financially_eligible_for_payout(completed) is True
    assert is_order_financially_eligible_for_payout(pending) is False
    assert is_order_financially_eligible_for_payout(cancelled) is False
    assert get_order_payout_eligible_amount(refunded) == Decimal("0.00")


def test_event_finance_summary_rollups(db_session: Session) -> None:
    data = _seed_finance_data(db_session)
    summary = get_event_finance_summary(db_session, event_id=data["event"].id)

    assert summary.gross_sales_amount == Decimal("180.00")
    assert summary.gross_face_value_amount == Decimal("240.00")
    assert summary.total_discount_amount == Decimal("60.00")
    assert summary.refunded_amount == Decimal("30.00")
    assert summary.net_sales_amount == Decimal("150.00")
    assert summary.eligible_payout_amount == Decimal("150.00")
    assert summary.reconciled_amount == Decimal("50.00")
    assert summary.unreconciled_amount == Decimal("130.00")
    assert summary.completed_order_count == 4
    assert summary.comp_order_count == 1
    assert summary.comp_face_value == Decimal("40.00")


def test_finance_order_list_filters_to_event_and_statuses(db_session: Session) -> None:
    data = _seed_finance_data(db_session)
    rows = list_event_finance_orders(db_session, event_id=data["event"].id)
    assert {row.order_id for row in rows}.isdisjoint(
        {order.order_id for order in list_event_finance_orders(db_session, event_id=data["other_event"].id)}
    )

    filtered = list_event_finance_orders(
        db_session,
        event_id=data["event"].id,
        reconciliation_status=ReconciliationStatus.RECONCILED,
    )
    assert len(filtered) == 1
    assert filtered[0].reconciliation_status == "reconciled"


def test_organizer_payout_summary_and_access(db_session: Session) -> None:
    data = _seed_finance_data(db_session)
    organizer_id = data["organizer_user"].id

    validate_organizer_finance_access(db_session, actor_user_id=organizer_id, organizer_user_id=organizer_id)
    summary = get_organizer_payout_summary(db_session, organizer_user_id=organizer_id)
    assert summary.total_gross_sales == Decimal("220.00")
    assert summary.total_refunded == Decimal("30.00")
    assert summary.total_payout_eligible == Decimal("150.00")

    with pytest.raises(FinanceReportingAuthorizationError):
        validate_organizer_finance_access(
            db_session,
            actor_user_id=data["unrelated_user"].id,
            organizer_user_id=organizer_id,
        )


def test_internal_reconciliation_actions_require_admin(db_session: Session) -> None:
    data = _seed_finance_data(db_session)
    order_id = data["completed_eligible"].id

    mark_order_reconciled(
        db_session,
        order_id=order_id,
        actor_user_id=data["admin_user"].id,
        note="MMG statement matched",
    )
    updated = mark_order_payout_status(
        db_session,
        order_id=order_id,
        actor_user_id=data["admin_user"].id,
        payout_status=PayoutStatus.INCLUDED,
        note="Batch Apr-07",
    )
    assert updated.payout_status == PayoutStatus.INCLUDED
    assert updated.payout_included_at is not None

    with pytest.raises(FinanceReportingAuthorizationError):
        mark_order_reconciled(
            db_session,
            order_id=order_id,
            actor_user_id=data["organizer_user"].id,
        )


def test_completed_payment_initializes_finance_defaults(db_session: Session) -> None:
    data = _seed_finance_data(db_session)
    order = data["pending_order"]
    order.status = OrderStatus.PENDING
    order.payment_verification_status = "verified"

    complete_paid_order(db_session, order)

    assert order.status == OrderStatus.COMPLETED
    assert order.reconciliation_status == ReconciliationStatus.UNRECONCILED
    assert order.payout_status == PayoutStatus.ELIGIBLE
