from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_admin
from app.api import auth as auth_api
from app.core.security import create_token, decode_token, utc_now
from app.models import AuthSession, User
from app.schemas.auth import LogoutRequest
from app.services.auth import (
    authenticate_user,
    change_password,
    generate_password_reset_token,
    refresh_auth_tokens,
    register_user,
    reset_password_with_token,
)
from app.services.auth_sessions import revoke_all_user_sessions, revoke_refresh_session


def seed(db: Session, suffix: str) -> tuple[User, object]:
    return register_user(
        db,
        email=f"session-{suffix}@example.com",
        password="GoodPass123",
        full_name="Session User",
    )


def session_for_token(db: Session, token: str) -> AuthSession:
    payload = decode_token(token, expected_type="refresh")
    return db.get(AuthSession, payload["sid"])


def assert_refresh_rejected(db: Session, token: str) -> None:
    with pytest.raises(HTTPException) as exc:
        refresh_auth_tokens(db, refresh_token=token)
    assert exc.value.status_code == 401


def test_login_creates_hashed_session_and_session_bound_jtis(db_session: Session) -> None:
    user, _ = seed(db_session, "login")
    _, tokens = authenticate_user(db_session, email=user.email, password="GoodPass123")
    refresh_claims = decode_token(tokens.refresh_token, expected_type="refresh")
    access_claims = decode_token(tokens.access_token, expected_type="access")
    row = db_session.get(AuthSession, refresh_claims["sid"])
    assert row is not None
    assert row.user_id == user.id
    assert row.revoked_at is None
    assert row.refresh_token_hash != tokens.refresh_token
    assert len(row.refresh_token_hash) == 64
    assert access_claims["sid"] == row.id
    assert access_claims["jti"]
    assert refresh_claims["jti"]


def test_refresh_rotates_and_reuse_revokes_family(db_session: Session) -> None:
    _, original = seed(db_session, "rotation")
    user, rotated = refresh_auth_tokens(db_session, refresh_token=original.refresh_token)
    assert user.id
    assert rotated.refresh_token != original.refresh_token
    row = session_for_token(db_session, rotated.refresh_token)
    rotated_hash = row.refresh_token_hash
    assert row.last_refreshed_at is not None

    assert_refresh_rejected(db_session, original.refresh_token)
    db_session.refresh(row)
    assert row.revoked_at is not None
    assert row.revocation_reason == "refresh_token_reuse"
    assert row.refresh_token_hash == rotated_hash
    assert_refresh_rejected(db_session, rotated.refresh_token)


def test_revoked_expired_and_session_mismatch_refreshes_fail(db_session: Session) -> None:
    user, tokens = seed(db_session, "invalid-states")
    row = session_for_token(db_session, tokens.refresh_token)
    assert revoke_refresh_session(db_session, refresh_token=tokens.refresh_token, reason="test") is True
    assert_refresh_rejected(db_session, tokens.refresh_token)

    _, expired_tokens = authenticate_user(db_session, email=user.email, password="GoodPass123")
    expired_row = session_for_token(db_session, expired_tokens.refresh_token)
    expired_row.expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    assert_refresh_rejected(db_session, expired_tokens.refresh_token)
    db_session.refresh(expired_row)
    assert expired_row.revocation_reason == "expired"

    _, mismatch_tokens = authenticate_user(db_session, email=user.email, password="GoodPass123")
    mismatch_row = session_for_token(db_session, mismatch_tokens.refresh_token)
    signed_mismatch = create_token(
        subject=str(user.id),
        token_type="refresh",
        expires_delta=timedelta(minutes=5),
        claims={"sid": mismatch_row.id},
    )
    assert_refresh_rejected(db_session, signed_mismatch)
    db_session.refresh(mismatch_row)
    assert mismatch_row.revocation_reason == "refresh_token_reuse"


def test_current_logout_is_idempotent_and_blocks_refresh(db_session: Session) -> None:
    _, tokens = seed(db_session, "logout")
    assert revoke_refresh_session(db_session, refresh_token=tokens.refresh_token) is True
    assert revoke_refresh_session(db_session, refresh_token=tokens.refresh_token) is True
    assert_refresh_rejected(db_session, tokens.refresh_token)


