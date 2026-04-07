from __future__ import annotations

import base64
from io import BytesIO
from urllib.parse import quote, urlparse


from app.core.config import settings
from app.models.ticket import Ticket


def get_ticket_qr_identity(ticket: Ticket) -> str:
    value = (ticket.qr_payload or ticket.ticket_code or "").strip()
    if not value:
        raise ValueError("Ticket QR identity is missing.")
    return value


def get_ticket_public_url(ticket: Ticket) -> str:
    base = settings.ticket_public_base_url.rstrip("/")
    token = quote(get_ticket_qr_identity(ticket), safe="")
    return f"{base}/t/{token}"


def get_ticket_qr_image_url(ticket: Ticket) -> str:
    return f"{get_ticket_public_url(ticket)}/qr"


def build_ticket_qr_payload(ticket: Ticket) -> str:
    return get_ticket_public_url(ticket)


def extract_ticket_lookup_value(value: str | None) -> str:
    lookup = (value or "").strip()
    if not lookup:
        return ""
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
