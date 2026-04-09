from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from io import BytesIO
from urllib.parse import quote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ticket import Ticket
from app.services.ticket_holds import get_guyana_now

QR_PAYLOAD_PREFIX = "admitly:ticket:"
QR_TOKEN_BYTES = 24
MAX_QR_TOKEN_GENERATION_ATTEMPTS = 10


def generate_ticket_qr_token() -> str:
    return secrets.token_urlsafe(QR_TOKEN_BYTES)


def generate_ticket_display_code(*, qr_token: str) -> str:
    normalized = "".join(ch for ch in qr_token.upper() if ch.isalnum())
    short = (normalized[:10] or secrets.token_hex(5).upper())
    return f"TKT-{short}"


def ensure_ticket_qr(db: Session, ticket: Ticket) -> Ticket:
    if ticket.qr_token:
        if not ticket.display_code:
            ticket.display_code = generate_ticket_display_code(qr_token=ticket.qr_token)
        return ticket

    now = get_guyana_now()
    for _ in range(MAX_QR_TOKEN_GENERATION_ATTEMPTS):
        qr_token = generate_ticket_qr_token()
        existing = db.execute(select(Ticket.id).where(Ticket.qr_token == qr_token)).scalar_one_or_none()
        if existing is not None:
            continue
        ticket.qr_token = qr_token
        ticket.qr_generated_at = ticket.qr_generated_at or now
        ticket.display_code = ticket.display_code or generate_ticket_display_code(qr_token=qr_token)
        ticket.qr_payload = ticket.qr_payload or qr_token
        return ticket
    raise RuntimeError("Unable to generate a unique ticket QR token.")


def get_ticket_qr_identity(ticket: Ticket) -> str:
    value = (ticket.qr_token or ticket.qr_payload or ticket.ticket_code or "").strip()
    if not value:
        raise ValueError("Ticket QR identity is missing.")
    return value


def build_ticket_qr_payload(ticket: Ticket) -> str:
    return f"{QR_PAYLOAD_PREFIX}{get_ticket_qr_identity(ticket)}"


def get_ticket_public_url(ticket: Ticket) -> str:
    base = settings.ticket_public_base_url.rstrip("/")
    token = quote(get_ticket_qr_identity(ticket), safe="")
    return f"{base}/t/{token}"


def get_ticket_qr_image_url(ticket: Ticket) -> str:
    return f"{get_ticket_public_url(ticket)}/qr"


def extract_ticket_lookup_value(value: str | None) -> str:
    lookup = (value or "").strip()
    if not lookup:
        return ""
    if lookup.startswith(QR_PAYLOAD_PREFIX):
        return lookup[len(QR_PAYLOAD_PREFIX) :].strip()

    parsed = urlparse(lookup)
    path = parsed.path.strip("/")
    if path.startswith("t/"):
        token = path.split("/", 2)[1].strip()
        return token
    return lookup


def generate_qr_png_bytes(payload: str) -> bytes:
    try:
        import qrcode
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("qrcode dependency is required to generate ticket QR images") from exc

    image = qrcode.make(payload)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def generate_ticket_qr_data_uri(ticket: Ticket) -> str:
    png = generate_qr_png_bytes(build_ticket_qr_payload(ticket))
    encoded = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _sign_ticket_payload(ticket_id: int, event_id: int) -> str:
    msg = f"{ticket_id}:{event_id}".encode("utf-8")
    signature = hmac.new(settings.jwt_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return signature


def generate_ticket_qr_payload(ticket: Ticket) -> dict[str, int | str]:
    return generate_signed_ticket_qr_payload(ticket_id=ticket.id, event_id=ticket.event_id)


def generate_signed_ticket_qr_payload(*, ticket_id: int, event_id: int) -> dict[str, int | str]:
    return {
        "ticket_id": ticket_id,
        "event_id": event_id,
        "hash": _sign_ticket_payload(ticket_id, event_id),
    }


def encode_ticket_qr_payload(ticket: Ticket) -> str:
    return json.dumps(generate_ticket_qr_payload(ticket), separators=(",", ":"), sort_keys=True)


def validate_ticket_qr_signature(payload: dict[str, object]) -> bool:
    ticket_id = payload.get("ticket_id")
    event_id = payload.get("event_id")
    provided_hash = payload.get("hash")
    if not isinstance(ticket_id, int) or not isinstance(event_id, int) or not isinstance(provided_hash, str):
        return False
    expected = _sign_ticket_payload(ticket_id, event_id)
    return hmac.compare_digest(expected, provided_hash)
