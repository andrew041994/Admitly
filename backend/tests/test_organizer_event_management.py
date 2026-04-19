from datetime import datetime, timedelta, timezone

UTC = timezone.utc
import os

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus
from app.models.event import Event
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.organizer_profile import OrganizerProfile
from app.models.ticket_tier import TicketTier
from app.models.user import User
from app.models.venue import Venue
from tests.utils import unique_email



@pytest.fixture
def client(db_session: Session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_user(db: Session, email: str, name: str) -> User:
    user = User(email=email, full_name=name)
    db.add(user)
    db.flush()
    return user


def _seed_event(
    db: Session,
    organizer_user: User,
    *,
    title: str,
    status: EventStatus = EventStatus.DRAFT,
    approval_status: EventApprovalStatus = EventApprovalStatus.APPROVED,
) -> Event:
    organizer = db.query(OrganizerProfile).filter(OrganizerProfile.user_id == organizer_user.id).one_or_none()
    if organizer is None:
        organizer = OrganizerProfile(user_id=organizer_user.id, business_name=organizer_user.full_name, display_name=organizer_user.full_name)
        db.add(organizer)
        db.flush()
    venue = Venue(organizer_id=organizer.id, name="National Park", city="Georgetown", country="GY")
    db.add(venue)
    db.flush()
    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title=title,
        slug=f"{title.lower().replace(' ', '-')}-{organizer_user.id}",
        start_at=datetime.now(UTC) + timedelta(days=3),
        end_at=datetime.now(UTC) + timedelta(days=3, hours=2),
        timezone="America/Guyana",
        status=status,
        visibility=EventVisibility.PUBLIC,
        approval_status=approval_status,
        custom_venue_name=venue.name,
    )
    db.add(event)
    db.flush()
    tier = TicketTier(
        event_id=event.id,
        name="General",
        tier_code=f"GEN-{event.id}",
        price_amount=1000,
        currency="GYD",
        quantity_total=100,
        quantity_sold=0,
        quantity_held=0,
        min_per_order=1,
        max_per_order=5,
        is_active=True,
        sort_order=0,
    )
    db.add(tier)
    db.flush()
    return event


def test_organizer_list_and_access_controls(client: TestClient, db_session: Session) -> None:
    owner = _seed_user(db_session, unique_email("owner_mgmt"), "Owner")
    other = _seed_user(db_session, unique_email("other_mgmt"), "Other")
    mine = _seed_event(db_session, owner, title="Mine")
    _seed_event(db_session, other, title="Theirs")

    listed = client.get("/events/organizer/events", headers={"x-user-id": str(owner.id)})
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert body[0]["id"] == mine.id

    forbidden = client.get(f"/events/organizer/events/{mine.id}", headers={"x-user-id": str(other.id)})
    assert forbidden.status_code == 403


def test_publish_unpublish_and_validation(client: TestClient, db_session: Session) -> None:
    owner = _seed_user(db_session, unique_email("publish_owner"), "Publisher")
    event = _seed_event(db_session, owner, title="Draft Publish", status=EventStatus.DRAFT)

    ok = client.post(f"/events/organizer/events/{event.id}/publish", headers={"x-user-id": str(owner.id)})
    assert ok.status_code == 200
    assert ok.json()["status"] == "published"
    assert ok.json()["approval_status"] == "approved"
    assert ok.json()["is_publicly_visible"] is True

    unpub = client.post(f"/events/organizer/events/{event.id}/unpublish", headers={"x-user-id": str(owner.id)})
    assert unpub.status_code == 200
    assert unpub.json()["status"] == "unpublished"

    event.title = ""
    db_session.flush()
    invalid = client.post(f"/events/organizer/events/{event.id}/publish", headers={"x-user-id": str(owner.id)})
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "publish_validation_failed"


