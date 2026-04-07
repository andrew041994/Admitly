from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Event, EventStaff, OrganizerProfile, Order, OrderItem, TicketTier, User, Venue
from app.models.enums import EventApprovalStatus, EventStaffRole, EventStatus, EventVisibility, OrderStatus
from app.services.event_permissions import EventPermissionAction, has_event_permission_by_id
from app.services.event_staff import (
    EventStaffConflictError,
    EventStaffValidationError,
    add_event_staff,
    list_event_staff,
    remove_event_staff,
    update_event_staff_role,
)
from app.services.tickets import check_in_ticket, issue_tickets_for_completed_order


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        yield session


def _seed_event(db: Session):
    now = datetime(2026, 4, 7, tzinfo=timezone.utc)
    owner = User(email="owner@event.test", full_name="Owner")
    admin = User(email="admin@event.test", full_name="Admin", is_admin=True)
    outsider = User(email="outsider@event.test", full_name="Outsider")
    manager = User(email="manager@event.test", full_name="Manager")
    checkin = User(email="checkin@event.test", full_name="Checkin")
    support = User(email="support@event.test", full_name="Support")
    buyer = User(email="buyer@event.test", full_name="Buyer")
    db.add_all([owner, admin, outsider, manager, checkin, support, buyer])
    db.flush()

    organizer = OrganizerProfile(user_id=owner.id, business_name="Org", display_name="Org")
    db.add(organizer)
    db.flush()
    venue = Venue(organizer_id=organizer.id, name="Venue")
    db.add(venue)
    db.flush()

    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title="Phase18",
        slug="phase18-event",
        start_at=now + timedelta(hours=1),
        end_at=now + timedelta(hours=4),
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
        name="GA",
        tier_code="GA",
        price_amount=Decimal("100.00"),
        currency="GYD",
        quantity_total=20,
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
        total_amount=Decimal("100.00"),
        currency="GYD",
        payment_verification_status="verified",
    )
    db.add(order)
    db.flush()

    db.add(OrderItem(order_id=order.id, ticket_tier_id=tier.id, quantity=1, unit_price=Decimal("100.00")))

    db.add_all(
        [
            EventStaff(event_id=event.id, user_id=manager.id, role=EventStaffRole.MANAGER, invited_by_user_id=owner.id),
            EventStaff(event_id=event.id, user_id=checkin.id, role=EventStaffRole.CHECKIN, invited_by_user_id=owner.id),
            EventStaff(event_id=event.id, user_id=support.id, role=EventStaffRole.SUPPORT, invited_by_user_id=owner.id),
        ]
    )
    db.commit()

    return {
        "event": event,
        "owner": owner,
        "admin": admin,
        "outsider": outsider,
        "manager": manager,
        "checkin": checkin,
        "support": support,
        "buyer": buyer,
    }


def test_staff_crud_permissions(db_session: Session) -> None:
    data = _seed_event(db_session)
    target = User(email="newstaff@event.test", full_name="New Staff")
    db_session.add(target)
    db_session.commit()

    added = add_event_staff(
        db_session,
        actor_user_id=data["owner"].id,
        event_id=data["event"].id,
        user_id=target.id,
        role=EventStaffRole.SUPPORT,
    )
    assert added.role == EventStaffRole.SUPPORT

    updated = update_event_staff_role(
        db_session,
        actor_user_id=data["owner"].id,
        event_id=data["event"].id,
        staff_id=added.id,
        role=EventStaffRole.CHECKIN,
    )
    assert updated.role == EventStaffRole.CHECKIN

    remove_event_staff(
        db_session,
        actor_user_id=data["owner"].id,
        event_id=data["event"].id,
        staff_id=added.id,
    )
    assert db_session.execute(select(EventStaff).where(EventStaff.id == added.id)).scalar_one_or_none() is None


