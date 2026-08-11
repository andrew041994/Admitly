from __future__ import annotations

import logging
import hashlib

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.rate_limit import apply_rate_limit, request_client_ip
from app.core.config import settings
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    AuthTokensResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutResponse,
    RefreshRequest,
    RegisterRequest,
    RequestVerificationRequest,
    ResetPasswordRequest,
    UserResponse,
    VerifyRequest,
    VerifyResponse,
)
from app.services.email import send_password_reset_email, send_verification_email
from app.services.auth import (
    authenticate_user,
    generate_email_verification_token,
    generate_password_reset_token,
    refresh_auth_tokens,
    register_user,
    reset_password_with_token,
    resolve_user_from_access_token,
    require_verified_email_access,
    requires_email_verification,
    verify_email_token,
)
from app.core.security import normalize_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

bearer_scheme = HTTPBearer(auto_error=False)


def _apply_auth_rate_limits(
    *, scope: str, identity_key: str, client_ip: str, limit: int, window_seconds: int
) -> None:
    # Limit both distributed attacks on one identity and one source rotating identities.
    apply_rate_limit(
        scope=f"{scope}_identity",
        key=identity_key,
        limit=limit,
        window_seconds=window_seconds,
    )
    apply_rate_limit(
        scope=f"{scope}_ip",
        key=client_ip,
        limit=limit,
        window_seconds=window_seconds,
    )


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_verified=user.is_verified,
        email_verified_at=user.email_verified_at,
        requires_email_verification=requires_email_verification(user),
        is_admin=user.is_admin,
        auth_provider=user.auth_provider,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


def _to_auth_response(user: User, tokens: AuthTokensResponse) -> AuthResponse:
    return AuthResponse(user=_to_user_response(user), tokens=tokens)


