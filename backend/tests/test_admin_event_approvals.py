from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.events import approve_event_for_discovery, discover_events, list_pending_event_approvals
from app.models.event import Event
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility
from app.models.organizer_profile import OrganizerProfile
from app.models.user import User
from app.models.venue import Venue


GUYANA_TZ = ZoneInfo("America/Guyana")


def _seed_event(
    db: Session,
    *,
    slug: str,
    title: str,
    approval_status: EventApprovalStatus,
    status: EventStatus = EventStatus.PUBLISHED,
    cancelled_at: datetime | None = None,
) -> Event:
    now = datetime.now(GUYANA_TZ).replace(microsecond=0)
    organizer_user = User(email=f"org-{slug}@test.local", full_name="Organizer")
    db.add(organizer_user)
    db.flush()

    organizer = OrganizerProfile(
        user_id=organizer_user.id,
        business_name="Organizer Biz",
        display_name="Organizer Biz",
    )
    db.add(organizer)
    db.flush()

    venue = Venue(organizer_id=organizer.id, name="Main Hall")
    db.add(venue)
    db.flush()

    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title=title,
        slug=slug,
        start_at=now + timedelta(days=1),
        end_at=now + timedelta(days=1, hours=3),
        status=status,
        visibility=EventVisibility.PUBLIC,
        approval_status=approval_status,
        timezone="America/Guyana",
        is_location_pinned=False,
        published_at=now - timedelta(minutes=5),
        cancelled_at=cancelled_at,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_pending_approval_list_and_approve_updates_state(db_session: Session) -> None:
    admin = User(email="admin-event-approve@test.local", full_name="Admin", is_admin=True)
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    pending = _seed_event(db_session, slug="pending-review-event", title="Pending Review", approval_status=EventApprovalStatus.PENDING)

    rows = list_pending_event_approvals(db=db_session, user_id=admin.id)
    assert [row.id for row in rows] == [pending.id]
    assert rows[0].approval_status == EventApprovalStatus.PENDING.value

    updated = approve_event_for_discovery(event_id=pending.id, db=db_session, user_id=admin.id)
    assert updated.id == pending.id
    assert updated.approval_status == EventApprovalStatus.APPROVED.value

    refreshed = db_session.execute(select(Event).where(Event.id == pending.id)).scalar_one()
    assert refreshed.approval_status == EventApprovalStatus.APPROVED

    remaining = list_pending_event_approvals(db=db_session, user_id=admin.id)
    assert remaining == []


def test_discovery_excludes_pending_and_includes_after_admin_approval(db_session: Session) -> None:
    admin = User(email="admin-event-discover@test.local", full_name="Admin", is_admin=True)
    viewer = User(email="viewer-event-discover@test.local", full_name="Viewer")
    db_session.add_all([admin, viewer])
    db_session.commit()
    db_session.refresh(admin)
    db_session.refresh(viewer)

    pending = _seed_event(db_session, slug="discover-pending-event", title="Needs Approval", approval_status=EventApprovalStatus.PENDING)

    before = discover_events(
        q=None,
        category=None,
        city=None,
        date_bucket=None,
        is_free=None,
        db=db_session,
    )
    assert all(item.id != pending.id for item in before)

    approve_event_for_discovery(event_id=pending.id, db=db_session, user_id=admin.id)

    after = discover_events(
        q=None,
        category=None,
        city=None,
        date_bucket=None,
        is_free=None,
        db=db_session,
    )
    assert any(item.id == pending.id for item in after)


def test_pending_approval_list_excludes_cancelled_events(db_session: Session) -> None:
    admin = User(email="admin-event-cancelled@test.local", full_name="Admin", is_admin=True)
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    active_pending = _seed_event(
        db_session,
        slug="active-pending-review-event",
        title="Active Pending Review",
        approval_status=EventApprovalStatus.PENDING,
    )
    _seed_event(
        db_session,
        slug="cancelled-status-pending-event",
        title="Cancelled By Status",
        approval_status=EventApprovalStatus.PENDING,
        status=EventStatus.CANCELLED,
    )
    _seed_event(
        db_session,
        slug="cancelled-at-pending-event",
        title="Cancelled By Timestamp",
        approval_status=EventApprovalStatus.PENDING,
        cancelled_at=datetime.now(GUYANA_TZ).replace(microsecond=0),
    )

    rows = list_pending_event_approvals(db=db_session, user_id=admin.id)
    assert [row.id for row in rows] == [active_pending.id]
