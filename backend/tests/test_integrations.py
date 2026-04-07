import os
from datetime import datetime, timezone
from decimal import Decimal

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.main import app
from app.models import Event, Order, OrganizerProfile, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus
from app.services.integrations import (
    SCOPE_READ,
    SCOPE_WRITE,
    authenticate_api_key,
    build_order_paid_payload,
    create_api_key,
    create_webhook_endpoint,
    dispatch_pending_webhook_deliveries,
    list_deliveries,
    publish_webhook_event,
    require_scope,
    revoke_api_key,
    verify_webhook_signature,
)


def _db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    return SessionLocal()


def _seed_admin(db: Session) -> User:
    admin = User(email="admin@x.com", full_name="Admin", is_admin=True)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def test_api_key_create_auth_scope_and_revoke() -> None:
    db = _db()
    admin = _seed_admin(db)
    key, raw = create_api_key(db, user_id=admin.id, name="Main", scopes=[SCOPE_READ, SCOPE_WRITE])
    db.commit()

    authed = authenticate_api_key(db, raw_key=raw)
    assert authed is not None
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
    endpoint, _ = create_webhook_endpoint(
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

    # force second attempt due now
    deliveries = list_deliveries(db, user_id=admin.id)
    retry = next(item for item in deliveries if item.attempt_number == 2)
    retry.next_retry_at = retry.requested_at
    db.commit()

    assert dispatch_pending_webhook_deliveries(db, transport=flaky) == 1
    db.commit()
    final = list_deliveries(db, user_id=admin.id)
    assert any(item.status == "delivered" for item in final)


def test_api_key_scope_contract() -> None:
    db = _db()
    admin = _seed_admin(db)
    key, raw = create_api_key(db, user_id=admin.id, name="Read", scopes=[SCOPE_READ])
    db.commit()

    principal = authenticate_api_key(db, raw_key=raw)
    assert principal is not None
    assert require_scope(principal, SCOPE_READ)
    assert not require_scope(principal, SCOPE_WRITE)

    revoke_api_key(db, key_id=key.id, user_id=admin.id)
    db.commit()
    assert authenticate_api_key(db, raw_key=raw) is None

def test_event_schema_stability_for_order_paid() -> None:
    db = _db()
    admin = _seed_admin(db)
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
        slug="event",
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
    order = Order(user_id=admin.id, event_id=event.id, status=OrderStatus.COMPLETED, total_amount=Decimal("10.00"), currency="GYD")
    db.add(order)
    db.flush()

    create_webhook_endpoint(db, user_id=admin.id, name="E", target_url="https://example.com", subscribed_events=["order.paid"])
    publish_webhook_event(db, event_type="order.paid", payload=build_order_paid_payload(order))
    db.commit()

    delivery = list_deliveries(db, user_id=admin.id)[0]
    assert '"type": "order.paid"' in delivery.payload_json
    assert '"version": "v1"' in delivery.payload_json
    assert '"id": "evt_' in delivery.payload_json
