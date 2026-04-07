import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Event, Order, OrganizerProfile, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus
from app.services.integrations import (
    DELIVERY_KIND_MANUAL_REDELIVERY,
    SCOPE_READ,
    SCOPE_WRITE,
    authenticate_api_key,
    build_order_paid_payload,
    build_refund_payload,
    build_transfer_payload,
    create_api_key,
    create_webhook_endpoint,
    dispatch_pending_webhook_deliveries,
    list_deliveries,
    publish_webhook_event,
    redeliver_webhook_delivery,
    require_scope,
    revoke_api_key,
    verify_webhook_signature,
)


def _db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    return SessionLocal()


def _seed_admin(db: Session, *, email: str = "admin@x.com") -> User:
    admin = User(email=email, full_name="Admin", is_admin=True)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def _seed_order(db: Session, *, admin: User) -> Order:
    organizer = OrganizerProfile(user_id=admin.id, business_name="Biz", display_name="Biz")
    db.add(organizer)
    db.flush()
    venue = Venue(organizer_id=organizer.id, name="Hall")
    db.add(venue)
    db.flush()
    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title="Event",
        slug=f"event-{admin.id}",
        start_at=datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 4, 7, 11, 0, tzinfo=timezone.utc),
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        approval_status=EventApprovalStatus.APPROVED,
        timezone="America/Guyana",
        is_location_pinned=False,
    )
    db.add(event)
    db.flush()
    order = Order(user_id=admin.id, event_id=event.id, status=OrderStatus.COMPLETED, total_amount=Decimal("10.00"), currency="USD")
    db.add(order)
    db.flush()
    return order


def test_api_key_create_auth_scope_and_revoke() -> None:
    db = _db()
    admin = _seed_admin(db)
    key, raw = create_api_key(db, user_id=admin.id, name="Main", scopes=[SCOPE_READ, SCOPE_WRITE, "bad:scope"])
    db.commit()

    assert "bad:scope" not in key.scopes_csv
    authed = authenticate_api_key(db, raw_key=raw)
    assert authed is not None
    assert authed.last_used_at is not None
    assert require_scope(authed, SCOPE_READ)
    assert require_scope(authed, SCOPE_WRITE)

    revoke_api_key(db, key_id=key.id, user_id=admin.id)
    db.commit()
    assert authenticate_api_key(db, raw_key=raw) is None


def test_webhook_signature_contract() -> None:
    timestamp = "1712500000"
    body = '{"id":"evt_1"}'
    secret = "whsec_test"
    import hashlib, hmac

    digest = hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()
    assert verify_webhook_signature(secret=secret, timestamp=timestamp, body=body, signature_header=f"v1={digest}")


def test_webhook_delivery_retry_and_success_audit() -> None:
    db = _db()
    admin = _seed_admin(db)
    create_webhook_endpoint(
        db,
        user_id=admin.id,
        name="Main endpoint",
        target_url="https://example.com/webhook",
        subscribed_events=["order.paid"],
    )
    publish_webhook_event(db, event_type="order.paid", payload={"order_id": 1})
    db.commit()

    calls = {"count": 0}

    def flaky(*, endpoint, body):
        calls["count"] += 1
        if calls["count"] == 1:
            return type("Res", (), {"ok": False, "status_code": 500, "error": "boom"})
        return type("Res", (), {"ok": True, "status_code": 200, "error": None})

    assert dispatch_pending_webhook_deliveries(db, transport=flaky) == 1
    db.commit()
    assert dispatch_pending_webhook_deliveries(db, transport=flaky) == 0

    deliveries = list_deliveries(db, user_id=admin.id)
    retry = next(item.delivery for item in deliveries if item.delivery.attempt_number == 2)
    retry.next_retry_at = retry.requested_at
    db.commit()

    assert dispatch_pending_webhook_deliveries(db, transport=flaky) == 1
    db.commit()
    final = list_deliveries(db, user_id=admin.id)
    assert any(item.delivery.status == "delivered" for item in final)
    assert any(item.delivery.delivery_kind == "automatic_retry" for item in final)


