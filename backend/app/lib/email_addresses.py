from __future__ import annotations

from pydantic import EmailStr, TypeAdapter, ValidationError


class InvalidEmailAddressError(ValueError):
    pass


_email_adapter = TypeAdapter(EmailStr)


def normalize_and_validate_email(value: str | None) -> str:
    candidate = (value or "").strip()
    try:
        validated = str(_email_adapter.validate_python(candidate))
    except ValidationError as exc:
        raise InvalidEmailAddressError("Enter a valid email address.") from exc
    # Admitly authentication already treats addresses case-insensitively.
    return validated.lower()
