from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Event, EventReminderLog, OrganizerProfile, Order, OrderItem, Ticket, TicketTier, User, Venue
from app.models.enums import (
    EventApprovalStatus,
    EventStatus,
    EventVisibility,
    OrderStatus,
    ReminderType,
    TicketStatus,
)
from app.services.reminders import (
    dispatch_due_event_reminders,
    get_eligible_event_reminder_recipients,
    get_reminder_due_times_for_event,
    should_send_reminder_for_event,
)
from app.services.tickets import issue_tickets_for_completed_order, transfer_ticket_to_user


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


def _seed_order(db: Session, *, suffix: str, event_start_at: datetime) -> tuple[Order, User, Event]:
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
        title=f"Reminder Event {suffix}",
        slug=f"reminder-event-{suffix}",
        start_at=event_start_at,
        end_at=event_start_at + timedelta(hours=2),
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
        status=OrderStatus.COMPLETED,
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


def test_should_send_window_logic() -> None:
    now = datetime(2026, 4, 6, 13, 0, tzinfo=timezone.utc)
    event_24 = Event(start_at=now + timedelta(hours=24), end_at=now + timedelta(hours=25), organizer_id=1, venue_id=None,
                     title="E1", slug="e1", status=EventStatus.PUBLISHED, visibility=EventVisibility.PUBLIC,
                     approval_status=EventApprovalStatus.APPROVED, timezone="America/Guyana", is_location_pinned=False)
    event_today = Event(start_at=now + timedelta(minutes=5), end_at=now + timedelta(hours=1), organizer_id=1, venue_id=None,
                    title="E2", slug="e2", status=EventStatus.PUBLISHED, visibility=EventVisibility.PUBLIC,
                     approval_status=EventApprovalStatus.APPROVED, timezone="America/Guyana", is_location_pinned=False)
    event_30 = Event(start_at=now + timedelta(minutes=30), end_at=now + timedelta(hours=1), organizer_id=1, venue_id=None,
                     title="E3", slug="e3", status=EventStatus.PUBLISHED, visibility=EventVisibility.PUBLIC,
                     approval_status=EventApprovalStatus.APPROVED, timezone="America/Guyana", is_location_pinned=False)
    outside = Event(start_at=now + timedelta(hours=10), end_at=now + timedelta(hours=11), organizer_id=1, venue_id=None,
                    title="E4", slug="e4", status=EventStatus.PUBLISHED, visibility=EventVisibility.PUBLIC,
                    approval_status=EventApprovalStatus.APPROVED, timezone="America/Guyana", is_location_pinned=False)

    assert should_send_reminder_for_event(event_24, ReminderType.HOURS_24_BEFORE, now=now)
    assert should_send_reminder_for_event(event_today, ReminderType.HOURS_3_BEFORE, now=now)
    assert should_send_reminder_for_event(event_30, ReminderType.MINUTES_30_BEFORE, now=now)
    assert not should_send_reminder_for_event(outside, ReminderType.HOURS_24_BEFORE, now=now)


def test_today_reminder_due_time_uses_event_timezone_local_morning() -> None:
    event = Event(
        start_at=datetime(2026, 4, 7, 14, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 4, 7, 16, 0, tzinfo=timezone.utc),
        organizer_id=1,
        venue_id=None,
        title="Timezone Event",
        slug="tz-event",
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        approval_status=EventApprovalStatus.APPROVED,
        timezone="America/Guyana",
        is_location_pinned=False,
    )
    due_times = get_reminder_due_times_for_event(event)
    assert due_times[ReminderType.HOURS_3_BEFORE] == datetime(2026, 4, 7, 13, 0, tzinfo=timezone.utc)


