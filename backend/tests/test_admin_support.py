from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.admin_support import create_support_note, get_support_snapshot, update_support_case
from app.main import app
from app.models import (
    AdminActionAudit,
    Dispute,
    Event,
    OrganizerProfile,
    Order,
    OrderItem,
    PromoCode,
    PromoCodeRedemption,
    Refund,
    SupportCase,
    SupportCaseNote,
    Ticket,
    TicketTier,
    TicketTransferInvite,
    User,
    Venue,
)
from app.models.enums import (
    DisputeStatus,
    EventApprovalStatus,
    EventStatus,
    EventVisibility,
    OrderStatus,
    PricingSource,
    RefundReason,
    RefundStatus,
    SupportCasePriority,
    SupportCaseStatus,
    TicketStatus,
    TransferInviteStatus,
)
from app.schemas.support import SupportActionRequest, SupportCasePatchRequest, SupportNoteCreateRequest
from app.services.support import (
    build_order_support_timeline,
    get_or_create_support_case_for_order,
    run_admin_support_action,
)
from app.db.base import Base



def _seed(db: Session, *, suffix: str = "support") -> tuple[Order, User, User]:
    now = datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc)
    admin = User(email=f"admin-{suffix}@test.local", full_name="Admin", is_admin=True)
    non_admin = User(email=f"buyer-{suffix}@test.local", full_name="Buyer", is_admin=False)
    organizer_user = User(email=f"org-{suffix}@test.local", full_name="Org")
    db.add_all([admin, non_admin, organizer_user])
    db.flush()

    organizer = OrganizerProfile(user_id=organizer_user.id, business_name="Biz", display_name="Biz")
    db.add(organizer)
    db.flush()
    venue = Venue(organizer_id=organizer.id, name="Main")
    db.add(venue)
    db.flush()
    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title=f"Support Event {suffix}",
        slug=f"support-event-{suffix}",
        start_at=now + timedelta(days=5),
        end_at=now + timedelta(days=5, hours=2),
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
        price_amount=Decimal("100.00"),
        currency="GYD",
        quantity_total=100,
        quantity_sold=0,
        quantity_held=0,
        min_per_order=1,
        max_per_order=4,
        is_active=True,
        sort_order=0,
    )
    db.add(tier)
    db.flush()

    order = Order(
        user_id=non_admin.id,
        event_id=event.id,
        status=OrderStatus.COMPLETED,
        subtotal_amount=Decimal("100.00"),
        discount_amount=Decimal("10.00"),
        total_amount=Decimal("90.00"),
        pricing_source=PricingSource.PROMO_CODE,
        promo_code_text="SAVE10",
        payment_reference="MMG-123",
        payment_verification_status="verified",
        paid_at=now,
    )
    db.add(order)
    db.flush()
    order_item = OrderItem(order_id=order.id, ticket_tier_id=tier.id, quantity=1, unit_price=Decimal("100.00"))
    db.add(order_item)
    db.flush()
    db.add(
        Ticket(
            order_id=order.id,
            order_item_id=order_item.id,
            event_id=event.id,
            user_id=non_admin.id,
            purchaser_user_id=non_admin.id,
            owner_user_id=non_admin.id,
            ticket_tier_id=tier.id,
            status=TicketStatus.ISSUED,
            ticket_code=f"TCK-{suffix}",
            qr_payload=f"QR-{suffix}",
            issued_at=now,
        )
    )
    db.commit()
    db.refresh(order)
    return order, admin, non_admin


def test_get_or_create_case_returns_existing_active_case(db_session: Session) -> None:
    order, admin, _ = _seed(db_session, suffix="existing")
    case1 = get_or_create_support_case_for_order(db_session, order.id, created_by_user_id=admin.id)
    case2 = get_or_create_support_case_for_order(db_session, order.id, created_by_user_id=admin.id)
    assert case1.id == case2.id


def test_adding_note_creates_case_and_audit(db_session: Session) -> None:
    order, admin, _ = _seed(db_session, suffix="note")
    created = create_support_note(order.id, SupportNoteCreateRequest(body="  Investigating payment mismatch  "), db=db_session, user_id=admin.id)
    assert created.body == "Investigating payment mismatch"
    case = db_session.execute(select(SupportCase).where(SupportCase.order_id == order.id)).scalar_one()
    assert case is not None
    audit = db_session.execute(select(AdminActionAudit).where(AdminActionAudit.action_type == "support_note_added")).scalar_one()
    assert audit.actor_user_id == admin.id


def test_patch_case_writes_audits(db_session: Session) -> None:
    order, admin, _ = _seed(db_session, suffix="patch")
    response = update_support_case(
        order.id,
        SupportCasePatchRequest(status="investigating", priority="urgent", assigned_to_user_id=admin.id, category="payment_issue"),
        db=db_session,
        user_id=admin.id,
    )
    assert response.status == "investigating"
    assert response.priority == "urgent"
    audits = db_session.execute(select(AdminActionAudit).where(AdminActionAudit.target_type == "support_case")).scalars().all()
    assert {a.action_type for a in audits} >= {
        "support_case_status_changed",
        "support_case_priority_changed",
        "support_case_assigned",
        "support_case_category_changed",
    }


