from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.admin_action_audit import AdminActionAudit
from app.models.enums import EventApprovalStatus, EventStaffRole, EventStatus, EventVisibility, OrderStatus
from app.models.event import Event
from app.models.event_reminder_log import EventReminderLog
from app.models.event_reschedule import EventReschedule
from app.models.event_staff import EventStaff
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.organizer_profile import OrganizerProfile
from app.models.push_dispatch import NotificationJob
from app.models.ticket import Ticket
from app.models.ticket_tier import TicketTier
from app.models.user import User
from app.models.venue import Venue
from app.services.nearby_notifications import process_notification_jobs
from app.services.ticket_wallet import get_wallet_ticket
from app.services.tickets import issue_tickets_for_completed_order
from tests.utils import auth_headers, unique_email

UTC = timezone.utc


def _user(db: Session, label: str, *, admin: bool = False) -> User:
    row = User(email=unique_email(label), full_name=label.title(), is_admin=admin)
    db.add(row)
    db.flush()
    return row


def _event(db: Session, owner: User, *, approved: bool = True) -> tuple[Event, TicketTier]:
    organizer = OrganizerProfile(user_id=owner.id, business_name="Creator", display_name="Creator")
    db.add(organizer)
    db.flush()
    venue = Venue(organizer_id=organizer.id, name=f"Original Venue {owner.id}", address_line1="1 Original Street")
    db.add(venue)
    db.flush()
    start = datetime.now(UTC) + timedelta(days=5)
    event = Event(
        organizer_id=organizer.id,
        venue_id=venue.id,
        title=f"Reschedule {owner.id}",
        slug=f"reschedule-{owner.id}",
        start_at=start,
        end_at=start + timedelta(hours=3),
        doors_open_at=start - timedelta(hours=1),
        sales_start_at=start - timedelta(days=4),
        sales_end_at=start - timedelta(hours=2),
        timezone="America/Guyana",
        status=EventStatus.PUBLISHED,
        visibility=EventVisibility.PUBLIC,
        approval_status=EventApprovalStatus.APPROVED if approved else EventApprovalStatus.PENDING,
    )
    db.add(event)
    db.flush()
    tier = TicketTier(
        event_id=event.id, name="General", tier_code="GEN", price_amount=1000, currency="GYD",
        quantity_total=100, quantity_sold=0, quantity_held=0, min_per_order=1, max_per_order=5,
        is_active=True, sort_order=0,
    )
    db.add(tier)
    db.commit()
    return event, tier


def _payload(event: Event, *, key: str = "reschedule-request-0001") -> dict:
    start = event.start_at + timedelta(days=7)
    return {
        "idempotency_key": key,
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=3)).isoformat(),
        "doors_open_at": (start - timedelta(hours=1)).isoformat(),
        "sales_start_at": event.sales_start_at.isoformat() if event.sales_start_at else None,
        "sales_end_at": (start - timedelta(hours=2)).isoformat(),
        "venue_id": event.venue_id,
        "custom_venue_name": event.custom_venue_name,
        "custom_address_text": event.custom_address_text,
        "latitude": str(event.latitude) if event.latitude is not None else None,
        "longitude": str(event.longitude) if event.longitude is not None else None,
        "is_location_pinned": bool(event.is_location_pinned),
        "reason": "Venue availability changed the event date.",
    }


def _venue_only_payload(event: Event, *, key: str, name: str = "New Custom Venue") -> dict:
    return {
        "idempotency_key": key,
        "start_at": event.start_at.isoformat(),
        "end_at": event.end_at.isoformat(),
        "doors_open_at": event.doors_open_at.isoformat() if event.doors_open_at else None,
        "sales_start_at": event.sales_start_at.isoformat() if event.sales_start_at else None,
        "sales_end_at": event.sales_end_at.isoformat() if event.sales_end_at else None,
        "venue_id": None,
        "custom_venue_name": name,
        "custom_address_text": "22 New Venue Road",
        "latitude": "6.8013000",
        "longitude": "-58.1551000",
        "is_location_pinned": True,
        "reason": "The event moved to a more suitable venue.",
    }


