from __future__ import annotations

import logging

from app.models.ticket import Ticket

logger = logging.getLogger(__name__)


def notify_ticket_issued(ticket: Ticket) -> None:
    logger.info(
        "ticket_notification_issued",
        extra={"ticket_id": ticket.id, "event_id": ticket.event_id, "owner_user_id": ticket.owner_user_id},
    )


def notify_ticket_transferred(ticket: Ticket, *, from_user_id: int, to_user_id: int) -> None:
    logger.info(
        "ticket_notification_transferred",
        extra={
            "ticket_id": ticket.id,
            "event_id": ticket.event_id,
            "from_user_id": from_user_id,
            "to_user_id": to_user_id,
        },
    )


def notify_ticket_voided(ticket: Ticket, *, actor_user_id: int) -> None:
    logger.info(
        "ticket_notification_voided",
        extra={
            "ticket_id": ticket.id,
            "event_id": ticket.event_id,
            "owner_user_id": ticket.owner_user_id,
            "actor_user_id": actor_user_id,
        },
    )
