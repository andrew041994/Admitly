from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.orders import resend_order_confirmation_notification
from app.db.base import Base
from app.api.tickets import resend_ticket
from app.models import Event, OrganizerProfile, Order, OrderItem, TicketTier, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus, ReminderType
from app.services.events import cancel_event
from app.services import notifications as notification_service
from app.services.notifications import (
    NotificationChannel,
    NotificationEventType,
    get_notification_channels,
    notify_event_reminder,
    notify_order_completed,
    notify_tickets_issued,
)
from app.services.orders import complete_paid_order, refund_completed_order
from app.services.tickets import issue_tickets_for_completed_order, transfer_ticket_to_user


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


def _seed_order(db: Session, *, suffix: str, completed: bool = True) -> tuple[Order, User, Event]:
    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    buyer = User(email=f"buyer-{suffix}@example.com", full_name="Buyer")
    organizer_user = User(email=f"org-{suffix}@example.com", full_name="Organizer")
    db.add_all([buyer, organizer_user])
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
        title=f"Notify Event {suffix}",
        slug=f"notify-event-{suffix}",
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
        tier_code=f"GEN-{suffix}",
        price_amount=Decimal("125.00"),
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
        user_id=buyer.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED if completed else OrderStatus.PENDING,
        total_amount=Decimal("250.00"),
        currency="GYD",
        payment_verification_status="verified",
    )
    db.add(order)
    db.flush()

    db.add(OrderItem(order_id=order.id, ticket_tier_id=tier.id, quantity=2, unit_price=Decimal("125.00")))
    db.commit()
    db.refresh(order)
    db.refresh(buyer)
    db.refresh(event)
    return order, buyer, event


