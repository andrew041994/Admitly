from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.api.admin_finance import export_admin_orders_csv, get_admin_summary
from app.models import Dispute, Event, OrganizerProfile, Order, Refund, User, Venue
from app.models.enums import (
    DisputeStatus,
    EventApprovalStatus,
    EventStatus,
    EventVisibility,
    OrderStatus,
    PricingSource,
    PayoutStatus,
    ReconciliationStatus,
    RefundReason,
    RefundStatus,
)
from app.services.finance_reporting import get_admin_finance_summary, list_admin_finance_orders
from tests.utils import unique_email



def _seed(db: Session):
    now = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)
    admin = User(email=unique_email("admin_fin_report"), full_name="Admin", is_admin=True)
    user = User(email=unique_email("user_fin_report"), full_name="User")
    organizer_user = User(email=unique_email("organizer_fin_report"), full_name="Org")
    db.add_all([admin, user, organizer_user])
    db.flush()

    organizer = OrganizerProfile(user_id=organizer_user.id, business_name="Biz", display_name="Biz")
    db.add(organizer)
    db.flush()
    venue = Venue(organizer_id=organizer.id, name="Venue")
    db.add(venue)
    db.flush()

    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title="Event",
        slug="event-fin-report",
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

    inside = Order(
        user_id=user.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        payment_verification_status="verified",
        pricing_source=PricingSource.PROMO_CODE,
        subtotal_amount=Decimal("120.00"),
        discount_amount=Decimal("20.00"),
        total_amount=Decimal("100.00"),
        paid_at=now,
        payout_status=PayoutStatus.ELIGIBLE,
        reconciliation_status=ReconciliationStatus.UNRECONCILED,
    )
    refunded = Order(
        user_id=user.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        payment_verification_status="verified",
        subtotal_amount=Decimal("50.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("50.00"),
        paid_at=now + timedelta(minutes=5),
        payout_status=PayoutStatus.PAID,
        reconciliation_status=ReconciliationStatus.RECONCILED,
    )
    outside = Order(
        user_id=user.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        payment_verification_status="verified",
        subtotal_amount=Decimal("30.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("30.00"),
        paid_at=now - timedelta(days=7),
    )
    db.add_all([inside, refunded, outside])
    db.flush()

    db.add(Refund(order_id=refunded.id, user_id=user.id, amount=Decimal("10.00"), status=RefundStatus.PROCESSED, reason=RefundReason.OTHER))
    db.add(Dispute(order_id=inside.id, user_id=user.id, message="chargeback", status=DisputeStatus.OPEN))
    db.commit()

    return {"admin": admin, "user": user, "event": event, "now": now}


def test_admin_summary_calculation_and_date_range(db_session: Session):
    data = _seed(db_session)
    summary = get_admin_finance_summary(
        db_session,
        date_from=data["now"] - timedelta(hours=1),
        date_to=data["now"] + timedelta(days=1),
    )

    assert summary.gross_sales_amount == Decimal("150.00")
    assert summary.refunded_amount == Decimal("10.00")
    assert summary.discount_amount == Decimal("20.00")
    assert summary.dispute_count == 1
    assert summary.promo_usage_count == 1
    assert summary.settled_amount == Decimal("40.00")


def test_admin_orders_use_paid_at_window(db_session: Session):
    data = _seed(db_session)
    rows = list_admin_finance_orders(
        db_session,
        date_from=data["now"] - timedelta(hours=1),
        date_to=data["now"] + timedelta(hours=1),
    )
    assert len(rows) == 2


def test_admin_csv_export_headers_and_rows(db_session: Session):
    data = _seed(db_session)
    response = export_admin_orders_csv(
        date_from=data["now"] - timedelta(hours=1),
        date_to=data["now"] + timedelta(hours=1),
        event_id=None,
        organizer_user_id=None,
        db=db_session,
        user_id=data["admin"].id,
    )
    assert response.media_type == "text/csv"
    body = response.body.decode()
    assert body.splitlines()[0] == (
        "order_id,order_reference,event_id,buyer_user_id,status,refund_status,reconciliation_status,"
        "payout_status,subtotal_amount,discount_amount,total_amount,refunded_amount,"
        "payout_eligible_amount,currency,paid_at"
    )
    assert "100.00" in body


def test_admin_summary_requires_admin(db_session: Session):
    data = _seed(db_session)
    with pytest.raises(HTTPException) as exc:
        get_admin_summary(db=db_session, user_id=data["user"].id)
    assert exc.value.status_code == 403
