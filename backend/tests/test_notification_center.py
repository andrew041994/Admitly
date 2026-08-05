from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models import (
    Event,
    NotificationPreference,
    OrganizerProfile,
    PushDispatch,
    PushToken,
    User,
    UserNotification,
)
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility
from app.services.nearby_notifications import (
    enqueue_nearby_event_job,
    haversine_km,
    process_notification_jobs,
)
from app.services.notification_center import create_user_notification
from app.services.notifications import (
    notify_ticket_transfer_canceled,
    notify_ticket_transfer_invite_accepted,
    notify_ticket_transfer_invite_created,
    notify_ticket_transfer_invite_declined,
)
from app.services.push_delivery import process_expo_receipts, process_push_dispatches
from tests.utils import auth_headers, unique_email


def _user(db: Session, prefix: str) -> User:
    row = User(email=unique_email(prefix), full_name=prefix, is_active=True, is_verified=True)
    db.add(row)
    db.flush()
    return row


def _client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: (yield db)
    return TestClient(app)


def test_notification_api_is_owner_scoped_and_read_operations_are_idempotent(db_session: Session) -> None:
    owner = _user(db_session, "notification-owner")
    other = _user(db_session, "notification-other")
    create_user_notification(
        db_session,
        user_id=owner.id,
        notification_type="ticket_purchase_completed",
        title="Tickets ready",
        body="Your tickets are in the wallet.",
        dedupe_key=f"test:owner:{owner.id}",
        route_key="wallet",
    )
    foreign, _ = create_user_notification(
        db_session,
        user_id=other.id,
        notification_type="ticket_purchase_completed",
        title="Other",
        body="Private notification.",
        dedupe_key=f"test:other:{other.id}",
        route_key="wallet",
    )
    db_session.commit()

    with _client(db_session) as client:
        assert client.get("/me/notifications").status_code == 401
        listed = client.get("/me/notifications", headers=auth_headers(owner))
        assert listed.status_code == 200
        assert [row["title"] for row in listed.json()["items"]] == ["Tickets ready"]
        assert client.get("/me/notifications/unread-count", headers=auth_headers(owner)).json() == {"unread_count": 1}
        assert client.post(f"/me/notifications/{foreign.id}/read", headers=auth_headers(owner)).status_code == 404
        notification_id = listed.json()["items"][0]["id"]
        assert client.post(f"/me/notifications/{notification_id}/read", headers=auth_headers(owner)).status_code == 200
        assert client.post(f"/me/notifications/{notification_id}/read", headers=auth_headers(owner)).status_code == 200
        assert client.post("/me/notifications/read-all", headers=auth_headers(owner)).json()["unread_count"] == 0
    app.dependency_overrides.clear()


def test_notification_creation_deduplicates_and_queues_each_active_device(db_session: Session) -> None:
    user = _user(db_session, "multi-device")
    db_session.add_all([
        PushToken(user_id=user.id, token="ExponentPushToken[test-device-a]", installation_id="installation-a", is_active=True),
        PushToken(user_id=user.id, token="ExponentPushToken[test-device-b]", installation_id="installation-b", is_active=True),
    ])
    db_session.flush()
    first, created = create_user_notification(
        db_session,
        user_id=user.id,
        notification_type="ticket_received",
        title="Transfer awaiting you",
        body="A ticket is awaiting acceptance.",
        dedupe_key="transfer:900:created",
        route_key="transfers",
        route_params={"transfer_id": 900},
    )
    second, repeated = create_user_notification(
        db_session,
        user_id=user.id,
        notification_type="ticket_received",
        title="Transfer awaiting you",
        body="A ticket is awaiting acceptance.",
        dedupe_key="transfer:900:created",
        route_key="transfers",
    )
    assert created is True and repeated is False and first.id == second.id
    assert len(db_session.execute(select(PushDispatch).where(PushDispatch.notification_id == first.id)).scalars().all()) == 2


