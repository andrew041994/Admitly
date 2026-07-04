from __future__ import annotations

import json
import logging
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import settings

logger = logging.getLogger(__name__)

SENDGRID_MAIL_SEND_URL = "https://api.sendgrid.com/v3/mail/send"
SENDGRID_TIMEOUT_SECONDS = 15


class EmailConfigurationError(RuntimeError):
    """Raised when email delivery is enabled but required provider settings are missing."""


def _provider() -> str:
    return (settings.email_provider or "noop").strip().lower()


def _require_smtp_config() -> tuple[str, int, str]:
    missing: list[str] = []
    if not settings.smtp_host:
        missing.append("SMTP_HOST")
    if not settings.email_from_address:
        missing.append("EMAIL_FROM_ADDRESS")
    if missing:
        raise EmailConfigurationError(f"SMTP email delivery is missing required setting(s): {', '.join(missing)}")
    return settings.smtp_host, settings.smtp_port, settings.email_from_address


def _require_sendgrid_config() -> tuple[str, str]:
    missing: list[str] = []
    if not settings.sendgrid_api_key:
        missing.append("SENDGRID_API_KEY")
    if not settings.email_from_address:
        missing.append("EMAIL_FROM_ADDRESS")
    if missing:
        raise EmailConfigurationError(f"SendGrid email delivery is missing required setting(s): {', '.join(missing)}")
    return settings.sendgrid_api_key, settings.email_from_address


def _send_sendgrid_email(to_email: str, subject: str, body: str) -> str:
    api_key, from_address = _require_sendgrid_config()
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_address},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    request = Request(
        SENDGRID_MAIL_SEND_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=SENDGRID_TIMEOUT_SECONDS) as response:
            status_code = response.getcode()
    except Exception as exc:
        status_code = getattr(exc, "code", None)
        if status_code is not None:
            raise EmailConfigurationError(f"SendGrid email delivery failed with status {status_code}") from exc
        raise EmailConfigurationError("SendGrid email delivery failed") from exc

    if 200 <= status_code < 300:
        return "sent_sendgrid"
    raise EmailConfigurationError(f"SendGrid email delivery failed with status {status_code}")


def send_email(to_email: str, subject: str, body: str) -> str:
    """Send a plain-text email using the configured provider.

    Return values are stable status strings so callers and tests can distinguish
    skipped delivery from successful delivery without exposing secrets or tokens.
    """
    if not settings.email_notifications_enabled:
        return "skipped_disabled"

    provider = _provider()
    if provider == "noop":
        return "skipped_noop"

    if provider == "mock":
        logger.info(
            "Mock email delivery accepted",
            extra={"email_provider": provider, "subject": subject, "body_length": len(body)},
        )
        return "sent_mock"

    if provider == "smtp":
        smtp_host, smtp_port, from_address = _require_smtp_config()
        message = EmailMessage()
        message["From"] = from_address
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                if not settings.smtp_password:
                    raise EmailConfigurationError("SMTP email delivery is missing required setting(s): SMTP_PASSWORD")
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return "sent_smtp"

    if provider == "sendgrid":
        return _send_sendgrid_email(to_email, subject, body)

    raise EmailConfigurationError(
        f"Unsupported email provider: {settings.email_provider}. Supported providers: noop, mock, smtp, sendgrid"
    )


def _base_url_with_path(base_url: str, path: str) -> str:
    if base_url.endswith("://"):
        return f"{base_url}{path.lstrip('/')}"
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def send_verification_email(to_email: str, token: str) -> str:
    link = f"{settings.frontend_base_url.rstrip('/')}/verify-email?token={token}"
    body = (
        "Welcome to Admitly!\n\n"
        "Verify your account by opening this link:\n"
        f"{link}\n\n"
        "If the link does not work, paste this verification code into the app:\n"
        f"{token}\n\n"
        "If you did not request this email, you can safely ignore it."
    )
    return send_email(to_email, "Verify your Admitly account", body)


def send_password_reset_email(to_email: str, token: str) -> str:
    link = f"{_base_url_with_path(settings.frontend_base_url, 'reset-password')}?{urlencode({'token': token})}"
    body = (
        "We received a request to reset your Admitly password.\n\n"
        "Tap this link on your phone to open Admitly and reset your password.\n"
        f"{link}\n\n"
        "If the app does not open, copy and paste this reset code into the Reset Password screen.\n"
        f"{token}\n\n"
        f"This link and code expire in {settings.password_reset_token_exp_minutes} minutes.\n\n"
        "If you did not request a password reset, you can safely ignore this email."
    )
    return send_email(to_email, "Reset your Admitly password", body)