def _issue_ticket(db: Session, *, event: Event, tier: TicketTier, buyer: User) -> Ticket:
    order = Order(
        user_id=buyer.id, event_id=event.id, status=OrderStatus.COMPLETED,
        total_amount=1000, currency="GYD", payment_verification_status="verified",
    )
    db.add(order)
    db.flush()
    db.add(OrderItem(order_id=order.id, ticket_tier_id=tier.id, quantity=1, unit_price=1000))
    db.commit()
    return issue_tickets_for_completed_order(db, order)[0]


def test_creator_reschedules_approved_event_with_durable_history_and_no_ticket_notification(db_session: Session) -> None:
    owner = _user(db_session, "reschedule-owner")
    event, _ = _event(db_session, owner)
    payload = _payload(event)
    old_start = event.start_at

    with TestClient(app) as client:
        response = client.post(f"/events/organizer/events/{event.id}/reschedule", json=payload, headers=auth_headers(owner))

    assert response.status_code == 200
    assert response.json()["notifications_required"] is False
    db_session.refresh(event)
    assert event.start_at.isoformat() == datetime.fromisoformat(payload["start_at"]).isoformat()
    history = db_session.execute(select(EventReschedule).where(EventReschedule.event_id == event.id)).scalar_one()
    assert history.previous_start_at == old_start
    assert history.actor_user_id == owner.id
    assert db_session.execute(select(AdminActionAudit).where(AdminActionAudit.action_type == "reschedule_event")).scalar_one()
    assert db_session.execute(select(NotificationJob).where(NotificationJob.job_type == "event_reschedule")).scalar_one_or_none() is None


def test_admin_allowed_but_unrelated_and_staff_rejected(db_session: Session) -> None:
    owner = _user(db_session, "reschedule-owner-auth")
    admin = _user(db_session, "reschedule-admin", admin=True)
    outsider = _user(db_session, "reschedule-outsider")
    scanner = _user(db_session, "reschedule-scanner")
    event, _ = _event(db_session, owner)
    db_session.add(EventStaff(event_id=event.id, user_id=scanner.id, role=EventStaffRole.CHECKIN, invited_by_user_id=owner.id))
    db_session.commit()

    with TestClient(app) as client:
        assert client.post(f"/events/organizer/events/{event.id}/reschedule", json=_payload(event, key="anonymous-request")).status_code == 401
        assert client.post(f"/events/organizer/events/{event.id}/reschedule", json=_payload(event, key="outsider-request"), headers=auth_headers(outsider)).status_code == 403
        assert client.post(f"/events/organizer/events/{event.id}/reschedule", json=_payload(event, key="scanner-request"), headers=auth_headers(scanner)).status_code == 403
        allowed = client.post(f"/events/organizer/events/{event.id}/reschedule", json=_venue_only_payload(event, key="admin-request-0001"), headers=auth_headers(admin))
    assert allowed.status_code == 200


def test_approved_patch_rejects_schedule_but_pending_patch_allows_it(db_session: Session) -> None:
    owner = _user(db_session, "patch-owner")
    approved, _ = _event(db_session, owner)
    pending_owner = _user(db_session, "patch-pending-owner")
    pending, _ = _event(db_session, pending_owner, approved=False)
    new_approved_start = approved.start_at + timedelta(days=1)
    new_pending_start = pending.start_at + timedelta(days=1)

    with TestClient(app) as client:
        blocked = client.patch(
            f"/events/organizer/events/{approved.id}",
            json={"start_at": new_approved_start.isoformat()}, headers=auth_headers(owner),
        )
        allowed = client.patch(
            f"/events/organizer/events/{pending.id}",
            json={"start_at": new_pending_start.isoformat(), "end_at": (new_pending_start + timedelta(hours=3)).isoformat()},
            headers=auth_headers(pending_owner),
        )
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["code"] == "material_change_required"
    assert allowed.status_code == 200


