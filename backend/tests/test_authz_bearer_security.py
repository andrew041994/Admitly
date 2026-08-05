from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.security import create_token
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.schemas.order import CreatePendingOrderFromHoldsRequest
from app.schemas.ticket import TicketScanRequest
from app.schemas.ticket_hold import CreateTicketHoldRequest
from tests.utils import auth_headers, unique_email


def _seed_user(db: Session, prefix: str, *, is_admin: bool = False) -> User:
    user = User(
        email=unique_email(prefix),
        full_name=prefix.title(),
        hashed_password="unused",
        is_active=True,
        is_verified=True,
        is_admin=is_admin,
        auth_provider="local",
    )
    db.add(user)
    db.flush()
    return user


def _client(db: Session) -> TestClient:
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_protected_route_requires_valid_bearer_and_ignores_legacy_identity_header(db_session: Session) -> None:
    owner = _seed_user(db_session, "bearer-owner")
    other = _seed_user(db_session, "header-other")

    with _client(db_session) as client:
        assert client.get("/account/profile").status_code == 401
        assert client.get("/account/profile", headers={"X-User-Id": str(owner.id)}).status_code == 401
        assert client.get("/account/profile", headers={"Authorization": "Bearer malformed"}).status_code == 401

        expired = create_token(subject=str(owner.id), token_type="access", expires_delta=timedelta(seconds=-5))
        assert client.get("/account/profile", headers={"Authorization": f"Bearer {expired}"}).status_code == 401

        headers = {**auth_headers(owner), "X-User-Id": str(other.id)}
        response = client.get("/account/profile", headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] == owner.id

    app.dependency_overrides.clear()


def test_admin_authorization_uses_current_database_user_not_client_flags(db_session: Session) -> None:
    normal = _seed_user(db_session, "normal-user")
    admin = _seed_user(db_session, "admin-user", is_admin=True)
    admin_headers = auth_headers(admin)

    with _client(db_session) as client:
        assert client.get("/events/admin/pending-approval").status_code == 401
        assert client.get(
            "/events/admin/pending-approval",
            headers={**auth_headers(normal), "X-Is-Admin": "true", "X-User-Id": str(admin.id)},
        ).status_code == 403
        assert client.get("/events/admin/pending-approval", headers=admin_headers).status_code == 200

        admin.is_admin = False
        db_session.flush()
        assert client.get("/events/admin/pending-approval", headers=admin_headers).status_code == 403

    app.dependency_overrides.clear()


def test_verification_gate_and_legacy_transition_apply_through_bearer_dependency(db_session: Session) -> None:
    new_unverified = _seed_user(db_session, "new-unverified")
    new_unverified.is_verified = False
    from app.core.security import utc_now

    new_unverified.email_verification_required_at = utc_now()
    legacy = _seed_user(db_session, "legacy-unverified")
    legacy.is_verified = False
    legacy.email_verification_required_at = None
    db_session.flush()

    with _client(db_session) as client:
        assert client.get("/account/profile", headers=auth_headers(new_unverified)).status_code == 403
        assert client.get("/account/profile", headers=auth_headers(legacy)).status_code == 200
        assert client.get("/events/discover").status_code == 200

    app.dependency_overrides.clear()


def test_identity_fields_are_rejected_by_ownership_sensitive_request_schemas() -> None:
    with pytest.raises(ValidationError):
        CreateTicketHoldRequest(ticket_tier_id=1, quantity=1, user_id=999)
    with pytest.raises(ValidationError):
        CreatePendingOrderFromHoldsRequest(hold_ids=[1], user_id=999)
    with pytest.raises(ValidationError):
        TicketScanRequest(payload="ticket", scanned_by_user_id=999)
