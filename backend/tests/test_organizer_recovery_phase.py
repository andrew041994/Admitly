from datetime import UTC, datetime, timedelta
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.enums import EventApprovalStatus, EventStaffRole, EventStatus, EventVisibility, OrderStatus
from app.models.event import Event
from app.models.event_staff import EventStaff
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.organizer_profile import OrganizerProfile
from app.models.ticket_tier import TicketTier
from app.models.user import User
from app.models.venue import Venue
from app.services.event_permissions import EventPermissionAction, has_event_permission_by_id


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client(db_session: Session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_user(db: Session, email: str, name: str = "User", phone: str | None = None) -> User:
    user = User(email=email, full_name=name, phone=phone)
    db.add(user)
    db.flush()
    return user


def _seed_event(db: Session, organizer_user: User, *, title: str = "Event", end_offset_hours: int = 8) -> Event:
    organizer = OrganizerProfile(user_id=organizer_user.id, business_name=organizer_user.full_name, display_name=organizer_user.full_name)
    db.add(organizer)
    db.flush()
    venue = Venue(organizer_id=organizer.id, name="Main Hall", city="Georgetown")
    db.add(venue)
    db.flush()
    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title=title,
        slug=f"{title.lower()}-{organizer_user.id}",
        start_at=datetime.now(UTC) + timedelta(hours=1),
        end_at=datetime.now(UTC) + timedelta(hours=end_offset_hours),
        timezone="UTC",
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        approval_status=EventApprovalStatus.APPROVED,
    )
    db.add(event)
    db.flush()
    return event


def test_event_creation_and_creator_ownership(client: TestClient, db_session: Session) -> None:
    creator = _seed_user(db_session, "creator@example.com", "Creator")
    payload = {
        "title": "Organizer Launch",
        "short_description": "Short",
        "long_description": "Long",
        "category": "Music",
        "start_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        "end_at": (datetime.now(UTC) + timedelta(days=2, hours=2)).isoformat(),
        "timezone": "UTC",
        "custom_venue_name": "Pop-up Stage",
        "custom_address_text": "Downtown",
    }
    response = client.post("/events", json=payload, headers={"x-user-id": str(creator.id)})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    created = db_session.get(Event, body["id"])
    assert created is not None
    profile = db_session.query(OrganizerProfile).filter(OrganizerProfile.user_id == creator.id).one()
    assert created.organizer_id == profile.id

    invalid = client.post("/events", json={**payload, "end_at": payload["start_at"]}, headers={"x-user-id": str(creator.id)})
    assert invalid.status_code == 422

    unauth = client.post("/events", json=payload)
    assert unauth.status_code == 401


def test_mine_and_active_event_listing(client: TestClient, db_session: Session) -> None:
    owner = _seed_user(db_session, "owner@example.com", "Owner")
    other = _seed_user(db_session, "other@example.com", "Other")
    _seed_event(db_session, owner, title="Active Event", end_offset_hours=10)
    ended = _seed_event(db_session, owner, title="Ended Event", end_offset_hours=-1)
    ended.end_at = datetime.now(UTC) - timedelta(hours=1)
    _seed_event(db_session, other, title="Other Event", end_offset_hours=10)
    db_session.commit()

    mine = client.get("/events/mine", headers={"x-user-id": str(owner.id)})
    assert mine.status_code == 200
    assert len(mine.json()) == 2

    active = client.get("/events/mine/active", headers={"x-user-id": str(owner.id)})
    assert active.status_code == 200
    titles = [row["title"] for row in active.json()]
    assert titles == ["Active Event"]


def test_staff_assignment_permissions_and_expiration(client: TestClient, db_session: Session) -> None:
    owner = _seed_user(db_session, "org@example.com", "Organizer")
    staff = _seed_user(db_session, "staff@example.com", "Staff")
    outsider = _seed_user(db_session, "outsider@example.com", "Outsider")
    event = _seed_event(db_session, owner, title="Checkin", end_offset_hours=2)
    outsider_event = _seed_event(db_session, outsider, title="Other", end_offset_hours=2)
    db_session.commit()

    assign = client.post(f"/events/{event.id}/staff", json={"user_id": staff.id, "role": EventStaffRole.CHECKIN.value}, headers={"x-user-id": str(owner.id)})
    assert assign.status_code == 201
    duplicate = client.post(f"/events/{event.id}/staff", json={"user_id": staff.id, "role": EventStaffRole.CHECKIN.value}, headers={"x-user-id": str(owner.id)})
    assert duplicate.status_code == 409
    forbidden = client.post(f"/events/{event.id}/staff", json={"user_id": owner.id, "role": EventStaffRole.CHECKIN.value}, headers={"x-user-id": str(outsider.id)})
    assert forbidden.status_code == 403

    assert has_event_permission_by_id(db_session, user_id=staff.id, event_id=event.id, action=EventPermissionAction.CHECKIN_TICKETS)
    assert not has_event_permission_by_id(db_session, user_id=staff.id, event_id=event.id, action=EventPermissionAction.EDIT_EVENT)
    assert not has_event_permission_by_id(db_session, user_id=staff.id, event_id=outsider_event.id, action=EventPermissionAction.CHECKIN_TICKETS)

    event.end_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()
    assert not has_event_permission_by_id(db_session, user_id=staff.id, event_id=event.id, action=EventPermissionAction.CHECKIN_TICKETS)


def test_dashboard_profile_and_user_search(client: TestClient, db_session: Session) -> None:
    owner = _seed_user(db_session, "owner2@example.com", "Owner Two", phone="+15550002222")
    staff = _seed_user(db_session, "staff2@example.com", "Staff Two")
    buyer = _seed_user(db_session, "buyer2@example.com", "Buyer Person")
    event = _seed_event(db_session, owner, title="Dash Event", end_offset_hours=12)
    tier = TicketTier(
        event_id=event.id,
        name="General",
        tier_code="GEN",
        price_amount=50,
        currency="GYD",
        quantity_total=10,
        quantity_sold=0,
        quantity_held=0,
        min_per_order=1,
        max_per_order=5,
        is_active=True,
        sort_order=0,
    )
    db_session.add(tier)
    db_session.flush()
    db_session.add(EventStaff(event_id=event.id, user_id=staff.id, role=EventStaffRole.CHECKIN, is_active=True, invited_by_user_id=owner.id))
    order = Order(user_id=buyer.id, event_id=event.id, status=OrderStatus.COMPLETED, total_amount=100, currency="GYD", payment_verification_status="verified")
    db_session.add(order)
    db_session.flush()
    db_session.add(OrderItem(order_id=order.id, ticket_tier_id=tier.id, quantity=2, unit_price=50))
    db_session.commit()

    dashboard = client.get(f"/events/{event.id}/dashboard", headers={"x-user-id": str(owner.id)})
    assert dashboard.status_code == 200
    assert "tickets_sold" in dashboard.json()
    forbidden = client.get(f"/events/{event.id}/dashboard", headers={"x-user-id": str(staff.id)})
    assert forbidden.status_code == 403

    profile = client.get("/account/profile", headers={"x-user-id": str(owner.id)})
    assert profile.status_code == 200
    assert profile.json()["my_events_count"] >= 1

    search = client.get("/users/search", params={"q": "staff"}, headers={"x-user-id": str(owner.id)})
    assert search.status_code == 200
    assert any("staff" in row["full_name"].lower() for row in search.json())
