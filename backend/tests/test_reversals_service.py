from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Event, OrganizerProfile, Order, OrderItem, Ticket, TicketHold, TicketTier, User, Venue
from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility, OrderStatus, TicketStatus
from app.services.events import EventAuthorizationError, cancel_event
from app.services.orders import (
    OrderAuthorizationError,
    OrderCancellationError,
    OrderRefundError,
    cancel_pending_order,
    refund_completed_order,
)
from app.services.tickets import (
    TicketCheckInConflictError,
    TicketTransferError,
    check_in_ticket_for_event,
    issue_tickets_for_completed_order,
    transfer_ticket_to_user,
)



def _seed_event(db: Session, *, organizer_user: User, slug: str) -> Event:
    now = datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc)
    organizer = OrganizerProfile(user_id=organizer_user.id, business_name="Org", display_name="Org")
    db.add(organizer)
    db.flush()

    venue = Venue(organizer_id=organizer.id, name="Venue")
    db.add(venue)
    db.flush()

    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title="Show",
        slug=slug,
        start_at=now + timedelta(days=2),
        end_at=now + timedelta(days=2, hours=2),
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        approval_status=EventApprovalStatus.APPROVED,
        timezone="America/Guyana",
        is_location_pinned=False,
    )
    db.add(event)
    db.flush()
    return event


def _seed_order(
    db: Session,
    *,
    event: Event,
    buyer: User,
    status: OrderStatus,
    payment_verification_status: str = "verified",
    quantity: int = 2,
    with_hold: bool = False,
) -> Order:
    tier = TicketTier(
        event_id=event.id,
        name="General",
        tier_code=f"GEN-{event.id}-{buyer.id}-{status.value}-{datetime.now(timezone.utc).timestamp()}",
        price_amount=Decimal("100.00"),
        currency="GYD",
        quantity_total=100,
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
        status=status,
        total_amount=Decimal(quantity) * Decimal("100.00"),
        currency="GYD",
        payment_verification_status=payment_verification_status,
    )
    db.add(order)
    db.flush()

    db.add(OrderItem(order_id=order.id, ticket_tier_id=tier.id, quantity=quantity, unit_price=Decimal("100.00")))

    if with_hold:
        db.add(
            TicketHold(
                event_id=event.id,
                ticket_tier_id=tier.id,
                user_id=buyer.id,
                quantity=quantity,
                expires_at=datetime(2026, 4, 6, 14, 0, tzinfo=timezone.utc),
                order_id=order.id,
            )
        )

    db.commit()
    db.refresh(order)
    return order


