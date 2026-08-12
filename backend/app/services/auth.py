from __future__ import annotations

import hashlib
from datetime import timedelta
import logging

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    TokenError,
    decode_token,
    generate_urlsafe_token,
    hash_password,
    utc_now,
    validate_password_strength,
    verify_password,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.models.verification_token import EmailVerificationToken
from app.lib.email_addresses import InvalidEmailAddressError, normalize_and_validate_email
from app.services.auth_sessions import (
    IssuedAuthTokens,
    create_auth_session,
    revoke_all_user_sessions,
    rotate_auth_session,
)

logger = logging.getLogger(__name__)



def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def register_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
) -> tuple[User, IssuedAuthTokens]:
    try:
        normalized = normalize_and_validate_email(email)
    except InvalidEmailAddressError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    existing = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")

    validate_password_strength(password)
    now = utc_now()
    user = User(
        email=normalized,
        full_name=full_name.strip(),
        hashed_password=hash_password(password),
        is_active=True,
        is_verified=False,
        is_admin=False,
        auth_provider="local",
        phone=None,
        email_verification_required_at=now,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account identity is already in use.") from exc
    tokens = create_auth_session(db, user=user)
    db.commit()
    db.refresh(user)
    return user, tokens


def authenticate_user(db: Session, *, email: str, password: str) -> tuple[User, IssuedAuthTokens]:
    try:
        normalized = normalize_and_validate_email(email)
    except InvalidEmailAddressError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    user = db.execute(select(User).where(User.email == normalized)).scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive.")

    user.last_login_at = utc_now()
    db.add(user)
    tokens = create_auth_session(db, user=user)
    db.commit()
    db.refresh(user)
    return user, tokens


def refresh_auth_tokens(db: Session, *, refresh_token: str) -> tuple[User, IssuedAuthTokens]:
    return rotate_auth_session(db, refresh_token=refresh_token)


def generate_email_verification_token(db: Session, *, user: User) -> str:
    raw = generate_urlsafe_token()
    expires_at = utc_now() + timedelta(hours=settings.verification_token_exp_hours)
    db.execute(
        update(EmailVerificationToken)
        .where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.is_active.is_(True),
        )
        .values(is_active=False, updated_at=utc_now())
    )
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
    if not token or len(token) > 512:
        return False
    token_hash = _token_hash(token)
    row = db.execute(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.token_hash == token_hash)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        return False
    if row.used_at is not None:
        return bool(row.user.is_verified)
    if not row.is_active or _is_expired(row.expires_at):
        return False
    if row.user.is_verified:
        row.used_at = utc_now()
        row.is_active = False
        db.commit()
        return True
    row.used_at = utc_now()
    row.is_active = False
    row.user.is_verified = True
    row.user.email_verified_at = row.used_at
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
    row = db.execute(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == token_hash)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or not row.is_active or _is_expired(row.expires_at):
        return False
    row.used_at = utc_now()
    row.is_active = False
    row.user.hashed_password = hash_password(new_password)
    revoked_count = revoke_all_user_sessions(
        db,
        user_id=row.user_id,
        reason="password_reset",
    )
    db.add(row)
    db.add(row.user)
    db.commit()
    logger.info(
        "password_reset_sessions_revoked",
        extra={"user_id": row.user_id, "session_count": revoked_count},
    )
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


def update_profile(db: Session, *, user: User, full_name: str) -> User:
    user.full_name = full_name.strip()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def requires_email_verification(user: User) -> bool:
    return user.email_verification_required_at is not None and not user.is_verified


def require_verified_email_access(user: User) -> User:
    if requires_email_verification(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verify your email before continuing.",
        )
    return user


def change_password(db: Session, *, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is invalid.")
    validate_password_strength(new_password)
    user.hashed_password = hash_password(new_password)
    revoked_count = revoke_all_user_sessions(
        db,
        user_id=user.id,
        reason="password_change",
    )
    db.add(user)
    db.commit()
    logger.info(
        "password_change_sessions_revoked",
        extra={"user_id": user.id, "session_count": revoked_count},
    )


def require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