def test_staff_duplicates_and_owner_role_rejected(db_session: Session) -> None:
    data = _seed_event(db_session)

    with pytest.raises(EventStaffConflictError):
        add_event_staff(
            db_session,
            actor_user_id=data["owner"].id,
            event_id=data["event"].id,
            user_id=data["manager"].id,
            role=EventStaffRole.MANAGER,
        )

    with pytest.raises(EventStaffValidationError):
        add_event_staff(
            db_session,
            actor_user_id=data["owner"].id,
            event_id=data["event"].id,
            user_id=data["outsider"].id,
            role=EventStaffRole.OWNER,
        )


def test_list_visibility_owner_admin_only(db_session: Session) -> None:
    from app.services.event_permissions import EventPermissionDeniedError

    data = _seed_event(db_session)
    assert len(list_event_staff(db_session, actor_user_id=data["owner"].id, event_id=data["event"].id)) == 3
    assert len(list_event_staff(db_session, actor_user_id=data["admin"].id, event_id=data["event"].id)) == 3

    with pytest.raises(EventPermissionDeniedError):
        list_event_staff(db_session, actor_user_id=data["manager"].id, event_id=data["event"].id)


def test_permission_matrix(db_session: Session) -> None:
    data = _seed_event(db_session)
    event_id = data["event"].id

    assert has_event_permission_by_id(db_session, user_id=data["owner"].id, event_id=event_id, action=EventPermissionAction.CANCEL_EVENT)
    assert has_event_permission_by_id(db_session, user_id=data["manager"].id, event_id=event_id, action=EventPermissionAction.MANAGE_REFUNDS)
    assert has_event_permission_by_id(db_session, user_id=data["checkin"].id, event_id=event_id, action=EventPermissionAction.CHECKIN_TICKETS)
    assert not has_event_permission_by_id(db_session, user_id=data["support"].id, event_id=event_id, action=EventPermissionAction.CHECKIN_TICKETS)
    assert has_event_permission_by_id(db_session, user_id=data["admin"].id, event_id=event_id, action=EventPermissionAction.MANAGE_EVENT_STAFF)


def test_checkin_role_can_checkin_support_cannot(db_session: Session) -> None:
    data = _seed_event(db_session)
    order = db_session.execute(select(Order).where(Order.event_id == data["event"].id)).scalar_one()
    ticket = issue_tickets_for_completed_order(db_session, order)[0]

    allowed = check_in_ticket(
        db_session,
        scanner_user_id=data["checkin"].id,
        event_id=data["event"].id,
        qr_payload=ticket.qr_payload,
    )
    assert allowed.valid is True

    denied = check_in_ticket(
        db_session,
        scanner_user_id=data["support"].id,
        event_id=data["event"].id,
        qr_payload=ticket.qr_payload,
    )
    assert denied.valid is False
    assert denied.status == "unauthorized"


def test_manager_can_refund_but_cannot_cancel_event(db_session: Session) -> None:
    from app.services.events import EventAuthorizationError, cancel_event
    from app.services.orders import refund_completed_order

    data = _seed_event(db_session)
    order = db_session.execute(select(Order).where(Order.event_id == data["event"].id)).scalar_one()
    issue_tickets_for_completed_order(db_session, order)

    refunded = refund_completed_order(
        db_session,
        order_id=order.id,
        actor_user_id=data["manager"].id,
        reason="ops",
    )
    assert refunded.refund_status == "refunded"

    with pytest.raises(EventAuthorizationError):
        cancel_event(db_session, event_id=data["event"].id, actor_user_id=data["manager"].id)


def test_checkin_role_cannot_refund_order(db_session: Session) -> None:
    from app.services.orders import OrderAuthorizationError, refund_completed_order

    data = _seed_event(db_session)
    order = db_session.execute(select(Order).where(Order.event_id == data["event"].id)).scalar_one()
    issue_tickets_for_completed_order(db_session, order)

    with pytest.raises(OrderAuthorizationError):
        refund_completed_order(db_session, order_id=order.id, actor_user_id=data["checkin"].id, reason="nope")