def test_approved_patch_blocks_venue_but_pending_venue_edit_remains_available(db_session: Session) -> None:
    owner = _user(db_session, "venue-patch-owner")
    approved, _ = _event(db_session, owner)
    pending_owner = _user(db_session, "venue-patch-pending")
    pending, _ = _event(db_session, pending_owner, approved=False)

    with TestClient(app) as client:
        blocked = client.patch(
            f"/events/organizer/events/{approved.id}",
            json={"venue_id": None, "custom_venue_name": "Silent Move", "custom_address_text": "1 Hidden Road"},
            headers=auth_headers(owner),
        )
        allowed = client.patch(
            f"/events/organizer/events/{pending.id}",
            json={"venue_id": None, "custom_venue_name": "Draft Venue", "custom_address_text": "5 Draft Street"},
            headers=auth_headers(pending_owner),
        )
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["code"] == "material_change_required"
    assert allowed.status_code == 200
    db_session.refresh(pending)
    assert pending.venue_id is None
    assert pending.custom_venue_name == "Draft Venue"


def test_venue_only_and_combined_material_changes_preserve_history(db_session: Session) -> None:
    owner = _user(db_session, "venue-change-owner")
    event, _ = _event(db_session, owner)
    old_venue_id = event.venue_id
    venue_payload = _venue_only_payload(event, key="venue-only-change-0001")

    with TestClient(app) as client:
        venue_only = client.post(f"/events/organizer/events/{event.id}/reschedule", json=venue_payload, headers=auth_headers(owner))
        retry = client.post(f"/events/organizer/events/{event.id}/reschedule", json=venue_payload, headers=auth_headers(owner))
    assert venue_only.status_code == retry.status_code == 200
    assert venue_only.json()["id"] == retry.json()["id"]
    assert venue_only.json()["notifications_required"] is False
    history = db_session.get(EventReschedule, venue_only.json()["id"])
    assert history is not None
    assert history.previous_venue_id == old_venue_id
    assert history.new_venue_id is None
    assert history.new_custom_venue_name == "New Custom Venue"
    assert history.previous_start_at == history.new_start_at

    new_venue = Venue(organizer_id=event.organizer_id, name="Combined Venue", address_line1="90 Combined Avenue")
    db_session.add(new_venue)
    db_session.commit()
    combined = _payload(event, key="combined-change-0001")
    combined.update({
        "venue_id": new_venue.id,
        "custom_venue_name": None,
        "custom_address_text": None,
        "latitude": None,
        "longitude": None,
        "is_location_pinned": False,
    })
    with TestClient(app) as client:
        response = client.post(f"/events/organizer/events/{event.id}/reschedule", json=combined, headers=auth_headers(owner))
    assert response.status_code == 200
    db_session.refresh(event)
    assert event.venue_id == new_venue.id
    assert event.start_at.isoformat() == datetime.fromisoformat(combined["start_at"]).isoformat()


def test_material_change_noop_invalid_location_and_reused_key_conflict(db_session: Session) -> None:
    owner = _user(db_session, "venue-validation-owner")
    event, _ = _event(db_session, owner)
    no_op = _venue_only_payload(event, key="no-op-change-0001")
    no_op.update({
        "venue_id": event.venue_id,
        "custom_venue_name": None,
        "custom_address_text": None,
        "latitude": None,
        "longitude": None,
        "is_location_pinned": False,
    })
    venue_payload = _venue_only_payload(event, key="venue-key-conflict-0001")
    with TestClient(app) as client:
        assert client.post(f"/events/organizer/events/{event.id}/reschedule", json=no_op, headers=auth_headers(owner)).status_code == 422
        assert client.post(
            f"/events/organizer/events/{event.id}/reschedule",
            json={**venue_payload, "venue_id": 999999, "custom_venue_name": None, "custom_address_text": None},
            headers=auth_headers(owner),
        ).status_code == 422
        first = client.post(f"/events/organizer/events/{event.id}/reschedule", json=venue_payload, headers=auth_headers(owner))
        conflict = client.post(
            f"/events/organizer/events/{event.id}/reschedule",
            json={**venue_payload, "custom_venue_name": "Different Venue"},
            headers=auth_headers(owner),
        )
    assert first.status_code == 200
    assert conflict.status_code == 409


