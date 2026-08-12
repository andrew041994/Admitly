from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.lib.email_addresses import InvalidEmailAddressError, normalize_and_validate_email


class NormalizedEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("Enter a valid email address.")
        try:
            return normalize_and_validate_email(value)
        except InvalidEmailAddressError as exc:
            raise ValueError(str(exc)) from exc


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    is_active: bool
    is_verified: bool
    email_verified_at: datetime | None
    requires_email_verification: bool
    is_admin: bool
    auth_provider: str
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None
    creator_age_identity_verification_status: str


class RegisterRequest(NormalizedEmailRequest):
    password: str
    full_name: str


class LoginRequest(NormalizedEmailRequest):
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AuthTokensResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_in_seconds: int
    refresh_expires_in_seconds: int


class AuthResponse(BaseModel):
    user: UserResponse
    tokens: AuthTokensResponse


class LogoutResponse(BaseModel):
    success: bool
    revoked_sessions: int = 0


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class VerifyRequest(BaseModel):
    token: str


class VerifyResponse(BaseModel):
    success: bool


class RequestVerificationRequest(NormalizedEmailRequest):
    pass


class ForgotPasswordRequest(NormalizedEmailRequest):
    pass


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
