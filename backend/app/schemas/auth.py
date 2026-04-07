from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    phone_number: str | None = None
    is_active: bool
    is_verified: bool
    is_admin: bool
    auth_provider: str
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str


class LoginRequest(BaseModel):
    email: str
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


class VerifyRequest(BaseModel):
    token: str


class VerifyResponse(BaseModel):
    success: bool


class RequestVerificationRequest(BaseModel):
    email: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