def test_ticketed_venue_change_keeps_credentials_updates_reads_and_notifies_once(db_session: Session, monkeypatch) -> None:  # noqa: ANN001
    owner = _user(db_session, "ticketed-venue-owner")
    buyer = _user(db_session, "ticketed-venue-buyer")
    event, tier = _event(db_session, owner)
    ticket = _issue_ticket(db_session, event=event, tier=tier, buyer=buyer)
    credentials = (ticket.ticket_code, ticket.manual_code, ticket.display_code, ticket.qr_payload, ticket.qr_token)
    event.creator_age_identity_verification_status = "verified"
    event.creator_age_identity_verified_user_id = owner.id
    event.creator_age_identity_verified_by_user_id = owner.id
    event.creator_age_identity_verified_at = datetime.now(UTC)
    event.published_at = datetime.now(UTC)
    db_session.commit()
    payload = _venue_only_payload(event, key="ticketed-venue-change-0001", name="Buyer Updated Venue")

    with TestClient(app) as client:
        response = client.post(f"/events/organizer/events/{event.id}/reschedule", json=payload, headers=auth_headers(owner))
        public = client.get(f"/events/discover/{event.id}")
    assert response.status_code == 200
    assert response.json()["notifications_required"] is True
    assert public.status_code == 200
    assert public.json()["custom_venue_name"] == "Buyer Updated Venue"
    assert db_session.query(NotificationJob).filter_by(job_type="event_reschedule").count() == 1
    db_session.refresh(ticket)
    assert (ticket.ticket_code, ticket.manual_code, ticket.display_code, ticket.qr_payload, ticket.qr_token) == credentials
    wallet = get_wallet_ticket(db_session, user_id=buyer.id, ticket_id=ticket.id)
    assert wallet is not None
    assert wallet.ticket.event.custom_venue_name == "Buyer Updated Venue"

    messages: list[dict] = []
    monkeypatch.setattr("app.services.nearby_notifications.dispatch_templated_message", lambda *args, **kwargs: messages.append(kwargs))
    assert process_notification_jobs(db_session)["notifications_created"] == 1
    assert process_notification_jobs(db_session)["notifications_created"] == 0
    assert len(messages) == 1
    body = messages[0]["context"]["body"]
    assert "venue changed" in body
    assert "Buyer Updated Venue" in body
    assert "ticket remains valid" in body

    combined_venue = Venue(organizer_id=event.organizer_id, name="Combined Buyer Venue", address_line1="44 Combined Road")
    db_session.add(combined_venue)
    db_session.commit()
    combined = _payload(event, key="ticketed-combined-change-0001")
    combined.update({
        "venue_id": combined_venue.id,
        "custom_venue_name": None,
        "custom_address_text": None,
        "latitude": None,
        "longitude": None,
        "is_location_pinned": False,
    })
    with TestClient(app) as client:
        assert client.post(f"/events/organizer/events/{event.id}/reschedule", json=combined, headers=auth_headers(owner)).status_code == 200
    assert process_notification_jobs(db_session)["notifications_created"] == 1
    combined_body = messages[-1]["context"]["body"]
    assert "schedule changed" in combined_body
    assert "venue changed" in combined_body


