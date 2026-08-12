from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import secrets

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import TokenError, create_token, decode_token, utc_now
from app.models.auth_session import AuthSession
from app.models.user import User

logger = logging.getLogger(__name__)


@dataclass
class IssuedAuthTokens:
    access_token: str
    refresh_token: str
    access_expires_in_seconds: int
    refresh_expires_in_seconds: int


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _invalid_refresh() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")


def cleanup_stale_auth_sessions(db: Session) -> int:
    """Delete a bounded batch after the configured investigation-retention window."""
    cutoff = utc_now() - timedelta(days=settings.auth_session_retention_days)
    ids = list(
        db.execute(
            select(AuthSession.id)
            .where(
                or_(
                    AuthSession.expires_at < cutoff,
                    AuthSession.revoked_at < cutoff,
                )
            )
            .order_by(AuthSession.expires_at.asc())
            .limit(settings.auth_session_cleanup_batch_size)
        ).scalars()
    )
    if ids:
        db.execute(delete(AuthSession).where(AuthSession.id.in_(ids)))
    return len(ids)


def _issue_tokens(user: User, auth_session: AuthSession) -> IssuedAuthTokens:
    now = utc_now()
    access_exp = timedelta(minutes=settings.jwt_access_token_exp_minutes)
    refresh_seconds = max(1, int((_aware(auth_session.expires_at) - now).total_seconds()))
    refresh_exp = timedelta(seconds=refresh_seconds)
    access = create_token(
        subject=str(user.id),
        token_type="access",
        expires_delta=access_exp,
        claims={"email": user.email, "is_admin": user.is_admin, "sid": auth_session.id},
    )
    refresh = create_token(
        subject=str(user.id),
        token_type="refresh",
        expires_delta=refresh_exp,
        claims={"sid": auth_session.id},
    )
    auth_session.refresh_token_hash = _token_hash(refresh)
    return IssuedAuthTokens(
        access_token=access,
        refresh_token=refresh,
        access_expires_in_seconds=int(access_exp.total_seconds()),
        refresh_expires_in_seconds=refresh_seconds,
    )


def create_auth_session(db: Session, *, user: User) -> IssuedAuthTokens:
    cleanup_stale_auth_sessions(db)
    now = utc_now()
    session_id = secrets.token_urlsafe(32)
    auth_session = AuthSession(
        id=session_id,
        user_id=user.id,
        refresh_token_hash=hashlib.sha256(f"pending:{session_id}".encode()).hexdigest(),
        expires_at=now + timedelta(days=settings.jwt_refresh_token_exp_days),
    )
    tokens = _issue_tokens(user, auth_session)
    db.add(auth_session)
    logger.info("session_created", extra={"user_id": user.id, "auth_session_id": session_id})
    return tokens


def rotate_auth_session(db: Session, *, refresh_token: str) -> tuple[User, IssuedAuthTokens]:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise _invalid_refresh() from exc
    session_id = payload.get("sid")
    subject = payload.get("sub")
    if not isinstance(session_id, str) or not session_id or subject is None:
        # Legacy stateless refresh JWTs intentionally fail after the migration rollout.
        raise _invalid_refresh()
    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise _invalid_refresh() from exc

    auth_session = db.execute(
        select(AuthSession).where(AuthSession.id == session_id).with_for_update()
    ).scalar_one_or_none()
    if auth_session is None or auth_session.user_id != user_id:
        raise _invalid_refresh()
    if auth_session.revoked_at is not None:
        raise _invalid_refresh()

    supplied_hash = _token_hash(refresh_token)
    if not hmac.compare_digest(supplied_hash, auth_session.refresh_token_hash):
        auth_session.revoked_at = utc_now()
        auth_session.revocation_reason = "refresh_token_reuse"
        db.add(auth_session)
        db.commit()
        logger.warning(
            "session_reuse_detected",
            extra={"user_id": user_id, "auth_session_id": session_id},
        )
        raise _invalid_refresh()

    now = utc_now()
    if _aware(auth_session.expires_at) <= now:
        auth_session.revoked_at = now
        auth_session.revocation_reason = "expired"
        db.add(auth_session)
        db.commit()
        raise _invalid_refresh()

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        revoke_all_user_sessions(db, user_id=user_id, reason="account_inactive", commit=True)
        raise _invalid_refresh()

    cleanup_stale_auth_sessions(db)
    tokens = _issue_tokens(user, auth_session)
    auth_session.last_refreshed_at = now
    db.add(auth_session)
    db.commit()
    db.refresh(user)
    logger.info("session_refreshed", extra={"user_id": user_id, "auth_session_id": session_id})
    return user, tokens


def revoke_refresh_session(db: Session, *, refresh_token: str | None, reason: str = "logout") -> bool:
    if not refresh_token:
        return False
    try:
        payload = decode_token(
            refresh_token,
            expected_type="refresh",
            verify_expiration=False,
        )
    except TokenError:
        return False
    session_id = payload.get("sid")
    subject = payload.get("sub")
    if not isinstance(session_id, str) or subject is None:
        return False
    auth_session = db.execute(
        select(AuthSession).where(AuthSession.id == session_id).with_for_update()
    ).scalar_one_or_none()
    if auth_session is None or str(auth_session.user_id) != str(subject):
        return False
    if auth_session.revoked_at is None:
        auth_session.revoked_at = utc_now()
        auth_session.revocation_reason = reason[:64]
        db.add(auth_session)
        db.commit()
        logger.info(
            "session_revoked",
            extra={"user_id": auth_session.user_id, "auth_session_id": session_id, "revocation_reason": reason[:64]},
        )
    return True


def revoke_all_user_sessions(
    db: Session,
    *,
    user_id: int,
    reason: str,
    commit: bool = False,
) -> int:
    now = utc_now()
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason=reason[:64], updated_at=now)
    )
    count = int(result.rowcount or 0)
    if commit:
        db.commit()
    logger.info(
        "all_sessions_revoked",
        extra={"user_id": user_id, "session_count": count, "revocation_reason": reason[:64]},
    )
    return count
