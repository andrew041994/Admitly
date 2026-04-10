from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import create_token, normalize_email, utc_now
from app.db.base import Base
from app.models import EmailVerificationToken, PasswordResetToken, User
from app.services.auth import (
    authenticate_user,
    change_password,
    generate_email_verification_token,
    generate_password_reset_token,
    refresh_auth_tokens,
    register_user,
    reset_password_with_token,
    resolve_user_from_access_token,
    update_profile,
    verify_email_token,
)



def _seed_user(db: Session, suffix: str, *, password: str = "GoodPass123", is_active: bool = True) -> User:
    user, _ = register_user(db, email=f"USER-{suffix}@Example.COM", password=password, full_name="Auth User")
    user.is_active = is_active
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_registration_success_and_lowercasing(db_session: Session) -> None:
    user, tokens = register_user(db_session, email="Test@Example.COM", password="GoodPass123", full_name="Name")
    assert user.email == "test@example.com"
    assert user.is_verified is False
    assert user.auth_provider == "local"
    assert tokens.access_token


def test_registration_duplicate_email_rejected(db_session: Session) -> None:
    register_user(db_session, email="dup@example.com", password="GoodPass123", full_name="Name")
    with pytest.raises(HTTPException) as exc:
        register_user(db_session, email="Dup@example.com", password="GoodPass123", full_name="Name")
    assert exc.value.status_code == 409


def test_login_success_and_invalid_password(db_session: Session) -> None:
    user = _seed_user(db_session, "login")

    logged_in, _ = authenticate_user(db_session, email=user.email, password="GoodPass123")
    assert logged_in.last_login_at is not None

    with pytest.raises(HTTPException) as exc:
        authenticate_user(db_session, email=user.email, password="WrongPass123")
    assert exc.value.status_code == 401


def test_login_rejects_inactive(db_session: Session) -> None:
    user = _seed_user(db_session, "inactive", is_active=False)
    with pytest.raises(HTTPException) as exc:
        authenticate_user(db_session, email=user.email, password="GoodPass123")
    assert exc.value.status_code == 403


def test_access_token_resolution_success_and_failure(db_session: Session) -> None:
    user = _seed_user(db_session, "access")
    _, tokens = authenticate_user(db_session, email=user.email, password="GoodPass123")

    resolved = resolve_user_from_access_token(db_session, token=tokens.access_token)
    assert resolved.id == user.id

    with pytest.raises(HTTPException) as exc:
        resolve_user_from_access_token(db_session, token="bad-token")
    assert exc.value.status_code == 401


def test_refresh_token_flow(db_session: Session) -> None:
    user = _seed_user(db_session, "refresh")
    _, tokens = authenticate_user(db_session, email=user.email, password="GoodPass123")
    refreshed_user, refreshed_tokens = refresh_auth_tokens(db_session, refresh_token=tokens.refresh_token)
    assert refreshed_user.id == user.id
    assert refreshed_tokens.access_token


def test_email_verification_token_success_failure_and_expiry(db_session: Session) -> None:
    user = _seed_user(db_session, "verify")
    token = generate_email_verification_token(db_session, user=user)

    assert verify_email_token(db_session, token=token) is True
    assert verify_email_token(db_session, token=token) is False

    expired_token = generate_email_verification_token(db_session, user=user)
    row = db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash.is_not(None)).order_by(EmailVerificationToken.id.desc())
    ).scalars().first()
    assert row is not None
    row.expires_at = utc_now() - timedelta(seconds=1)
    db_session.add(row)
    db_session.commit()
    assert verify_email_token(db_session, token=expired_token) is False


def test_forgot_and_reset_password_success_failure_and_expiry(db_session: Session) -> None:
    user = _seed_user(db_session, "reset")
    token = generate_password_reset_token(db_session, user=user)
    assert reset_password_with_token(db_session, token=token, new_password="NewPass123") is True
    assert reset_password_with_token(db_session, token=token, new_password="Another123") is False

    expired = generate_password_reset_token(db_session, user=user)
    row = db_session.execute(select(PasswordResetToken).order_by(PasswordResetToken.id.desc())).scalars().first()
    assert row is not None
    row.expires_at = utc_now() - timedelta(seconds=1)
    db_session.add(row)
    db_session.commit()
    assert reset_password_with_token(db_session, token=expired, new_password="OtherPass123") is False


def test_change_password_success_and_failure(db_session: Session) -> None:
    user = _seed_user(db_session, "change")
    change_password(db_session, user=user, current_password="GoodPass123", new_password="BetterPass123")
    authenticate_user(db_session, email=user.email, password="BetterPass123")

    with pytest.raises(HTTPException) as exc:
        change_password(db_session, user=user, current_password="bad", new_password="NextPass123")
    assert exc.value.status_code == 401


def test_profile_update_behavior(db_session: Session) -> None:
    user = _seed_user(db_session, "profile")
    updated = update_profile(db_session, user=user, full_name="Updated Name", phone_number="+15550001111")
    assert updated.full_name == "Updated Name"
    assert updated.phone == "+15550001111"
    assert normalize_email(updated.email) == updated.email


def test_expired_refresh_token_rejected(db_session: Session) -> None:
    user = _seed_user(db_session, "refresh-expired")
    expired = create_token(subject=str(user.id), token_type="refresh", expires_delta=timedelta(seconds=-5))
    with pytest.raises(HTTPException) as exc:
        refresh_auth_tokens(db_session, refresh_token=expired)
    assert exc.value.status_code == 401