def test_cancel_and_tier_editing_rules(client: TestClient, db_session: Session) -> None:
    owner = _seed_user(db_session, unique_email("cancel_owner"), "Canceller")
    event = _seed_event(db_session, owner, title="To Cancel", status=EventStatus.PUBLISHED)
    tier = db_session.query(TicketTier).filter(TicketTier.event_id == event.id).one()

    draft_edit = client.patch(
        f"/events/organizer/events/{event.id}",
        headers={"x-user-id": str(owner.id)},
        json={
            "title": "Updated Title",
            "ticket_tiers": [
                {
                    "id": tier.id,
                    "name": "General Updated",
                    "price_amount": "1200.00",
                    "currency": "GYD",
                    "quantity_total": 90,
                    "min_per_order": 1,
                    "max_per_order": 5,
                },
                {
                    "name": "VIP",
                    "price_amount": "3000.00",
                    "currency": "GYD",
                    "quantity_total": 10,
                    "min_per_order": 1,
                    "max_per_order": 2,
                },
            ],
        },
    )
    assert draft_edit.status_code == 200
    assert draft_edit.json()["title"] == "Updated Title"
    assert len(draft_edit.json()["ticket_tiers"]) == 2

    tier.quantity_sold = 8
    db_session.flush()
    too_low = client.patch(
        f"/events/organizer/events/{event.id}",
        headers={"x-user-id": str(owner.id)},
        json={
            "ticket_tiers": [
                {
                    "id": tier.id,
                    "name": "General Updated",
                    "price_amount": "1200.00",
                    "currency": "GYD",
                    "quantity_total": 5,
                    "min_per_order": 1,
                    "max_per_order": 5,
                }
            ]
        },
    )
    assert too_low.status_code == 422

    cannot_delete = client.patch(
        f"/events/organizer/events/{event.id}",
        headers={"x-user-id": str(owner.id)},
        json={
            "ticket_tiers": [
                {
                    "id": tier.id,
                    "name": "General Updated",
                    "price_amount": "1200.00",
                    "currency": "GYD",
                    "quantity_total": 90,
                    "min_per_order": 1,
                    "max_per_order": 5,
                    "delete": True,
                }
            ]
        },
    )
    assert cannot_delete.status_code == 422

    cancel = client.post(
        f"/events/organizer/events/{event.id}/cancel",
        headers={"x-user-id": str(owner.id)},
        json={"reason": "weather"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"


def test_dashboard_metrics_defaults(client: TestClient, db_session: Session) -> None:
    owner = _seed_user(db_session, unique_email("metrics_owner"), "Metrics")
    event = _seed_event(db_session, owner, title="Metrics Event", status=EventStatus.PUBLISHED)
    tier = db_session.query(TicketTier).filter(TicketTier.event_id == event.id).one()
    tier.quantity_sold = 3

    order = Order(
        event_id=event.id,
        user_id=owner.id,
        status=OrderStatus.COMPLETED,
        total_amount=3000,
        currency="GYD",
        payment_provider="manual",
        payment_reference="abc",
        payment_verification_status="verified",
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(OrderItem(order_id=order.id, ticket_tier_id=tier.id, quantity=3, unit_price=1000, currency="GYD"))
    db_session.flush()

    listed = client.get("/events/organizer/events", headers={"x-user-id": str(owner.id)})
    assert listed.status_code == 200
    row = listed.json()[0]
    assert row["status"] == "published"
    assert row["approval_status"] == "approved"
    assert row["is_publicly_visible"] is True
    assert row["sold_count"] == 3
    assert row["gross_revenue"] == 3000.0


def test_discovery_requires_published_and_approved(client: TestClient, db_session: Session) -> None:
    owner = _seed_user(db_session, unique_email("discover_owner"), "Discover Owner")
    approved = _seed_event(
        db_session,
        owner,
        title="Approved Discovery Event",
        status=EventStatus.PUBLISHED,
        approval_status=EventApprovalStatus.APPROVED,
    )
    pending = _seed_event(
        db_session,
        owner,
        title="Pending Discovery Event",
        status=EventStatus.PUBLISHED,
        approval_status=EventApprovalStatus.PENDING,
    )
    approved.published_at = datetime.now(UTC)
    pending.published_at = datetime.now(UTC)
    db_session.flush()

    response = client.get("/events/discover", headers={"x-user-id": str(owner.id)})
    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert approved.id in ids
    assert pending.id not in ids


def test_discovery_this_week_bucket_returns_success(client: TestClient, db_session: Session) -> None:
    owner = _seed_user(db_session, unique_email("discover_week_owner"), "Discover Week Owner")
    event = _seed_event(
        db_session,
        owner,
        title="This Week Event",
        status=EventStatus.PUBLISHED,
        approval_status=EventApprovalStatus.APPROVED,
    )
    event.published_at = datetime.now(UTC)
    db_session.flush()

    response = client.get(
        "/events/discover",
        params={"date_bucket": "this_week"},
        headers={"x-user-id": str(owner.id)},
    )
    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert event.id in ids


def test_organizer_event_status_variants_are_explicit(client: TestClient, db_session: Session) -> None:
    owner = _seed_user(db_session, unique_email("states_owner"), "States Owner")
    draft = _seed_event(db_session, owner, title="Draft State", status=EventStatus.DRAFT, approval_status=EventApprovalStatus.PENDING)
    published_pending = _seed_event(
        db_session,
        owner,
        title="Published Pending State",
        status=EventStatus.PUBLISHED,
        approval_status=EventApprovalStatus.PENDING,
    )
    published_pending.published_at = datetime.now(UTC)
    published_approved = _seed_event(
        db_session,
        owner,
        title="Published Approved State",
        status=EventStatus.PUBLISHED,
        approval_status=EventApprovalStatus.APPROVED,
    )
    published_approved.published_at = datetime.now(UTC)
    cancelled = _seed_event(db_session, owner, title="Cancelled State", status=EventStatus.CANCELLED, approval_status=EventApprovalStatus.APPROVED)
    db_session.flush()

    listed = client.get("/events/organizer/events", headers={"x-user-id": str(owner.id)})
    assert listed.status_code == 200
    by_title = {row["title"]: row for row in listed.json()}

    assert by_title[draft.title]["status"] == "draft"
    assert by_title[draft.title]["approval_status"] == "pending"
    assert by_title[draft.title]["is_publicly_visible"] is False

    assert by_title[published_pending.title]["status"] == "published"
    assert by_title[published_pending.title]["approval_status"] == "pending"
    assert by_title[published_pending.title]["visibility_state"] == "pending_review"
    assert by_title[published_pending.title]["is_publicly_visible"] is False

    assert by_title[published_approved.title]["status"] == "published"
    assert by_title[published_approved.title]["approval_status"] == "approved"
    assert by_title[published_approved.title]["visibility_state"] is None
    assert by_title[published_approved.title]["is_publicly_visible"] is True

    assert by_title[cancelled.title]["status"] == "cancelled"
    assert by_title[cancelled.title]["approval_status"] == "approved"
    assert by_title[cancelled.title]["is_publicly_visible"] is False

    detail = client.get(
        f"/events/organizer/events/{published_pending.id}",
        headers={"x-user-id": str(owner.id)},
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "published"
    assert detail.json()["approval_status"] == "pending"
    assert detail.json()["visibility_state"] == "pending_review"
    assert detail.json()["is_publicly_visible"] is False
