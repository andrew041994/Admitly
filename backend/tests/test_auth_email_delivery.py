from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.api import auth as auth_api
from app.models import User
from app.schemas.auth import ForgotPasswordRequest, RequestVerificationRequest
from app.services.auth import register_user
from app.services import email as email_service
from app.services.email import EmailConfigurationError, send_email


def _seed_user(db: Session, suffix: str, *, is_verified: bool = False, is_active: bool = True) -> User:
    user, _ = register_user(
        db,
        email=f"email-{suffix}@example.com",
        password="GoodPass123",
        full_name="Email User",
    )
    user.is_verified = is_verified
    user.is_active = is_active
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_request_verification_for_existing_unverified_user_calls_email_sender(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _seed_user(db_session, "verify")
    calls: list[tuple[str, str]] = []

    def fake_send(to_email: str, token: str) -> str:
        calls.append((to_email, token))
        return "sent_mock"

    monkeypatch.setattr(auth_api, "send_verification_email", fake_send)

    response = auth_api.request_verification(RequestVerificationRequest(email=user.email), db=db_session)

    assert response.success is True
    assert len(calls) == 1
    assert calls[0][0] == user.email
    assert calls[0][1]


def test_request_verification_for_unknown_email_returns_success_without_sending(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(auth_api, "send_verification_email", lambda to_email, token: calls.append((to_email, token)))

    response = auth_api.request_verification(RequestVerificationRequest(email="unknown@example.com"), db=db_session)

    assert response.success is True
    assert calls == []


def test_forgot_password_for_existing_active_user_calls_email_sender(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _seed_user(db_session, "reset")
    calls: list[tuple[str, str]] = []

    def fake_send(to_email: str, token: str) -> str:
        calls.append((to_email, token))
        return "sent_mock"

    monkeypatch.setattr(auth_api, "send_password_reset_email", fake_send)

    response = auth_api.forgot_password(ForgotPasswordRequest(email=user.email), db=db_session)

    assert response.success is True
    assert len(calls) == 1
    assert calls[0][0] == user.email
    assert calls[0][1]


def test_forgot_password_for_unknown_email_returns_success_without_sending(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(auth_api, "send_password_reset_email", lambda to_email, token: calls.append((to_email, token)))

    response = auth_api.forgot_password(ForgotPasswordRequest(email="unknown-reset@example.com"), db=db_session)

    assert response.success is True
    assert calls == []


def test_noop_email_provider_skips_delivery_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.email.settings.email_notifications_enabled", True)
    monkeypatch.setattr("app.services.email.settings.email_provider", "noop")

    assert send_email("user@example.com", "Subject", "Body") == "skipped_noop"


def test_smtp_missing_config_raises_safe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.email.settings.email_notifications_enabled", True)
    monkeypatch.setattr("app.services.email.settings.email_provider", "smtp")
    monkeypatch.setattr("app.services.email.settings.smtp_host", None)
    monkeypatch.setattr("app.services.email.settings.email_from_address", None)

    with pytest.raises(EmailConfigurationError) as exc:
        send_email("user@example.com", "Subject", "secret-token-body")

    message = str(exc.value)
    assert "SMTP_HOST" in message
    assert "EMAIL_FROM_ADDRESS" in message
    assert "secret-token-body" not in message
    assert "user@example.com" not in message


def test_smtp_missing_config_is_swallowed_by_auth_endpoint_for_existing_user(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = _seed_user(db_session, "smtp-safe")

    def fail_send(to_email: str, token: str) -> str:
        raise EmailConfigurationError("SMTP email delivery is missing required setting(s): SMTP_HOST")

    monkeypatch.setattr(auth_api, "send_password_reset_email", fail_send)

    response = auth_api.forgot_password(ForgotPasswordRequest(email=user.email), db=db_session)

    assert response.success is True


def test_password_reset_email_uses_clickable_web_link_and_plain_code_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, str] = {}

    def fake_send_email(to_email: str, subject: str, body: str) -> str:
        sent["to_email"] = to_email
        sent["subject"] = subject
        sent["body"] = body
        return "sent_mock"

    monkeypatch.setattr(email_service.settings, "frontend_base_url", "https://admitlyevents.com")
    monkeypatch.setattr(email_service, "send_email", fake_send_email)

    status = email_service.send_password_reset_email("user@example.com", "reset-token-123")

    assert status == "sent_mock"
    assert sent["to_email"] == "user@example.com"
    assert sent["subject"] == "Reset your Admitly password"
    assert "https://admitlyevents.com/reset-password?token=reset-token-123" in sent["body"]
    assert "Tap this link on your phone to open Admitly and reset your password." in sent["body"]
    assert "If the app does not open, copy and paste this reset code into the Reset Password screen." in sent["body"]
    assert "reset-token-123" in sent["body"]
    assert "admitly://reset-password" not in sent["body"]
