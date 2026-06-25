from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.tickets import manual_event_ticket_check_in, scan_ticket_qr
from app.models import Ticket
from app.models.enums import TicketStatus
from app.models.ticket_check_in_attempt import TicketCheckInAttempt
from app.schemas.ticket import TicketCheckInValidateRequest, TicketScanRequest
from app.services.tickets import CHECK_IN_METHOD_MANUAL, issue_tickets_for_completed_order
from tests.test_tickets_service import _seed_order


def test_scan_ticket_qr_commits_successful_scan(monkeypatch) -> None:
    class _FakeDb:
        def __init__(self) -> None:
            self.commit_calls = 0

        def commit(self) -> None:
            self.commit_calls += 1

    expected_checked_in_at = datetime.now(timezone.utc)

    monkeypatch.setattr(
        "app.api.tickets.scan_ticket",
        lambda db, *, payload, user_id: SimpleNamespace(
            status="SUCCESS",
            ticket_id=123,
            checked_in_at=expected_checked_in_at,
            message="Ticket checked in successfully.",
        ),
    )

    db = _FakeDb()
    response = scan_ticket_qr(
        payload=TicketScanRequest(payload={"ticket_id": 123, "event_id": 99, "hash": "signed"}),
        db=db,
        user_id=456,
    )

    assert db.commit_calls == 1
    assert response.status == "SUCCESS"
    assert response.ticket_id == 123
    assert response.checked_in_at == expected_checked_in_at


def test_scan_ticket_qr_rejects_outside_scan_window_without_commit(monkeypatch) -> None:
    class _FakeDb:
        def __init__(self) -> None:
            self.commit_calls = 0

        def commit(self) -> None:
            self.commit_calls += 1

    monkeypatch.setattr(
        "app.api.tickets.scan_ticket",
        lambda db, *, payload, user_id: SimpleNamespace(
            status="INVALID",
            ticket_id=None,
            checked_in_at=None,
            message="Ticket scanning has closed for this event.",
        ),
    )

    db = _FakeDb()
    with pytest.raises(HTTPException) as exc:
        scan_ticket_qr(
            payload=TicketScanRequest(payload={"ticket_id": 123, "event_id": 99, "hash": "signed"}),
            db=db,
            user_id=456,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Ticket scanning has closed for this event."
    assert db.commit_calls == 0


def test_manual_event_ticket_check_in_commits_successful_admission(db_session: Session) -> None:
    order, _, _, _, event = _seed_order(db_session, quantity=1)
    ticket = issue_tickets_for_completed_order(db_session, order)[0]
    ticket.manual_code = "ADM-123456"
    db_session.commit()
    ticket_id = ticket.id
    scanner_user_id = event.organizer.user_id
    event_id = event.id

    response = manual_event_ticket_check_in(
        event_id=event_id,
        payload=TicketCheckInValidateRequest(ticket_code="ADM-123456"),
        db=db_session,
        user_id=scanner_user_id,
    )

    assert response.success is True
    assert response.code == "admitted"
    assert response.ticket_id == ticket_id
    assert response.checked_in_by_user_id == scanner_user_id

    db_session.expire_all()
    persisted_ticket = db_session.get(Ticket, ticket_id)
    assert persisted_ticket is not None
    assert persisted_ticket.status == TicketStatus.CHECKED_IN
    assert persisted_ticket.checked_in_at is not None
    assert persisted_ticket.checked_in_by_user_id == scanner_user_id
    assert persisted_ticket.check_in_method == CHECK_IN_METHOD_MANUAL

    attempt = db_session.execute(
        select(TicketCheckInAttempt).where(
            TicketCheckInAttempt.ticket_id == ticket_id,
            TicketCheckInAttempt.event_id == event_id,
            TicketCheckInAttempt.actor_user_id == scanner_user_id,
            TicketCheckInAttempt.method == CHECK_IN_METHOD_MANUAL,
        )
    ).scalar_one_or_none()
    assert attempt is not None

    duplicate_response = manual_event_ticket_check_in(
        event_id=event_id,
        payload=TicketCheckInValidateRequest(ticket_code="ADM-123456"),
        db=db_session,
        user_id=scanner_user_id,
    )

    assert duplicate_response.success is False
    assert duplicate_response.code == "already_used"