def test_ticket_reschedule_is_idempotent_keeps_credentials_and_queues_one_notification(db_session: Session) -> None:
    owner = _user(db_session, "ticket-reschedule-owner")
    buyer = _user(db_session, "ticket-reschedule-buyer")
    event, tier = _event(db_session, owner)
    ticket = _issue_ticket(db_session, event=event, tier=tier, buyer=buyer)
    credentials = (ticket.ticket_code, ticket.manual_code, ticket.qr_payload, ticket.qr_token)
    payload = _payload(event, key="ticketed-reschedule-0001")

    with TestClient(app) as client:
        first = client.post(f"/events/organizer/events/{event.id}/reschedule", json=payload, headers=auth_headers(owner))
        second = client.post(f"/events/organizer/events/{event.id}/reschedule", json=payload, headers=auth_headers(owner))

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["notifications_required"] is True
    assert db_session.query(EventReschedule).filter_by(event_id=event.id).count() == 1
    assert db_session.query(NotificationJob).filter_by(job_type="event_reschedule").count() == 1
    db_session.refresh(ticket)
    assert (ticket.ticket_code, ticket.manual_code, ticket.qr_payload, ticket.qr_token) == credentials
    assert ticket.event.start_at.isoformat() == datetime.fromisoformat(payload["start_at"]).isoformat()
    wallet_ticket = get_wallet_ticket(db_session, user_id=buyer.id, ticket_id=ticket.id)
    assert wallet_ticket is not None
    assert wallet_ticket.display_status == "active"
    assert wallet_ticket.ticket.event.end_at.isoformat() == datetime.fromisoformat(payload["end_at"]).isoformat()

    summary = process_notification_jobs(db_session)
    assert summary["notifications_created"] == 1
    assert process_notification_jobs(db_session)["notifications_created"] == 0


def test_invalid_schedule_sales_and_reused_key_conflict(db_session: Session) -> None:
    owner = _user(db_session, "invalid-reschedule-owner")
    event, _ = _event(db_session, owner)
    payload = _payload(event, key="invalid-reuse-key")
    with TestClient(app) as client:
        invalid_range = client.post(
            f"/events/organizer/events/{event.id}/reschedule",
            json={**payload, "end_at": payload["start_at"]}, headers=auth_headers(owner),
        )
        invalid_sales = client.post(
            f"/events/organizer/events/{event.id}/reschedule",
            json={**payload, "sales_end_at": (datetime.fromisoformat(payload["start_at"]) + timedelta(hours=1)).isoformat()},
            headers=auth_headers(owner),
        )
        first = client.post(f"/events/organizer/events/{event.id}/reschedule", json=payload, headers=auth_headers(owner))
        conflict = client.post(
            f"/events/organizer/events/{event.id}/reschedule",
            json={**payload, "reason": "A different operation using the same key."}, headers=auth_headers(owner),
        )
    assert invalid_range.status_code == 422
    assert invalid_sales.status_code == 422
    assert first.status_code == 200
    assert conflict.status_code == 409


def test_reschedule_keeps_historical_reminders_and_future_due_times_use_new_schedule(db_session: Session) -> None:
    owner = _user(db_session, "reminder-reschedule-owner")
    buyer = _user(db_session, "reminder-reschedule-buyer")
    event, tier = _event(db_session, owner)
    _issue_ticket(db_session, event=event, tier=tier, buyer=buyer)
    from app.models.enums import ReminderType
    old_log = EventReminderLog(event_id=event.id, user_id=buyer.id, reminder_type=ReminderType.HOURS_24_BEFORE, sent_at=datetime.now(UTC))
    db_session.add(old_log)
    db_session.commit()
    payload = _payload(event, key="reminder-reschedule-0001")

    with TestClient(app) as client:
        response = client.post(f"/events/organizer/events/{event.id}/reschedule", json=payload, headers=auth_headers(owner))
    assert response.status_code == 200
    assert db_session.get(EventReminderLog, old_log.id) is not None
    db_session.refresh(event)
    from app.services.reminders import get_reminder_due_times_for_event
    assert get_reminder_due_times_for_event(event)[ReminderType.HOURS_1_BEFORE] == event.start_at - timedelta(hours=1)
