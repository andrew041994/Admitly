from __future__ import annotations

import re


class InvalidPhoneNumberError(ValueError):
    """Raised when a phone number cannot be represented safely as E.164."""


_ALLOWED_PHONE_RE = re.compile(r"^[+0-9().\-\s]+$")


def normalize_phone_number(value: str | None, *, default_country_code: str = "592") -> str | None:
    """Normalize explicit international numbers and Guyana local numbers to E.164.

    Admitly currently operates in Guyana, so a seven-digit local number is treated as
    Guyanese. Other markets must provide an international ``+``/``00`` number. Ten
    digit North American numbers are retained for the legacy market data already in
    the application.
    """

    raw = (value or "").strip()
    if not raw:
        return None
    if not _ALLOWED_PHONE_RE.fullmatch(raw):
        raise InvalidPhoneNumberError("Enter a valid phone number.")

    explicit_international = raw.startswith("+") or raw.startswith("00")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if raw.startswith("00"):
        digits = digits[2:]
    elif not explicit_international:
        if len(digits) == 7:
            digits = f"{default_country_code}{digits}"
        elif len(digits) == 10:
            digits = f"1{digits}"
        else:
            raise InvalidPhoneNumberError(
                "Use a 7-digit Guyana number or include the international country code."
            )

    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise InvalidPhoneNumberError("Enter a valid international phone number.")
    return f"+{digits}"
