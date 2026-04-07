from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from app.core.config import settings

_PASSWORD_SALT_BYTES = 16
_PASSWORD_ITERATIONS = 600_000


class TokenError(Exception):
    pass


def normalize_email(value: str) -> str:
    return value.strip().lower()


def _password_digest(password: str, salt_hex: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        _PASSWORD_ITERATIONS,
    )
    return digest.hex()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(_PASSWORD_SALT_BYTES)
    digest = _password_digest(password, salt)
    return f"pbkdf2_sha256${_PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, hashed_password: str | None) -> bool:
    if not hashed_password:
        return False
    try:
        algorithm, iterations_str, salt_hex, expected_digest = hashed_password.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iterations_str)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        iterations,
    ).hex()
    return hmac.compare_digest(digest, expected_digest)


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password must be at least 8 characters.")
    if password.lower() == password or password.upper() == password or not any(ch.isdigit() for ch in password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must include upper, lower, and numeric characters.",
        )


def _jwt_secret() -> str:
    return settings.jwt_secret


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(*, subject: str, token_type: str, expires_delta: timedelta, claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    if claims:
        payload.update(claims)
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(_jwt_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64url_encode(signature)}"


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
        signature = _b64url_decode(encoded_signature)
    except Exception as exc:  # noqa: BLE001
        raise TokenError("Invalid token.") from exc

    expected_signature = hmac.new(_jwt_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise TokenError("Invalid token.")

    try:
        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise TokenError("Invalid token.") from exc

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(datetime.now(timezone.utc).timestamp()):
        raise TokenError("Token expired.")

    if expected_type and payload.get("type") != expected_type:
        raise TokenError("Invalid token type.")
    return payload


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_urlsafe_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)
