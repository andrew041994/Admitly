from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    generate_urlsafe_token,
    hash_password,
    normalize_email,
    utc_now,
    validate_password_strength,
    verify_password,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.models.verification_token import EmailVerificationToken


@dataclass
class IssuedAuthTokens:
    access_token: str
    refresh_token: str
    access_expires_in_seconds: int
    refresh_expires_in_seconds: int



def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _issue_auth_tokens(user: User) -> IssuedAuthTokens:
    access_exp = timedelta(minutes=settings.jwt_access_token_exp_minutes)
    refresh_exp = timedelta(days=settings.jwt_refresh_token_exp_days)
    access = create_token(
        subject=str(user.id),
        token_type="access",
        expires_delta=access_exp,
        claims={"email": user.email, "is_admin": user.is_admin},
    )
    refresh = create_token(subject=str(user.id), token_type="refresh", expires_delta=refresh_exp)
    return IssuedAuthTokens(
        access_token=access,
        refresh_token=refresh,
        access_expires_in_seconds=int(access_exp.total_seconds()),
        refresh_expires_in_seconds=int(refresh_exp.total_seconds()),
    )


def register_user(db: Session, *, email: str, password: str, full_name: str) -> tuple[User, IssuedAuthTokens]:
    normalized = normalize_email(email)
    existing = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")

    validate_password_strength(password)
    user = User(
        email=normalized,
        full_name=full_name.strip(),
        hashed_password=hash_password(password),
        is_active=True,
        is_verified=False,
        is_admin=False,
        auth_provider="local",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, _issue_auth_tokens(user)


def authenticate_user(db: Session, *, email: str, password: str) -> tuple[User, IssuedAuthTokens]:
    normalized = normalize_email(email)
    user = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive.")

    user.last_login_at = utc_now()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, _issue_auth_tokens(user)


def refresh_auth_tokens(db: Session, *, refresh_token: str) -> tuple[User, IssuedAuthTokens]:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.") from exc
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")
    user = db.get(User, int(sub))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")
    return user, _issue_auth_tokens(user)


def generate_email_verification_token(db: Session, *, user: User) -> str:
    raw = generate_urlsafe_token()
    expires_at = utc_now() + timedelta(hours=settings.verification_token_exp_hours)
    token = EmailVerificationToken(user_id=user.id, token_hash=_token_hash(raw), expires_at=expires_at, is_active=True)
    db.add(token)
    db.commit()
    return raw


def _is_expired(expires_at) -> bool:
    now = utc_now()
    if getattr(expires_at, "tzinfo", None) is None:
        return expires_at < now.replace(tzinfo=None)
    return expires_at < now


def verify_email_token(db: Session, *, token: str) -> bool:
    token_hash = _token_hash(token)
    row = db.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or not row.is_active or _is_expired(row.expires_at):
        return False
    row.used_at = utc_now()
    row.is_active = False
    row.user.is_verified = True
    db.add(row)
    db.add(row.user)
    db.commit()
    return True


def generate_password_reset_token(db: Session, *, user: User) -> str:
    raw = generate_urlsafe_token()
    expires_at = utc_now() + timedelta(minutes=settings.password_reset_token_exp_minutes)
    token = PasswordResetToken(user_id=user.id, token_hash=_token_hash(raw), expires_at=expires_at, is_active=True)
    db.add(token)
    db.commit()
    return raw


def reset_password_with_token(db: Session, *, token: str, new_password: str) -> bool:
    validate_password_strength(new_password)
    token_hash = _token_hash(token)
    row = db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)).scalar_one_or_none()
    if row is None or row.used_at is not None or not row.is_active or _is_expired(row.expires_at):
        return False
    row.used_at = utc_now()
    row.is_active = False
    row.user.hashed_password = hash_password(new_password)
    db.add(row)
    db.add(row.user)
    db.commit()
    return True


def resolve_user_from_access_token(db: Session, *, token: str) -> User:
    try:
        payload = decode_token(token, expected_type="access")
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.") from exc
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.")
    user = db.get(User, int(sub))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.")
    return user


def update_profile(db: Session, *, user: User, full_name: str, phone_number: str | None) -> User:
    user.full_name = full_name.strip()
    user.phone = phone_number.strip() if phone_number else None
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, *, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is invalid.")
    validate_password_strength(new_password)
    user.hashed_password = hash_password(new_password)
    db.add(user)
    db.commit()


def require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