def test_manual_redelivery_creates_new_attempt_with_same_event_id() -> None:
    db = _db()
    admin = _seed_admin(db)
    create_webhook_endpoint(
        db,
        user_id=admin.id,
        name="Main endpoint",
        target_url="https://example.com/webhook",
        subscribed_events=["order.paid"],
    )
    publish_webhook_event(db, event_type="order.paid", payload={"order_id": 1})
    db.commit()

    first = list_deliveries(db, user_id=admin.id)[0].delivery
    replay = redeliver_webhook_delivery(db, delivery_id=first.id, user_id=admin.id)
    db.commit()

    assert replay is not None
    assert replay.event_id == first.event_id
    assert replay.payload_json == first.payload_json
    assert replay.attempt_number == first.attempt_number + 1
    assert replay.delivery_kind == DELIVERY_KIND_MANUAL_REDELIVERY


def test_manual_redelivery_requires_owner_boundary() -> None:
    db = _db()
    admin = _seed_admin(db)
    other = _seed_admin(db, email="other@x.com")
    create_webhook_endpoint(
        db,
        user_id=admin.id,
        name="Main endpoint",
        target_url="https://example.com/webhook",
        subscribed_events=["order.paid"],
    )
    publish_webhook_event(db, event_type="order.paid", payload={"order_id": 1})
    db.commit()

    first = list_deliveries(db, user_id=admin.id)[0].delivery
    denied = redeliver_webhook_delivery(db, delivery_id=first.id, user_id=other.id)
    assert denied is None


def test_event_schema_stability_for_order_and_refund_examples() -> None:
    db = _db()
    admin = _seed_admin(db)
    order = _seed_order(db, admin=admin)

    create_webhook_endpoint(db, user_id=admin.id, name="E", target_url="https://example.com", subscribed_events=["order.paid", "order.refunded"])
    publish_webhook_event(db, event_type="order.paid", payload=build_order_paid_payload(order))
    publish_webhook_event(db, event_type="order.refunded", payload=build_refund_payload(order, refund_id=9, amount=2.5))
    db.commit()

    payloads = [json.loads(item.delivery.payload_json) for item in list_deliveries(db, user_id=admin.id)]
    for envelope in payloads:
        assert set(envelope.keys()) == {"id", "type", "version", "created_at", "data"}
        assert envelope["id"].startswith("evt_")
        assert envelope["version"] == "v1"
        assert envelope["created_at"]


def test_delivery_history_exposes_diagnostics_fields() -> None:
    db = _db()
    admin = _seed_admin(db)
    create_webhook_endpoint(
        db,
        user_id=admin.id,
        name="Main endpoint",
        target_url="https://example.com/webhook",
        subscribed_events=["order.paid"],
    )
    publish_webhook_event(db, event_type="order.paid", payload={"order_id": 1})
    db.commit()

    rows = list_deliveries(db, user_id=admin.id)
    assert rows[0].endpoint_url == "https://example.com/webhook"
    assert rows[0].delivery.event_type == "order.paid"
    assert rows[0].delivery.event_id.startswith("evt_")
    assert rows[0].delivery.status in {"pending", "retry_scheduled", "delivered", "failed"}


def test_example_fixture_contract_matches_required_envelope_shape() -> None:
    fixture = Path(__file__).with_name("fixtures").joinpath("webhook_envelope_examples.json")
    data = json.loads(fixture.read_text())
    assert {"order.paid", "order.refunded", "transfer.accepted", "checkin.completed"}.issubset(set(data.keys()))

    for event_type, envelope in data.items():
        assert envelope["type"] == event_type
        assert set(envelope.keys()) == {"id", "type", "version", "created_at", "data"}
        assert envelope["version"] == "v1"
        assert envelope["id"].startswith("evt_")
        assert isinstance(envelope["data"], dict)


def test_transfer_payload_keys_stable() -> None:
    class Invite:
        id = 1

    class TicketRecord:
        id = 2
        event_id = 3
        owner_user_id = 4

    payload = build_transfer_payload(Invite(), TicketRecord())
    assert set(payload.keys()) == {"invite_id", "ticket_id", "event_id", "to_user_id"}