def test_transfer_lifecycle_notifications_are_recipient_derived_and_deduplicated(db_session: Session) -> None:
    sender = _user(db_session, "transfer-notify-sender")
    recipient = _user(db_session, "transfer-notify-recipient")
    invite = SimpleNamespace(
        id=701,
        ticket_id=801,
        sender_user_id=sender.id,
        recipient_user_id=recipient.id,
        recipient_email=recipient.email,
    )
    ticket = SimpleNamespace(id=801, event_id=901, owner_user_id=recipient.id)
    notify_ticket_transfer_invite_created(db_session, invite)
    notify_ticket_transfer_invite_created(db_session, invite)
    notify_ticket_transfer_invite_accepted(db_session, invite, ticket)
    notify_ticket_transfer_invite_declined(db_session, invite)
    notify_ticket_transfer_canceled(db_session, invite)
    rows = db_session.execute(
        select(UserNotification).where(UserNotification.related_entity_type == "transfer")
    ).scalars().all()
    assert {(row.user_id, row.notification_type) for row in rows} == {
        (recipient.id, "ticket_received"),
        (sender.id, "ticket_transfer_accepted"),
        (sender.id, "ticket_transfer_declined"),
        (recipient.id, "ticket_transfer_canceled"),
    }
    assert len(rows) == 4


def test_push_registration_is_authenticated_deduplicated_and_does_not_echo_token(db_session: Session) -> None:
    user = _user(db_session, "push-api")
    other = _user(db_session, "push-api-other")
    payload = {"token": "ExponentPushToken[secure-test-token]", "platform": "android", "installation_id": "test-installation-123"}
    with _client(db_session) as client:
        assert client.post("/me/push-tokens", json=payload).status_code == 401
        response = client.post("/me/push-tokens", json=payload, headers=auth_headers(user))
        assert response.status_code == 201
        assert response.json() == {"success": True, "device_registered": True}
        assert "token" not in response.json()
        client.post("/me/push-tokens", json=payload, headers=auth_headers(user))
    rows = db_session.execute(select(PushToken).where(PushToken.installation_id == payload["installation_id"])).scalars().all()
    assert len(rows) == 1 and rows[0].user_id == user.id and rows[0].user_id != other.id
    app.dependency_overrides.clear()