def test_recipients_use_current_owner_after_transfer(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    order, buyer, event = _seed_order(db_session, suffix="transfer-owner", event_start_at=now + timedelta(hours=24, minutes=5))
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    recipient = User(email="recipient-reminder@example.com", full_name="Recipient")
    db_session.add(recipient)
    db_session.commit()
    db_session.refresh(recipient)

    transfer_ticket_to_user(db_session, ticket_id=ticket.id, from_user_id=buyer.id, to_user_id=recipient.id)

    recipients = get_eligible_event_reminder_recipients(
        db_session,
        event_id=event.id,
        reminder_type=ReminderType.HOURS_24_BEFORE,
        now=now,
    )
    user_ids = {user.id for user, _ in recipients}
    assert recipient.id in user_ids


def test_recipient_eligibility_and_grouping(db_session: Session) -> None:
    now = datetime(2026, 4, 6, 13, 0, tzinfo=timezone.utc)
    order, buyer, event = _seed_order(db_session, suffix="eligible", event_start_at=now + timedelta(minutes=5))
    tickets = issue_tickets_for_completed_order(db_session, order)

    tickets[0].status = TicketStatus.CHECKED_IN
    tickets[0].checked_in_at = now
    db_session.flush()

    recipients = get_eligible_event_reminder_recipients(
        db_session,
        event_id=event.id,
        reminder_type=ReminderType.HOURS_3_BEFORE,
        now=now,
    )
    assert recipients == [(buyer, 1)]

    tickets[1].status = TicketStatus.VOIDED
    db_session.flush()
    recipients = get_eligible_event_reminder_recipients(
        db_session,
        event_id=event.id,
        reminder_type=ReminderType.HOURS_3_BEFORE,
        now=now,
    )
    assert recipients == []

    event.status = EventStatus.CANCELLED
    db_session.flush()
    recipients = get_eligible_event_reminder_recipients(
        db_session,
        event_id=event.id,
        reminder_type=ReminderType.HOURS_3_BEFORE,
        now=now,
    )
    assert recipients == []


def test_dispatch_dedup_and_repeat_runs(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    order, buyer, event = _seed_order(db_session, suffix="dedup", event_start_at=now + timedelta(minutes=35))
    issue_tickets_for_completed_order(db_session, order)

    calls: list[tuple[int, int, str]] = []

    def _fake_notify(db, *, event, user, reminder_type, ticket_count):
        calls.append((event.id, user.id, reminder_type.value))
        from app.services.notifications import NotificationDispatchResult

        return NotificationDispatchResult(success=True, channel_results={"email": "sent_mock", "push": "sent_mock:1"})

    monkeypatch.setattr("app.services.reminders.notify_event_reminder", _fake_notify)

    summary1 = dispatch_due_event_reminders(db_session, now=now)
    db_session.commit()
    summary2 = dispatch_due_event_reminders(db_session, now=now)

    assert summary1.reminders_sent == 1
    assert summary2.reminders_sent == 0
    assert len(calls) == 1

    logs = db_session.execute(
        select(EventReminderLog).where(
            EventReminderLog.event_id == event.id,
            EventReminderLog.user_id == buyer.id,
            EventReminderLog.reminder_type == ReminderType.MINUTES_30_BEFORE,
        )
    ).scalars().all()
    assert len(logs) == 1


def test_dispatch_uses_email_and_push_paths(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    order, _, _ = _seed_order(db_session, suffix="channels", event_start_at=now + timedelta(hours=24, minutes=1))
    issue_tickets_for_completed_order(db_session, order)

    monkeypatch.setattr("app.services.notifications.settings.email_notifications_enabled", True)
    monkeypatch.setattr("app.services.notifications.settings.email_provider", "mock")
    monkeypatch.setattr("app.services.notifications.settings.push_notifications_enabled", True)
    monkeypatch.setattr("app.services.notifications.settings.push_provider", "mock")

    sent = {"email": 0, "push": 0}

    def _email(message):
        sent["email"] += 1
        return "sent_mock"

    def _push(db, message):
        sent["push"] += 1
        return "sent_mock:1"

    monkeypatch.setattr("app.services.notifications._send_email", _email)
    monkeypatch.setattr("app.services.notifications._send_push", _push)

    dispatch_due_event_reminders(db_session, now=now)

    assert sent["email"] == 0
    assert sent["push"] == 1


def test_reminder_dispatch_does_not_mutate_ticket_state(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    order, _, _ = _seed_order(db_session, suffix="no-mutate", event_start_at=now + timedelta(hours=3, minutes=1))
    tickets = issue_tickets_for_completed_order(db_session, order)
    before = [(t.id, t.owner_user_id, t.status) for t in tickets]

    monkeypatch.setattr("app.services.notifications.settings.email_notifications_enabled", False)
    monkeypatch.setattr("app.services.notifications.settings.push_notifications_enabled", False)

    dispatch_due_event_reminders(db_session, now=now)

    for ticket_id, owner_id, status in before:
        ticket = db_session.execute(select(Ticket).where(Ticket.id == ticket_id)).scalar_one()
        assert ticket.owner_user_id == owner_id
        assert ticket.status == status
