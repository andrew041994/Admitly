from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, object_session

from app.models.event import Event
from app.models.enums import EventStatus, OrderStatus, TicketStatus
from app.models.ticket import Ticket
from app.services.tickets import get_active_pending_transfer_for_ticket
from app.services.ticket_holds import get_guyana_now


@dataclass
class WalletTicketView:
    ticket: Ticket
    event_is_upcoming: bool
    display_status: str
    is_valid_for_entry: bool
    can_display_entry_code: bool


def _to_timestamp(value: datetime | None) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        tz = get_guyana_now().tzinfo
        return value.replace(tzinfo=tz).timestamp()
    return value.timestamp()


def _is_event_upcoming(ticket: Ticket, now: datetime) -> bool:
    now_ts = _to_timestamp(now) or 0.0
    event_end_ts = _to_timestamp(ticket.event.end_at if ticket.event else None)
    if event_end_ts is not None:
        return event_end_ts >= now_ts
    event_start_ts = _to_timestamp(ticket.event.start_at if ticket.event else None)
    return bool(event_start_ts and event_start_ts >= now_ts)


def _derive_display_status(ticket: Ticket) -> str:
    db = object_session(ticket)
    if db is not None and get_active_pending_transfer_for_ticket(db, ticket_id=ticket.id) is not None:
        return "transfer_pending"
    if ticket.status == TicketStatus.CHECKED_IN:
        return "used"
    if ticket.status == TicketStatus.VOIDED:
        return "invalid"
    if ticket.order and ticket.order.refund_status == "refunded":
        return "invalid"
    if ticket.order and ticket.order.status in {OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.FAILED}:
        return "invalid"
    if ticket.event and ticket.event.status == EventStatus.CANCELLED:
        return "invalid"
    return "active"


def _is_valid_for_entry(ticket: Ticket, *, display_status: str) -> bool:
    return display_status == "active"


def _build_wallet_view(ticket: Ticket, *, now: datetime) -> WalletTicketView:
    is_upcoming = _is_event_upcoming(ticket, now)
    display_status = _derive_display_status(ticket)
    token_value = (ticket.qr_token or ticket.qr_payload or "").strip()
    can_display_entry_code = bool(token_value)
    return WalletTicketView(
        ticket=ticket,
        event_is_upcoming=is_upcoming,
        display_status=display_status,
        is_valid_for_entry=_is_valid_for_entry(ticket, display_status=display_status),
        can_display_entry_code=can_display_entry_code,
    )


def _wallet_sort_key(view: WalletTicketView) -> tuple[int, float, int]:
    start_at = view.ticket.event.start_at if view.ticket.event else None
    ts = _to_timestamp(start_at) or 0.0
    group_rank = 0 if view.event_is_upcoming else 1
    group_time = ts if view.event_is_upcoming else -ts
    return (group_rank, group_time, view.ticket.id)


def _base_wallet_query(user_id: int):
    return (
        select(Ticket)
        .where(Ticket.owner_user_id == user_id)
        .options(
            joinedload(Ticket.event).joinedload(Event.venue),
            joinedload(Ticket.event).joinedload(Event.organizer),
            joinedload(Ticket.ticket_tier),
            joinedload(Ticket.order),
        )
    )


def list_wallet_tickets(db: Session, *, user_id: int) -> list[WalletTicketView]:
    now = get_guyana_now()
    tickets = db.execute(_base_wallet_query(user_id)).scalars().unique().all()
    views = [_build_wallet_view(ticket, now=now) for ticket in tickets]
    views.sort(key=_wallet_sort_key)
    return views


def get_wallet_ticket(db: Session, *, user_id: int, ticket_id: int) -> WalletTicketView | None:
    ticket = db.execute(_base_wallet_query(user_id).where(Ticket.id == ticket_id)).scalars().unique().one_or_none()
    if ticket is None:
        return None
    return _build_wallet_view(ticket, now=get_guyana_now())