def test_logout_endpoints_revoke_current_and_all_sessions(db_session: Session) -> None:
    user, first = seed(db_session, "logout-api")
    response = auth_api.logout(LogoutRequest(refresh_token=first.refresh_token), db=db_session)
    assert response.success is True
    assert response.revoked_sessions == 1
    repeated = auth_api.logout(LogoutRequest(refresh_token=first.refresh_token), db=db_session)
    assert repeated.success is True

    _, second = authenticate_user(db_session, email=user.email, password="GoodPass123")
    _, third = authenticate_user(db_session, email=user.email, password="GoodPass123")
    all_response = auth_api.logout_all(db=db_session, current_user=user)
    assert all_response.revoked_sessions == 2
    assert_refresh_rejected(db_session, second.refresh_token)
    assert_refresh_rejected(db_session, third.refresh_token)


def test_logout_all_revokes_every_active_family(db_session: Session) -> None:
    user, first = seed(db_session, "logout-all")
    _, second = authenticate_user(db_session, email=user.email, password="GoodPass123")
    assert revoke_all_user_sessions(db_session, user_id=user.id, reason="logout_all", commit=True) == 2
    assert_refresh_rejected(db_session, first.refresh_token)
    assert_refresh_rejected(db_session, second.refresh_token)


def test_password_reset_revokes_sessions_and_changes_credentials(db_session: Session) -> None:
    user, first = seed(db_session, "reset")
    _, second = authenticate_user(db_session, email=user.email, password="GoodPass123")
    reset_token = generate_password_reset_token(db_session, user=user)
    assert reset_password_with_token(db_session, token=reset_token, new_password="NewPass123") is True
    assert reset_password_with_token(db_session, token=reset_token, new_password="OtherPass123") is False
    assert_refresh_rejected(db_session, first.refresh_token)
    assert_refresh_rejected(db_session, second.refresh_token)
    with pytest.raises(HTTPException):
        authenticate_user(db_session, email=user.email, password="GoodPass123")
    authenticate_user(db_session, email=user.email, password="NewPass123")


def test_password_change_revokes_all_sessions_and_requires_new_login(db_session: Session) -> None:
    user, first = seed(db_session, "change")
    _, second = authenticate_user(db_session, email=user.email, password="GoodPass123")
    change_password(db_session, user=user, current_password="GoodPass123", new_password="BetterPass123")
    assert_refresh_rejected(db_session, first.refresh_token)
    assert_refresh_rejected(db_session, second.refresh_token)
    with pytest.raises(HTTPException):
        authenticate_user(db_session, email=user.email, password="GoodPass123")
    authenticate_user(db_session, email=user.email, password="BetterPass123")


def test_inactive_user_cannot_login_or_refresh_and_sessions_are_revoked(db_session: Session) -> None:
    user, tokens = seed(db_session, "inactive")
    user.is_active = False
    db_session.commit()
    assert_refresh_rejected(db_session, tokens.refresh_token)
    row = session_for_token(db_session, tokens.refresh_token)
    assert row.revocation_reason == "account_inactive"
    with pytest.raises(HTTPException) as exc:
        authenticate_user(db_session, email=user.email, password="GoodPass123")
    assert exc.value.status_code == 403


def test_admin_authorization_uses_current_database_state(db_session: Session) -> None:
    user, _ = seed(db_session, "admin-state")
    user.is_admin = True
    db_session.commit()
    assert get_current_admin(user) is user
    user.is_admin = False
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        get_current_admin(user)
    assert exc.value.status_code == 403


def test_legacy_refresh_without_session_id_fails_safely(db_session: Session) -> None:
    user, _ = seed(db_session, "legacy")
    legacy = create_token(
        subject=str(user.id),
        token_type="refresh",
        expires_delta=timedelta(days=1),
    )
    assert_refresh_rejected(db_session, legacy)


def test_repeated_rotation_never_creates_duplicate_session_rows(db_session: Session) -> None:
    user, tokens = seed(db_session, "single-family")
    _, rotated = refresh_auth_tokens(db_session, refresh_token=tokens.refresh_token)
    _, rotated_again = refresh_auth_tokens(db_session, refresh_token=rotated.refresh_token)
    assert rotated_again.refresh_token != rotated.refresh_token
    count = db_session.scalar(select(func.count(AuthSession.id)).where(AuthSession.user_id == user.id))
    assert count == 1
