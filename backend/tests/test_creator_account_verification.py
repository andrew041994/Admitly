from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.events import (
    approve_event_for_discovery,
    discover_events,
    get_event_creator_verification_history,
    record_event_creator_age_identity_verification,
    revoke_event_creator_verification,
)
from app.models.creator_age_identity_verification_history import CreatorAgeIdentityVerificationHistory
from app.models.event import Event
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus, TicketStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.organizer_profile import OrganizerProfile
from app.models.user import User
from app.models.ticket import Ticket
from app.models.ticket_tier import TicketTier
from app.schemas.event import (
    CreatorAgeIdentityRevocationRequest,
    EventCreatorAgeIdentityVerificationRequest,
)

UTC = timezone.utc


def _event(db: Session, *, creator: User, slug: str) -> Event:
    organizer = creator.organizer_profile
    if organizer is None:
        organizer = OrganizerProfile(
            user_id=creator.id,
            business_name=creator.full_name,
            display_name=creator.full_name,
        )
        db.add(organizer)
        db.flush()
    event = Event(
        organizer_id=organizer.id,
        title=slug.replace("-", " ").title(),
        slug=slug,
        start_at=datetime.now(UTC) + timedelta(days=2),
        end_at=datetime.now(UTC) + timedelta(days=2, hours=2),
        timezone="America/Guyana",
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        approval_status=EventApprovalStatus.PENDING,
        published_at=datetime.now(UTC),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_one_account_verification_supports_multiple_separately_approved_events(db_session: Session) -> None:
    admin = User(email="account-verify-admin@test.local", full_name="Admin", is_admin=True)
    creator = User(email="account-verify-creator@test.local", full_name="Creator")
    db_session.add_all([admin, creator]); db_session.commit()
    first = _event(db_session, creator=creator, slug="creator-first-event")
    second = _event(db_session, creator=creator, slug="creator-second-event")

    with pytest.raises(HTTPException) as blocked:
        approve_event_for_discovery(event_id=first.id, db=db_session, user_id=admin.id)
    assert blocked.value.status_code == 409

    result = record_event_creator_age_identity_verification(
        event_id=first.id,
        payload=EventCreatorAgeIdentityVerificationRequest(note="Mailbox review completed; no document data retained."),
        db=db_session,
        user_id=admin.id,
    )
    assert result.creator_account_verification_status == "verified"
    approve_event_for_discovery(event_id=first.id, db=db_session, user_id=admin.id)
    approve_event_for_discovery(event_id=second.id, db=db_session, user_id=admin.id)

    rows = db_session.execute(
        select(CreatorAgeIdentityVerificationHistory).where(
            CreatorAgeIdentityVerificationHistory.user_id == creator.id
        )
    ).scalars().all()
    assert [(row.action, row.previous_status, row.new_status) for row in rows] == [
        ("verified", "pending", "verified")
    ]
    for event_id in (first.id, second.id):
        snapshot = db_session.get(Event, event_id)
        assert snapshot.approval_status == EventApprovalStatus.APPROVED
        assert snapshot.creator_age_identity_verified_user_id == creator.id
        assert snapshot.creator_age_identity_verified_by_user_id == admin.id
        assert snapshot.creator_age_identity_verified_at is not None


def test_revocation_blocks_future_approval_without_mutating_approved_event(db_session: Session) -> None:
    admin = User(email="revoke-admin@test.local", full_name="Admin", is_admin=True)
    creator = User(email="revoke-creator@test.local", full_name="Creator")
    db_session.add_all([admin, creator]); db_session.commit()
    approved = _event(db_session, creator=creator, slug="approved-before-revocation")
    record_event_creator_age_identity_verification(
        event_id=approved.id,
        payload=EventCreatorAgeIdentityVerificationRequest(),
        db=db_session,
        user_id=admin.id,
    )
    approved_result = approve_event_for_discovery(event_id=approved.id, db=db_session, user_id=admin.id)
    original_snapshot_time = approved_result.creator_age_identity_verified_at
    tier = TicketTier(event_id=approved.id, name="General", tier_code="REVOKE-GEN", price_amount=Decimal("100.00"), currency="GYD", quantity_total=10)
    db_session.add(tier); db_session.flush()
    order = Order(user_id=creator.id, event_id=approved.id, status=OrderStatus.COMPLETED, total_amount=Decimal("100.00"), currency="GYD", payment_verification_status="verified")
    db_session.add(order); db_session.flush()
    item = OrderItem(order_id=order.id, ticket_tier_id=tier.id, quantity=1, unit_price=Decimal("100.00"), currency="GYD")
    db_session.add(item); db_session.flush()
    ticket = Ticket(order_id=order.id, order_item_id=item.id, event_id=approved.id, user_id=creator.id, purchaser_user_id=creator.id, owner_user_id=creator.id, ticket_tier_id=tier.id, status=TicketStatus.ISSUED, ticket_code="REVOKE-TICKET", manual_code="RVK-123456", qr_payload="REVOKE-QR", issued_at=datetime.now(UTC))
    db_session.add(ticket); db_session.commit()
    future = _event(db_session, creator=creator, slug="future-after-revocation")

    revoked = revoke_event_creator_verification(
        creator_user_id=creator.id,
        event_id=approved.id,
        payload=CreatorAgeIdentityRevocationRequest(reason="Document verification error requires review."),
        db=db_session,
        user_id=admin.id,
    )
    assert revoked.creator_account_verification_status == "revoked"
    assert revoked.creator_verification_manual_review_required is True
    preserved = db_session.get(Event, approved.id)
    assert preserved.approval_status == EventApprovalStatus.APPROVED
    assert preserved.status == EventStatus.PUBLISHED
    assert preserved.creator_age_identity_verified_at == original_snapshot_time
    assert db_session.get(Order, order.id).status == OrderStatus.COMPLETED
    assert db_session.get(Ticket, ticket.id).status == TicketStatus.ISSUED

    with pytest.raises(HTTPException) as blocked:
        approve_event_for_discovery(event_id=future.id, db=db_session, user_id=admin.id)
    assert blocked.value.status_code == 409
    assert approved.id in {
        row.id for row in discover_events(q=None, category=None, city=None, date_bucket=None, is_free=None, db=db_session)
    }

    record_event_creator_age_identity_verification(
        event_id=future.id,
        payload=EventCreatorAgeIdentityVerificationRequest(note="Reverification completed."),
        db=db_session,
        user_id=admin.id,
    )
    approve_event_for_discovery(event_id=future.id, db=db_session, user_id=admin.id)
    history = get_event_creator_verification_history(creator_user_id=creator.id, db=db_session, user_id=admin.id)
    assert [row.action for row in reversed(history)] == ["verified", "revoked", "verified"]


def test_non_admin_cannot_verify_or_revoke_creator(db_session: Session) -> None:
    creator = User(email="authority-creator@test.local", full_name="Creator")
    other = User(email="authority-other@test.local", full_name="Event Staff")
    db_session.add_all([creator, other]); db_session.commit()
    event = _event(db_session, creator=creator, slug="authority-event")

    with pytest.raises(HTTPException) as verify_error:
        record_event_creator_age_identity_verification(
            event_id=event.id,
            payload=EventCreatorAgeIdentityVerificationRequest(),
            db=db_session,
            user_id=other.id,
        )
    assert verify_error.value.status_code == 403

    creator.creator_age_identity_verification_status = "verified"
    db_session.add(creator); db_session.commit()
    with pytest.raises(HTTPException) as revoke_error:
        revoke_event_creator_verification(
            creator_user_id=creator.id,
            event_id=event.id,
            payload=CreatorAgeIdentityRevocationRequest(reason="Not authorized."),
            db=db_session,
            user_id=other.id,
        )
    assert revoke_error.value.status_code == 403


def test_api_models_expose_status_but_no_identity_document_fields() -> None:
    from app.schemas.account import AccountProfileResponse
    from app.schemas.auth import UserResponse

    for model in (AccountProfileResponse, UserResponse):
        names = set(model.model_fields)
        assert "creator_age_identity_verification_status" in names
        assert not names.intersection({"date_of_birth", "dob", "government_id_number", "id_image", "document_url"})