def test_support_snapshot_merges_data(db_session: Session) -> None:
    order, admin, _ = _seed(db_session, suffix="snapshot")
    db_session.add(Refund(order_id=order.id, user_id=order.user_id, amount=Decimal("20.00"), status=RefundStatus.PENDING, reason=RefundReason.OTHER))
    db_session.add(Dispute(order_id=order.id, user_id=order.user_id, message="help", status=DisputeStatus.OPEN))
    db_session.commit()
    create_support_note(order.id, SupportNoteCreateRequest(body="hello"), db=db_session, user_id=admin.id)

    snap = get_support_snapshot(order.id, db=db_session, user_id=admin.id)
    assert snap.order_id == order.id
    assert snap.order_reference == order.reference_code
    assert snap.dispute_count == 1
    assert snap.support_case is not None
    assert len(snap.timeline) >= 2


def test_timeline_includes_order_payment_note_and_audit_ordered(db_session: Session) -> None:
    order, admin, _ = _seed(db_session, suffix="timeline")
    create_support_note(order.id, SupportNoteCreateRequest(body="timeline note"), db=db_session, user_id=admin.id)
    timeline = build_order_support_timeline(db_session, order.id)
    titles = [i["title"] for i in timeline]
    assert "Order created" in titles
    assert "Support note" in titles
    timestamps = [i["timestamp"] for i in timeline]
    assert timestamps == sorted(timestamps)


def test_resend_confirmation_action_dispatches_and_audits(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    order, admin, _ = _seed(db_session, suffix="resend")
    called = {"completed": 0, "tickets": 0}
    monkeypatch.setattr("app.services.support.notify_order_completed", lambda db, o: type("R", (), {"success": True})())
    monkeypatch.setattr("app.services.support.notify_tickets_issued", lambda db, o, t: called.__setitem__("tickets", len(t)) or type("R", (), {"success": True})())

    result = run_admin_support_action(db_session, order_id=order.id, actor_user_id=admin.id, action_type="resend_confirmation", reason="customer request")
    assert result.success is True
    assert called["tickets"] == 1
    audit = db_session.execute(select(AdminActionAudit).where(AdminActionAudit.action_type == "resend_confirmation")).scalar_one()
    assert audit is not None


def test_resend_transfer_invite_requires_pending(db_session: Session) -> None:
    order, admin, _ = _seed(db_session, suffix="invite")
    ticket = db_session.execute(select(Ticket).where(Ticket.order_id == order.id)).scalar_one()
    db_session.add(TicketTransferInvite(ticket_id=ticket.id, sender_user_id=order.user_id, invite_token="abc", status=TransferInviteStatus.ACCEPTED))
    db_session.commit()

    with pytest.raises(Exception):
        run_admin_support_action(db_session, order_id=order.id, actor_user_id=admin.id, action_type="resend_transfer_invite", reason="retry")


def test_remove_promo_application_conflicts_when_order_immutable(db_session: Session) -> None:
    order, admin, _ = _seed(db_session, suffix="promo-conflict")
    with pytest.raises(Exception):
        run_admin_support_action(db_session, order_id=order.id, actor_user_id=admin.id, action_type="remove_promo_application", reason="cleanup")


def test_non_admin_access_rejected(db_session: Session) -> None:
    order, _, non_admin = _seed(db_session, suffix="nonadmin")
    with pytest.raises(HTTPException) as exc:
        create_support_note(order.id, SupportNoteCreateRequest(body="x"), db=db_session, user_id=non_admin.id)
    assert exc.value.status_code == 403


def test_blank_note_and_sensitive_reason_validation(db_session: Session) -> None:
    order, admin, _ = _seed(db_session, suffix="validation")
    with pytest.raises(HTTPException):
        create_support_note(order.id, SupportNoteCreateRequest(body="   "), db=db_session, user_id=admin.id)

    with pytest.raises(Exception):
        run_admin_support_action(db_session, order_id=order.id, actor_user_id=admin.id, action_type="flag_for_fraud_review", reason="  ")

def test_flag_for_fraud_review_replay_is_noop(db_session: Session) -> None:
    order, admin, _ = _seed(db_session, suffix="fraud-noop")
    first = run_admin_support_action(
        db_session,
        order_id=order.id,
        actor_user_id=admin.id,
        action_type="flag_for_fraud_review",
        reason="suspicious retries",
    )
    second = run_admin_support_action(
        db_session,
        order_id=order.id,
        actor_user_id=admin.id,
        action_type="flag_for_fraud_review",
        reason="duplicate click",
    )
    assert first.success is True
    assert second.success is True
    assert "No-op" in second.message


def test_admin_support_routes_registered() -> None:
    route_paths = {route.path for route in app.routes}
    assert "/admin/support/orders/{order_id}" in route_paths
    assert "/admin/support/orders/{order_id}/notes" in route_paths
    assert "/admin/support/orders/{order_id}/case" in route_paths
    assert "/admin/support/orders/{order_id}/actions" in route_paths
