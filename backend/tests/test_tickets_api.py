from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.tickets import scan_ticket_qr
from app.schemas.ticket import TicketScanRequest


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
