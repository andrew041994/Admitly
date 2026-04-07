from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
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
from app.services.auth import (
    authenticate_user,
    generate_email_verification_token,
    generate_password_reset_token,
    refresh_auth_tokens,
    register_user,
    reset_password_with_token,
    resolve_user_from_access_token,
    verify_email_token,
)
from app.core.security import normalize_email

router = APIRouter(prefix="/auth", tags=["auth"])

bearer_scheme = HTTPBearer(auto_error=False)


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone_number=user.phone,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_admin=user.is_admin,
        auth_provider=user.auth_provider,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


def _to_auth_response(user: User, tokens: AuthTokensResponse) -> AuthResponse:
    return AuthResponse(user=_to_user_response(user), tokens=tokens)


def get_current_user(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return resolve_user_from_access_token(db, token=credentials.credentials)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user, issued = register_user(db, email=payload.email, password=payload.password, full_name=payload.full_name)
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
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
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
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> AuthResponse:
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
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _to_user_response(current_user)


@router.post("/request-verification", response_model=VerifyResponse)
def request_verification(payload: RequestVerificationRequest, db: Session = Depends(get_db)) -> VerifyResponse:
    email = normalize_email(payload.email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None and user.is_active and not user.is_verified:
        # Token generation is in place; email delivery wiring can be plugged in later.
        generate_email_verification_token(db, user=user)
    return VerifyResponse(success=True)


@router.post("/verify", response_model=VerifyResponse)
def verify(payload: VerifyRequest, db: Session = Depends(get_db)) -> VerifyResponse:
    success = verify_email_token(db, token=payload.token)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token.")
    return VerifyResponse(success=True)


@router.post("/forgot-password", response_model=VerifyResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> VerifyResponse:
    email = normalize_email(payload.email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None and user.is_active:
        # Token generation is in place; email delivery wiring can be plugged in later.
        generate_password_reset_token(db, user=user)
    return VerifyResponse(success=True)


@router.post("/reset-password", response_model=VerifyResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> VerifyResponse:
    success = reset_password_with_token(db, token=payload.token, new_password=payload.new_password)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token.")
    return VerifyResponse(success=True)