def get_authenticated_user(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return resolve_user_from_access_token(db, token=credentials.credentials)


def get_current_user(current_user: User = Depends(get_authenticated_user)) -> User:
    return require_verified_email_access(current_user)


def get_current_user_id(current_user: User = Depends(get_current_user)) -> int:
    """Return the verified Bearer-token principal's database user ID."""
    return current_user.id


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require current database-backed administrator authorization."""
    if not current_user.is_admin:
        logger.warning("Admin authorization denied", extra={"user_id": current_user.id})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return current_user


def get_current_admin_id(current_user: User = Depends(get_current_admin)) -> int:
    return current_user.id


def _deliver_verification_email(user: User, token: str) -> None:
    try:
        delivery_status = send_verification_email(user.email, token)
        logger.info(
            "Verification email delivery processed",
            extra={"user_id": user.id, "delivery_status": delivery_status},
        )
    except Exception:
        logger.exception(
            "Verification email delivery failed",
            extra={"user_id": user.id, "email_provider": "configured"},
        )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    client_ip: str = Depends(request_client_ip),
) -> AuthResponse:
    email_key = hashlib.sha256(normalize_email(payload.email).encode("utf-8")).hexdigest()
    _apply_auth_rate_limits(
        scope="auth_signup",
        identity_key=email_key,
        client_ip=client_ip,
        limit=settings.rate_limit_signup_count,
        window_seconds=settings.rate_limit_signup_window_seconds,
    )
    user, issued = register_user(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )
    verification_token = generate_email_verification_token(db, user=user)
    _deliver_verification_email(user, verification_token)
    return _to_auth_response(
        user,
        AuthTokensResponse(
            access_token=issued.access_token,
            refresh_token=issued.refresh_token,
            access_expires_in_seconds=issued.access_expires_in_seconds,
            refresh_expires_in_seconds=issued.refresh_expires_in_seconds,
        ),
    )


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    client_ip: str = Depends(request_client_ip),
) -> AuthResponse:
    email_key = hashlib.sha256(normalize_email(payload.email).encode("utf-8")).hexdigest()
    _apply_auth_rate_limits(
        scope="auth_login",
        identity_key=email_key,
        client_ip=client_ip,
        limit=settings.rate_limit_login_count,
        window_seconds=settings.rate_limit_login_window_seconds,
    )
    user, issued = authenticate_user(db, email=payload.email, password=payload.password)
    return _to_auth_response(
        user,
        AuthTokensResponse(
            access_token=issued.access_token,
            refresh_token=issued.refresh_token,
            access_expires_in_seconds=issued.access_expires_in_seconds,
            refresh_expires_in_seconds=issued.refresh_expires_in_seconds,
        ),
    )


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
    client_ip: str = Depends(request_client_ip),
) -> AuthResponse:
    token_key = hashlib.sha256(payload.refresh_token.encode("utf-8")).hexdigest()
    _apply_auth_rate_limits(
        scope="auth_refresh",
        identity_key=token_key,
        client_ip=client_ip,
        limit=settings.rate_limit_login_count,
        window_seconds=settings.rate_limit_login_window_seconds,
    )
    user, issued = refresh_auth_tokens(db, refresh_token=payload.refresh_token)
    return _to_auth_response(
        user,
        AuthTokensResponse(
            access_token=issued.access_token,
            refresh_token=issued.refresh_token,
            access_expires_in_seconds=issued.access_expires_in_seconds,
            refresh_expires_in_seconds=issued.refresh_expires_in_seconds,
        ),
    )


@router.post("/logout", response_model=LogoutResponse)
def logout() -> LogoutResponse:
    return LogoutResponse(success=True)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_authenticated_user)) -> UserResponse:
    return _to_user_response(current_user)


@router.post("/request-verification", response_model=VerifyResponse)
def request_verification(
    payload: RequestVerificationRequest,
    db: Session = Depends(get_db),
    client_ip: str = Depends(request_client_ip),
) -> VerifyResponse:
    email = normalize_email(payload.email)
    email_key = hashlib.sha256(email.encode("utf-8")).hexdigest()
    _apply_auth_rate_limits(
        scope="email_verification_resend",
        identity_key=email_key,
        client_ip=client_ip,
        limit=settings.rate_limit_verification_resend_count,
        window_seconds=settings.rate_limit_verification_resend_window_seconds,
    )
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None and user.is_active and not user.is_verified:
        token = generate_email_verification_token(db, user=user)
        _deliver_verification_email(user, token)
    return VerifyResponse(success=True)


@router.post("/verify", response_model=VerifyResponse)
def verify(
    payload: VerifyRequest,
    db: Session = Depends(get_db),
    client_ip: str = Depends(request_client_ip),
) -> VerifyResponse:
    token_key = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    _apply_auth_rate_limits(
        scope="auth_verification_submit",
        identity_key=token_key,
        client_ip=client_ip,
        limit=settings.rate_limit_password_reset_count,
        window_seconds=settings.rate_limit_password_reset_window_seconds,
    )
    success = verify_email_token(db, token=payload.token)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token.")
    return VerifyResponse(success=True)


@router.post("/forgot-password", response_model=VerifyResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    client_ip: str = Depends(request_client_ip),
) -> VerifyResponse:
    email = normalize_email(payload.email)
    email_key = hashlib.sha256(email.encode("utf-8")).hexdigest()
    _apply_auth_rate_limits(
        scope="auth_password_reset_request",
        identity_key=email_key,
        client_ip=client_ip,
        limit=settings.rate_limit_password_reset_count,
        window_seconds=settings.rate_limit_password_reset_window_seconds,
    )
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None and user.is_active:
        token = generate_password_reset_token(db, user=user)
        try:
            delivery_status = send_password_reset_email(user.email, token)
            logger.info(
                "Password reset email delivery processed",
                extra={"user_id": user.id, "delivery_status": delivery_status},
            )
        except Exception:
            logger.exception(
                "Password reset email delivery failed",
                extra={"user_id": user.id, "email_provider": "configured"},
            )
    return VerifyResponse(success=True)


@router.post("/reset-password", response_model=VerifyResponse)
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    client_ip: str = Depends(request_client_ip),
) -> VerifyResponse:
    token_key = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    _apply_auth_rate_limits(
        scope="auth_password_reset_submit",
        identity_key=token_key,
        client_ip=client_ip,
        limit=settings.rate_limit_password_reset_count,
        window_seconds=settings.rate_limit_password_reset_window_seconds,
    )
    success = reset_password_with_token(db, token=payload.token, new_password=payload.new_password)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")
    return VerifyResponse(success=True)