def test_push_failure_is_retried_without_removing_in_app_notification(db_session: Session, monkeypatch) -> None:
    user = _user(db_session, "push-failure")
    db_session.add(PushToken(user_id=user.id, token="ExponentPushToken[failure-test]", installation_id="failure-install", is_active=True))
    db_session.flush()
    notification, _ = create_user_notification(
        db_session, user_id=user.id, notification_type="ticket_purchase_completed",
        title="Ready", body="Tickets ready.", dedupe_key="order:999:tickets-issued", route_key="wallet",
    )
    db_session.commit()
    monkeypatch.setattr("app.services.push_delivery.settings.push_notifications_enabled", True)
    monkeypatch.setattr("app.services.push_delivery.settings.push_provider", "expo")
    monkeypatch.setattr("app.services.push_delivery._expo_post", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    summary = process_push_dispatches(db_session)
    assert summary["failed"] == 1
    assert db_session.get(UserNotification, notification.id) is not None
    dispatch = db_session.execute(select(PushDispatch).where(PushDispatch.notification_id == notification.id)).scalar_one()
    assert dispatch.status == "pending" and dispatch.attempts == 1


def test_device_not_registered_receipt_disables_only_the_invalid_token(db_session: Session, monkeypatch) -> None:
    user = _user(db_session, "invalid-device")
    token = PushToken(user_id=user.id, token="ExponentPushToken[invalid-device]", installation_id="invalid-install", is_active=True)
    db_session.add(token)
    db_session.flush()
    notification, _ = create_user_notification(
        db_session, user_id=user.id, notification_type="ticket_received", title="Transfer",
        body="A transfer is waiting.", dedupe_key="transfer:invalid-device", route_key="transfers",
    )
    dispatch = db_session.execute(select(PushDispatch).where(PushDispatch.notification_id == notification.id)).scalar_one()
    dispatch.status = "receipt_pending"
    dispatch.provider_ticket_id = "expo-ticket-invalid"
    dispatch.next_attempt_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    monkeypatch.setattr("app.services.push_delivery.settings.push_notifications_enabled", True)
    monkeypatch.setattr("app.services.push_delivery.settings.push_provider", "expo")
    monkeypatch.setattr("app.services.push_delivery._expo_post", lambda *args, **kwargs: {
        "data": {"expo-ticket-invalid": {"status": "error", "details": {"error": "DeviceNotRegistered"}}}
    })
    summary = process_expo_receipts(db_session)
    db_session.refresh(token)
    assert summary == {"checked": 1, "delivered": 0, "failed": 1}
    assert token.is_active is False and token.disabled_reason == "DeviceNotRegistered"


def test_reminder_push_opt_out_preserves_transactional_in_app_record(db_session: Session) -> None:
    user = _user(db_session, "reminder-opt-out")
    db_session.add_all([
        PushToken(user_id=user.id, token="ExponentPushToken[reminder-opt-out]", installation_id="reminder-opt-install", is_active=True),
        NotificationPreference(user_id=user.id, event_reminders_push_enabled=False),
    ])
    db_session.flush()
    notification, created = create_user_notification(
        db_session, user_id=user.id, notification_type="event_starting_soon",
        title="Starting soon", body="Your event begins in one hour.",
        dedupe_key="event:77:user:88:reminder:1_hour_before", route_key="event", route_params={"event_id": 77},
    )
    assert created is True and notification.push_status == "suppressed"
    assert db_session.execute(select(PushDispatch).where(PushDispatch.notification_id == notification.id)).scalars().all() == []


def _nearby_event(db: Session, organizer_user: User) -> Event:
    organizer = OrganizerProfile(user_id=organizer_user.id, business_name="Nearby Org", display_name="Nearby Org")
    db.add(organizer)
    db.flush()
    event = Event(
        organizer_id=organizer.id, title="Nearby Concert", slug=f"nearby-{organizer_user.id}",
        start_at=datetime.now(timezone.utc) + timedelta(days=2), end_at=datetime.now(timezone.utc) + timedelta(days=2, hours=2),
        status=EventStatus.PUBLISHED, visibility=EventVisibility.PUBLIC, approval_status=EventApprovalStatus.APPROVED,
        published_at=datetime.now(timezone.utc), timezone="America/Guyana", latitude=Decimal("6.8013"), longitude=Decimal("-58.1551"), is_location_pinned=True,
    )
    db.add(event)
    db.flush()
    return event


def test_nearby_event_uses_haversine_opt_in_visibility_and_deduplication(db_session: Session) -> None:
    organizer = _user(db_session, "nearby-organizer")
    inside = _user(db_session, "nearby-inside")
    outside = _user(db_session, "nearby-outside")
    opted_out = _user(db_session, "nearby-opted-out")
    event = _nearby_event(db_session, organizer)
    db_session.add_all([
        NotificationPreference(user_id=inside.id, nearby_events_push_enabled=True, location_discovery_enabled=True, latitude=6.81, longitude=-58.16),
        NotificationPreference(user_id=outside.id, nearby_events_push_enabled=True, location_discovery_enabled=True, latitude=7.30, longitude=-58.16),
        NotificationPreference(user_id=opted_out.id, nearby_events_push_enabled=False, location_discovery_enabled=True, latitude=6.81, longitude=-58.16),
    ])
    boundary_latitude = 6.8013 + (20.0 / 111.195)
    assert 19.99 <= haversine_km(6.8013, -58.1551, boundary_latitude, -58.1551) <= 20.01
    assert haversine_km(6.8013, -58.1551, boundary_latitude + 0.002, -58.1551) > 20.0
    enqueue_nearby_event_job(db_session, event_id=event.id)
    db_session.commit()
    first = process_notification_jobs(db_session)
    second = process_notification_jobs(db_session)
    assert first["notifications_created"] == 1 and second["notifications_created"] == 0
    recipients = set(db_session.execute(select(UserNotification.user_id).where(UserNotification.notification_type == "nearby_event_created")).scalars())
    assert recipients == {inside.id}
