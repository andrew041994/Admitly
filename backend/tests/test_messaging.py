from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.messaging import get_event_message_history, send_event_broadcast_message
from app.db.base import Base
from app.models import Event, OrganizerProfile, Order, OrderItem, Ticket, TicketTier, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, MessageDeliveryStatus, MessageTemplateType, OrderStatus, TicketStatus
from app.models.message_delivery_log import MessageDeliveryLog
from app.schemas.messaging import EventBroadcastSendRequest
from app.services.notifications import notify_order_completed
from app.services.tickets import issue_tickets_for_completed_order



def _seed(db: Session, *, admin: bool = True):
    now = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)
    actor = User(email="actor@test.local", full_name="Actor", is_admin=admin)
    buyer = User(email="buyer@test.local", full_name="Buyer")
    organizer_user = User(email="org@test.local", full_name="Organizer")
    db.add_all([actor, buyer, organizer_user])
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
        slug="event",
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
        tier_code="GEN",
        price_amount=Decimal("100.00"),
        currency="GYD",
        quantity_total=100,
        quantity_sold=0,
        quantity_held=0,
        min_per_order=1,
        max_per_order=4,
        is_active=True,
        sort_order=0,
    )
    db.add(tier)
    db.flush()
    order = Order(user_id=buyer.id, event_id=event.id, status=OrderStatus.COMPLETED, total_amount=Decimal("100.00"), currency="GYD", payment_verification_status="verified")
    db.add(order)
    db.flush()
    db.add(OrderItem(order_id=order.id, ticket_tier_id=tier.id, quantity=1, unit_price=Decimal("100.00")))
    db.commit()
    issue_tickets_for_completed_order(db, order)
    return actor, buyer, event, order


def test_dispatch_logs_order_confirmation_attempts(db_session: Session) -> None:
    _, _, _, order = _seed(db_session)
    notify_order_completed(db_session, order)
    notify_order_completed(db_session, order)
    logs = db_session.execute(select(MessageDeliveryLog).where(MessageDeliveryLog.related_entity_type == "order", MessageDeliveryLog.related_entity_id == order.id, MessageDeliveryLog.template_type == MessageTemplateType.ORDER_CONFIRMATION)).scalars().all()
    assert len(logs) == 4


def test_event_broadcast_permission_enforced(db_session: Session) -> None:
    actor, _, event, _ = _seed(db_session, admin=False)
    with pytest.raises(HTTPException) as exc:
        send_event_broadcast_message(event.id, EventBroadcastSendRequest(subject="update", body="hello", include_email=True, include_push=False), db=db_session, user_id=actor.id)
    assert exc.value.status_code == 403


def test_event_broadcast_and_history(db_session: Session) -> None:
    actor, _, event, _ = _seed(db_session, admin=True)
    result = send_event_broadcast_message(event.id, EventBroadcastSendRequest(subject="Ops", body="Doors delayed", include_email=False, include_push=True), db=db_session, user_id=actor.id)
    assert result.attempted_recipients == 1
    history = get_event_message_history(event.id, db=db_session, user_id=actor.id)
    assert len(history) >= 1
    assert history[0].template_type in {MessageTemplateType.EVENT_DAY_UPDATE.value, MessageTemplateType.REMINDER.value}


def test_failed_dispatch_logged(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, _, order = _seed(db_session)
    monkeypatch.setattr("app.services.notifications._send_email", lambda message: (_ for _ in ()).throw(RuntimeError("boom")))
    result = notify_order_completed(db_session, order)
    assert result.success is False
    failed = db_session.execute(select(MessageDeliveryLog).where(MessageDeliveryLog.status == MessageDeliveryStatus.FAILED)).scalars().all()
    assert failed