def test_cancel_pending_order_owner_only_and_not_payable(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = User(email="owner_cancel@example.com", full_name="Owner")
    other = User(email="other_cancel@example.com", full_name="Other")
    db_session.add_all([owner, other])
    db_session.flush()
    event = _seed_event(db_session, organizer_user=owner, slug="cancel-pending")
    order = _seed_order(db_session, event=event, buyer=owner, status=OrderStatus.PENDING, with_hold=True)

    called = {"cancelled": False}

    def _notify(order_obj, *, actor_user_id: int) -> None:  # noqa: ANN001
        assert order_obj.id == order.id
        assert actor_user_id == owner.id
        called["cancelled"] = True

    monkeypatch.setattr("app.services.orders.notify_order_cancelled", _notify)

    with pytest.raises(OrderAuthorizationError):
        cancel_pending_order(db_session, order_id=order.id, actor_user_id=other.id)

    cancelled = cancel_pending_order(db_session, order_id=order.id, actor_user_id=owner.id, reason="changed mind")
    assert cancelled.status == OrderStatus.CANCELLED
    assert cancelled.cancelled_at is not None
    assert cancelled.cancelled_by_user_id == owner.id
    assert cancelled.cancel_reason == "changed mind"
    assert called["cancelled"]


def test_cancel_pending_order_rejects_completed_and_repeat_cancel(db_session: Session) -> None:
    owner = User(email="owner_cancel2@example.com", full_name="Owner")
    db_session.add(owner)
    db_session.flush()
    event = _seed_event(db_session, organizer_user=owner, slug="cancel-completed")
    completed = _seed_order(db_session, event=event, buyer=owner, status=OrderStatus.COMPLETED)

    with pytest.raises(OrderCancellationError):
        cancel_pending_order(db_session, order_id=completed.id, actor_user_id=owner.id)

    pending = _seed_order(db_session, event=event, buyer=owner, status=OrderStatus.PENDING, with_hold=True)
    cancel_pending_order(db_session, order_id=pending.id, actor_user_id=owner.id)
    with pytest.raises(OrderCancellationError):
        cancel_pending_order(db_session, order_id=pending.id, actor_user_id=owner.id)


def test_refund_completed_order_invalidates_tickets_and_records_audit(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    organizer_user = User(email="organizer_refund@example.com", full_name="Organizer")
    buyer = User(email="buyer_refund@example.com", full_name="Buyer")
    db_session.add_all([organizer_user, buyer])
    db_session.flush()

    event = _seed_event(db_session, organizer_user=organizer_user, slug="refund-event")
    order = _seed_order(db_session, event=event, buyer=buyer, status=OrderStatus.COMPLETED)
    tickets = issue_tickets_for_completed_order(db_session, order)
    assert all(ticket.status == TicketStatus.ISSUED for ticket in tickets)

    called = {"refunded": False}

    def _notify(order_obj, *, actor_user_id: int) -> None:  # noqa: ANN001
        assert order_obj.id == order.id
        assert actor_user_id == organizer_user.id
        called["refunded"] = True

    monkeypatch.setattr("app.services.orders.notify_order_refunded", _notify)

    refunded = refund_completed_order(
        db_session,
        order_id=order.id,
        actor_user_id=organizer_user.id,
        reason="customer request",
    )
    assert refunded.refund_status == "refunded"
    assert refunded.refunded_by_user_id == organizer_user.id
    assert refunded.refund_reason == "customer request"
    assert refunded.refunded_at is not None
    assert called["refunded"]

    refreshed = db_session.execute(select(Ticket).where(Ticket.order_id == order.id)).scalars().all()
    assert len(refreshed) == len(tickets)
    assert all(ticket.status == TicketStatus.VOIDED for ticket in refreshed)

    with pytest.raises(TicketCheckInConflictError):
        check_in_ticket_for_event(
            db_session,
            scanner_user_id=organizer_user.id,
            event_id=event.id,
            qr_payload=refreshed[0].qr_payload,
            ticket_code=None,
        )

    recipient = User(email="recipient_refund@example.com", full_name="Recipient")
    db_session.add(recipient)
    db_session.commit()
    db_session.refresh(recipient)
    with pytest.raises(TicketTransferError):
        transfer_ticket_to_user(
            db_session,
            ticket_id=refreshed[0].id,
            from_user_id=buyer.id,
            to_user_id=recipient.id,
        )


def test_refund_rejects_unauthorized_repeat_and_checked_in_ticket(db_session: Session) -> None:
    organizer_user = User(email="organizer_refund2@example.com", full_name="Organizer")
    buyer = User(email="buyer_refund2@example.com", full_name="Buyer")
    outsider = User(email="outsider_refund2@example.com", full_name="Outsider")
    db_session.add_all([organizer_user, buyer, outsider])
    db_session.flush()

    event = _seed_event(db_session, organizer_user=organizer_user, slug="refund-event-2")
    order = _seed_order(db_session, event=event, buyer=buyer, status=OrderStatus.COMPLETED)
    tickets = issue_tickets_for_completed_order(db_session, order)

    with pytest.raises(OrderAuthorizationError):
        refund_completed_order(db_session, order_id=order.id, actor_user_id=outsider.id)

    refunded = refund_completed_order(db_session, order_id=order.id, actor_user_id=organizer_user.id)
    assert refunded.refund_status == "refunded"
    with pytest.raises(OrderRefundError):
        refund_completed_order(db_session, order_id=order.id, actor_user_id=organizer_user.id)

    order2 = _seed_order(db_session, event=event, buyer=buyer, status=OrderStatus.COMPLETED)
    tickets2 = issue_tickets_for_completed_order(db_session, order2)
    check_in_ticket_for_event(
        db_session,
        scanner_user_id=organizer_user.id,
        event_id=event.id,
        qr_payload=tickets2[0].qr_payload,
        ticket_code=None,
    )
    with pytest.raises(OrderRefundError):
        refund_completed_order(db_session, order_id=order2.id, actor_user_id=organizer_user.id)

    assert tickets


def test_cancel_event_voids_issued_tickets_and_cancels_pending_orders(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    organizer_user = User(email="organizer_event_cancel@example.com", full_name="Organizer")
    buyer = User(email="buyer_event_cancel@example.com", full_name="Buyer")
    outsider = User(email="outsider_event_cancel@example.com", full_name="Outsider")
    db_session.add_all([organizer_user, buyer, outsider])
    db_session.flush()

    event = _seed_event(db_session, organizer_user=organizer_user, slug="event-cancel")
    completed = _seed_order(db_session, event=event, buyer=buyer, status=OrderStatus.COMPLETED)
    pending = _seed_order(db_session, event=event, buyer=buyer, status=OrderStatus.PENDING, with_hold=True)
    issued = issue_tickets_for_completed_order(db_session, completed)

    called = {"event": False}

    def _notify(event_obj, *, actor_user_id: int) -> None:  # noqa: ANN001
        assert event_obj.id == event.id
        assert actor_user_id == organizer_user.id
        called["event"] = True

    monkeypatch.setattr("app.services.events.notify_event_cancelled", _notify)

    with pytest.raises(EventAuthorizationError):
        cancel_event(db_session, event_id=event.id, actor_user_id=outsider.id)

    cancelled_event, _ = cancel_event(db_session, event_id=event.id, actor_user_id=organizer_user.id, reason="weather")
    assert cancelled_event.status == EventStatus.CANCELLED
    assert cancelled_event.cancelled_by_user_id == organizer_user.id
    assert cancelled_event.cancellation_reason == "weather"
    assert called["event"]

    db_session.refresh(pending)
    assert pending.status == OrderStatus.CANCELLED
    assert pending.cancel_reason == "Event cancelled: weather"

    refreshed_tickets = db_session.execute(select(Ticket).where(Ticket.event_id == event.id)).scalars().all()
    assert len(refreshed_tickets) == len(issued)
    assert all(ticket.status == TicketStatus.VOIDED for ticket in refreshed_tickets)
