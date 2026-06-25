import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.orders import _started_event_confirmation_detail, create_order_from_selection, complete_dev_test_checkout
from app.core.config import settings
from app.main import app
from app.models import Event, OrganizerProfile, TicketTier, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus
from app.schemas.order import CreateOrderFromSelectionRequest, TicketSelectionItemRequest
from tests.utils import unique_email


def test_dev_test_checkout_route_registered() -> None:
    route_paths = {route.path for route in app.routes}

    assert "/orders/{order_id}/payments/dev-test/complete" in route_paths


def test_dev_test_checkout_route_is_post_and_defaults_to_http_200() -> None:
    target_route = next(route for route in app.routes if route.path == "/orders/{order_id}/payments/dev-test/complete")

    assert "POST" in target_route.methods
    assert target_route.status_code is None


def test_dev_test_checkout_handler_returns_payload_when_enabled(monkeypatch) -> None:
    previous_enabled = settings.enable_dev_test_checkout
    previous_env = settings.env

    settings.enable_dev_test_checkout = True
    settings.env = "development"

    def _fake_complete_checkout(db, *, order_id: int, user_id: int):
        assert order_id == 77
        assert user_id == 123
        return SimpleNamespace(
            order_id=order_id,
            order_reference="ORD-77",
            provider="dev_test",
            payment_method="dev_test",
            payment_reference="pay-ref-77",
            status="completed",
            payment_verification_status="verified",
            message="Dev test checkout completed.",
        )

    monkeypatch.setattr("app.api.orders.apply_rate_limit", lambda **_: None)
    monkeypatch.setattr("app.api.orders.complete_dev_test_checkout_for_order", _fake_complete_checkout)

    class _FakeDb:
        def __init__(self) -> None:
            self.commit_calls = 0

        def commit(self) -> None:
            self.commit_calls += 1

    db = _FakeDb()

    try:
        response = complete_dev_test_checkout(
            order_id=77,
            db=db,
            current_user=SimpleNamespace(id=123),
            client_ip="127.0.0.1",
        )
    finally:
        settings.enable_dev_test_checkout = previous_enabled
        settings.env = previous_env

    assert db.commit_calls == 1
    assert response.order_id == 77
    assert response.provider == "dev_test"
    assert response.payment_reference == "pay-ref-77"


def test_dev_test_checkout_handler_commits_after_success(monkeypatch) -> None:
    previous_enabled = settings.enable_dev_test_checkout
    previous_env = settings.env

    settings.enable_dev_test_checkout = True
    settings.env = "development"

    class _FakeDb:
        def __init__(self) -> None:
            self.commit_calls = 0

        def commit(self) -> None:
            self.commit_calls += 1

    def _fake_complete_checkout(db, *, order_id: int, user_id: int):
        assert order_id == 88
        assert user_id == 456
        return SimpleNamespace(
            order_id=order_id,
            order_reference="ORD-88",
            provider="dev_test",
            payment_method="dev_test",
            payment_reference="pay-ref-88",
            status="completed",
            payment_verification_status="verified",
            message="Dev test checkout completed.",
        )

    monkeypatch.setattr("app.api.orders.apply_rate_limit", lambda **_: None)
    monkeypatch.setattr("app.api.orders.complete_dev_test_checkout_for_order", _fake_complete_checkout)
    db = _FakeDb()

    try:
        complete_dev_test_checkout(
            order_id=88,
            db=db,
            current_user=SimpleNamespace(id=456),
            client_ip="127.0.0.1",
        )
    finally:
        settings.enable_dev_test_checkout = previous_enabled
        settings.env = previous_env

    assert db.commit_calls == 1


def test_dev_test_checkout_handler_returns_403_when_disabled(monkeypatch) -> None:
    previous_enabled = settings.enable_dev_test_checkout
    settings.enable_dev_test_checkout = False
    monkeypatch.setattr("app.api.orders.apply_rate_limit", lambda **_: None)

    try:
        with pytest.raises(HTTPException) as exc:
            complete_dev_test_checkout(
                order_id=77,
                db=object(),
                current_user=SimpleNamespace(id=123),
                client_ip="127.0.0.1",
            )
    finally:
        settings.enable_dev_test_checkout = previous_enabled

    assert exc.value.status_code == 403
    assert exc.value.detail == "Dev test checkout is disabled."


def test_started_event_confirmation_detail_contains_stable_code_and_time_remaining() -> None:
    now = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)
    event = Event(
        id=42,
        organizer_id=1,
        venue_id=1,
        title="Late Show",
        slug="late-show",
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=2, minutes=30),
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        approval_status=EventApprovalStatus.APPROVED,
        timezone="America/Guyana",
        is_location_pinned=False,
    )

    detail = _started_event_confirmation_detail(event, now)

    assert detail["code"] == "EVENT_ALREADY_STARTED_CONFIRMATION_REQUIRED"
    assert detail["event_id"] == 42
    assert detail["event_title"] == "Late Show"
    assert detail["seconds_until_event_end"] == 9000
    assert detail["human_readable_time_remaining"] == "2 hours and 30 minutes"
    assert "This event has already started" in detail["message"]