def test_complete_paid_order_triggers_notification_hooks(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    order, _, _ = _seed_order(db_session, suffix="complete", completed=False)
    called = {"completed": 0, "issued": 0}
    monkeypatch.setattr("app.services.orders.notify_order_completed", lambda db, order: called.__setitem__("completed", 1))
    monkeypatch.setattr("app.services.orders.notify_tickets_issued", lambda db, order, tickets: called.__setitem__("issued", len(tickets)))

    complete_paid_order(db_session, order)
    assert called == {"completed": 1, "issued": 2}


def test_ticket_transfer_triggers_notification(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    order, buyer, _ = _seed_order(db_session, suffix="transfer")
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    recipient = User(email="recipient-notify@example.com", full_name="Recipient")
    db_session.add(recipient)
    db_session.commit()
    db_session.refresh(recipient)

    called = {"count": 0}
    monkeypatch.setattr(
        "app.services.tickets.notify_ticket_transferred",
        lambda db, t, from_user_id, to_user_id: called.__setitem__("count", called["count"] + 1),
    )

    transfer_ticket_to_user(db_session, ticket_id=ticket.id, from_user_id=buyer.id, to_user_id=recipient.id)
    assert called["count"] == 1


def test_refund_and_event_cancel_paths_trigger_orchestration(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    order, _, event = _seed_order(db_session, suffix="refund")
    issue_tickets_for_completed_order(db_session, order)

    called = {"refund": 0, "event_cancel": 0}
    monkeypatch.setattr("app.services.orders.notify_order_refunded", lambda db, o, actor_user_id: called.__setitem__("refund", 1))
    monkeypatch.setattr("app.services.events.notify_event_cancelled", lambda db, e, actor_user_id: called.__setitem__("event_cancel", 1))

    refund_completed_order(db_session, order_id=order.id, actor_user_id=event.organizer.user_id, reason="test")
    _, _, event2 = _seed_order(db_session, suffix="cancel")
    cancel_event(db_session, event_id=event2.id, actor_user_id=event2.organizer.user_id, reason="cancel")

    assert called == {"refund": 1, "event_cancel": 1}


def test_email_channel_enabled_and_disabled(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    order, _, _ = _seed_order(db_session, suffix="email")
    monkeypatch.setattr("app.services.notifications.settings.email_notifications_enabled", True)
    monkeypatch.setattr("app.services.notifications.settings.email_provider", "mock")
    assert notify_order_completed(db_session, order).channel_results["email"] == "sent_mock"

    monkeypatch.setattr("app.services.notifications.settings.email_notifications_enabled", False)
    assert notify_order_completed(db_session, order).channel_results["email"] == "skipped_disabled"


def test_resend_endpoints_authorization(db_session: Session) -> None:
    order, buyer, _ = _seed_order(db_session, suffix="resend-auth")
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    assert resend_order_confirmation_notification(order.id, db=db_session, user_id=buyer.id).success is True

    with pytest.raises(HTTPException) as forbidden_order:
        resend_order_confirmation_notification(order.id, db=db_session, user_id=999)
    assert forbidden_order.value.status_code == 403

    assert resend_ticket(ticket.id, db=db_session, user_id=ticket.owner_user_id).success is True

    with pytest.raises(HTTPException) as forbidden_ticket:
        resend_ticket(ticket.id, db=db_session, user_id=999)
    assert forbidden_ticket.value.status_code == 403


def test_resend_does_not_change_business_state(db_session: Session) -> None:
    order, buyer, _ = _seed_order(db_session, suffix="resend-state")
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    before_status = order.status
    before_ticket_status = ticket.status

    resend_order_confirmation_notification(order.id, db=db_session, user_id=buyer.id)

    db_session.refresh(order)
    db_session.refresh(ticket)
    assert order.status == before_status
    assert ticket.status == before_ticket_status


def test_notification_provider_failure_soft_fails(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    order, _, _ = _seed_order(db_session, suffix="soft-fail")
    monkeypatch.setattr("app.services.notifications.settings.email_notifications_enabled", True)
    monkeypatch.setattr("app.services.notifications.settings.email_provider", "mock")
    monkeypatch.setattr("app.services.notifications._send_email", lambda msg: (_ for _ in ()).throw(RuntimeError("boom")))

    result = notify_order_completed(db_session, order)
    assert result.success is False
    assert result.channel_results["email"] == "failed"


def test_notification_channel_routing_policy_excludes_sms() -> None:
    assert get_notification_channels(NotificationEventType.ORDER_COMPLETED) == (
        NotificationChannel.EMAIL,
        NotificationChannel.PUSH,
    )
    assert get_notification_channels(NotificationEventType.REFUND_PROCESSED) == (
        NotificationChannel.EMAIL,
        NotificationChannel.PUSH,
    )
    assert get_notification_channels(NotificationEventType.EVENT_CANCELLED) == (
        NotificationChannel.EMAIL,
        NotificationChannel.PUSH,
    )
    assert get_notification_channels(NotificationEventType.DISPUTE_RESOLVED) == (
        NotificationChannel.EMAIL,
        NotificationChannel.PUSH,
    )
    assert get_notification_channels(NotificationEventType.EVENT_REMINDER) == (NotificationChannel.PUSH,)
    assert get_notification_channels(NotificationEventType.TICKET_TRANSFER_RECEIVED) == (NotificationChannel.PUSH,)
    assert get_notification_channels(NotificationEventType.TICKET_TRANSFER_ACCEPTED) == (NotificationChannel.PUSH,)
    assert "sms" not in {channel.value for event in NotificationEventType for channel in get_notification_channels(event)}


def test_event_reminder_routes_push_only_and_graceful_without_tokens(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    order, buyer, event = _seed_order(db_session, suffix="reminder-routing")
    issue_tickets_for_completed_order(db_session, order)

    sent = {"email": 0, "push": 0}
    monkeypatch.setattr("app.services.notifications.settings.email_notifications_enabled", True)
    monkeypatch.setattr("app.services.notifications.settings.email_provider", "mock")
    monkeypatch.setattr("app.services.notifications.settings.push_notifications_enabled", True)
    monkeypatch.setattr("app.services.notifications.settings.push_provider", "mock")
    monkeypatch.setattr(
        "app.services.notifications._send_email",
        lambda message: sent.__setitem__("email", sent["email"] + 1),
    )
    original_send_push = notification_service._send_push

    def _wrapped_send_push(db, message):
        sent["push"] += 1
        return original_send_push(db, message)

    monkeypatch.setattr("app.services.notifications._send_push", _wrapped_send_push)
    result = notify_event_reminder(
        db_session,
        event=event,
        user=buyer,
        reminder_type=ReminderType.HOURS_24_BEFORE,
        ticket_count=2,
    )
    assert result.success is True
    assert result.channel_results["push"] == "skipped_no_tokens"
    assert sent == {"email": 0, "push": 1}


def test_ticket_issue_email_includes_ticket_specific_qr_links(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    order, _, _ = _seed_order(db_session, suffix="qr-email")
    tickets = issue_tickets_for_completed_order(db_session, order)

    monkeypatch.setattr("app.services.notifications.settings.email_notifications_enabled", True)
    monkeypatch.setattr("app.services.notifications.settings.email_provider", "mock")

    captured: dict[str, str] = {}

    def _capture_email(message):
        captured["subject"] = message.subject
        captured["body"] = message.body
        return "sent_mock"

    monkeypatch.setattr("app.services.notifications._send_email", _capture_email)

    result = notify_tickets_issued(db_session, order, tickets)
    assert result.channel_results["email"] == "sent_mock"
    assert "Ticket access links" in captured["body"]
    for ticket in tickets:
        assert f"/t/{ticket.qr_payload}" in captured["body"]