def _seed_orderable_event(
    db,
    *,
    start_at: datetime,
    end_at: datetime,
    status: EventStatus = EventStatus.PUBLISHED,
    approval_status: EventApprovalStatus = EventApprovalStatus.APPROVED,
) -> tuple[User, Event, TicketTier]:
    owner = User(email=unique_email("order-api-owner"), full_name="Owner")
    buyer = User(email=unique_email("order-api-buyer"), full_name="Buyer")
    db.add_all([owner, buyer])
    db.flush()

    organizer = OrganizerProfile(user_id=owner.id, business_name="Biz", display_name="Biz")
    db.add(organizer)
    db.flush()

    venue = Venue(organizer_id=organizer.id, name="Venue")
    db.add(venue)
    db.flush()

    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title="Concert",
        slug=f"order-api-{unique_email('event').replace('@', '-')}",
        start_at=start_at,
        end_at=end_at,
        status=status,
        visibility=EventVisibility.PUBLIC,
        approval_status=approval_status,
        timezone="America/Guyana",
        is_location_pinned=False,
    )
    db.add(event)
    db.flush()

    tier = TicketTier(
        event_id=event.id,
        name="General",
        tier_code="GENERAL",
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
    db.commit()
    db.refresh(buyer)
    db.refresh(event)
    db.refresh(tier)
    return buyer, event, tier


def _selection_payload(event_id: int, tier_id: int, *, acknowledge_started_event: bool = False) -> CreateOrderFromSelectionRequest:
    return CreateOrderFromSelectionRequest(
        event_id=event_id,
        items=[TicketSelectionItemRequest(ticket_tier_id=tier_id, quantity=1)],
        acknowledge_started_event=acknowledge_started_event,
    )


def test_future_event_order_creation_still_works(db_session, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    buyer, event, tier = _seed_orderable_event(
        db_session,
        start_at=now + timedelta(days=2),
        end_at=now + timedelta(days=2, hours=4),
    )
    monkeypatch.setattr("app.api.orders.apply_rate_limit", lambda **_: None)

    response = create_order_from_selection(
        payload=_selection_payload(event.id, tier.id),
        db=db_session,
        current_user=buyer,
        client_ip="127.0.0.1",
    )

    assert response.event_id == event.id
    assert response.status == OrderStatus.AWAITING_PAYMENT.value
    assert len(response.items) == 1


def test_started_event_without_acknowledgement_returns_409_confirmation(db_session, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    buyer, event, tier = _seed_orderable_event(
        db_session,
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=3),
    )
    monkeypatch.setattr("app.api.orders.apply_rate_limit", lambda **_: None)

    with pytest.raises(HTTPException) as exc:
        create_order_from_selection(
            payload=_selection_payload(event.id, tier.id),
            db=db_session,
            current_user=buyer,
            client_ip="127.0.0.1",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "EVENT_ALREADY_STARTED_CONFIRMATION_REQUIRED"
    assert exc.value.detail["event_id"] == event.id
    assert exc.value.detail["seconds_until_event_end"] > 0
    assert "human_readable_time_remaining" in exc.value.detail


def test_started_event_with_acknowledgement_creates_order_and_hold(db_session, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    buyer, event, tier = _seed_orderable_event(
        db_session,
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=3),
    )
    monkeypatch.setattr("app.api.orders.apply_rate_limit", lambda **_: None)

    response = create_order_from_selection(
        payload=_selection_payload(event.id, tier.id, acknowledge_started_event=True),
        db=db_session,
        current_user=buyer,
        client_ip="127.0.0.1",
    )

    assert response.event_id == event.id
    assert response.status == OrderStatus.AWAITING_PAYMENT.value
    assert len(response.items) == 1


def test_ended_event_returns_409_event_ended(db_session, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    buyer, event, tier = _seed_orderable_event(
        db_session,
        start_at=now - timedelta(hours=5),
        end_at=now - timedelta(minutes=1),
    )
    monkeypatch.setattr("app.api.orders.apply_rate_limit", lambda **_: None)

    with pytest.raises(HTTPException) as exc:
        create_order_from_selection(
            payload=_selection_payload(event.id, tier.id, acknowledge_started_event=True),
            db=db_session,
            current_user=buyer,
            client_ip="127.0.0.1",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "EVENT_ENDED"
    assert exc.value.detail["message"] == "This event has ended and tickets are no longer available."
    assert exc.value.detail["event_id"] == event.id


def test_cancelled_started_event_returns_controlled_rejection_not_confirmation(db_session, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    buyer, event, tier = _seed_orderable_event(
        db_session,
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=3),
        status=EventStatus.CANCELLED,
    )
    monkeypatch.setattr("app.api.orders.apply_rate_limit", lambda **_: None)

    with pytest.raises(HTTPException) as exc:
        create_order_from_selection(
            payload=_selection_payload(event.id, tier.id),
            db=db_session,
            current_user=buyer,
            client_ip="127.0.0.1",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "EVENT_NOT_SELLABLE"
    assert exc.value.detail["code"] != "EVENT_ALREADY_STARTED_CONFIRMATION_REQUIRED"


def test_cancelled_at_started_event_returns_controlled_rejection_not_confirmation(db_session, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    buyer, event, tier = _seed_orderable_event(
        db_session,
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=3),
    )
    event.cancelled_at = now - timedelta(minutes=10)
    db_session.commit()
    monkeypatch.setattr("app.api.orders.apply_rate_limit", lambda **_: None)

    with pytest.raises(HTTPException) as exc:
        create_order_from_selection(
            payload=_selection_payload(event.id, tier.id),
            db=db_session,
            current_user=buyer,
            client_ip="127.0.0.1",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "EVENT_NOT_SELLABLE"
    assert exc.value.detail["code"] != "EVENT_ALREADY_STARTED_CONFIRMATION_REQUIRED"
