from __future__ import annotations

import logging
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.core.config import settings
from app.models.event import Event
from app.models.enums import ReminderType
from app.models.order import Order
from app.models.push_token import PushToken
from app.models.ticket import Ticket
from app.models.ticket_transfer_invite import TicketTransferInvite
from app.models.user import User

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class NotificationDispatchResult:
    success: bool
    channel_results: dict[str, str]


@dataclass(slots=True)
class EmailMessage:
    to_email: str
    subject: str
    body: str


@dataclass(slots=True)
class PushMessage:
    user_id: int
    title: str
    body: str
    data: dict[str, str]


def _send_email(message: EmailMessage) -> str:
    if not settings.email_notifications_enabled:
        return "skipped_disabled"
    provider = settings.email_provider
    if provider == "noop":
        return "skipped_noop"
    if provider == "mock":
        logger.info(
            "mock_email_sent",
            extra={"to_email": message.to_email, "subject": message.subject},
        )
        return "sent_mock"
    logger.warning(
        "email_provider_not_implemented",
        extra={"provider": provider, "to_email": message.to_email},
    )
    return "skipped_unconfigured"


def _send_push(db: Session, message: PushMessage) -> str:
    if not settings.push_notifications_enabled:
        return "skipped_disabled"
    provider = settings.push_provider
    if provider == "noop":
        return "skipped_noop"

    tokens = (
        db.execute(
            select(PushToken)
            .where(PushToken.user_id == message.user_id, PushToken.is_active.is_(True))
            .order_by(PushToken.id.asc())
        )
        .scalars()
        .all()
    )
    if not tokens:
        return "skipped_no_tokens"

    if provider == "mock":
        for token in tokens:
            logger.info(
                "mock_push_sent",
                extra={
                    "user_id": message.user_id,
                    "token_id": token.id,
                    "title": message.title,
                    "data": message.data,
                },
            )
        return f"sent_mock:{len(tokens)}"

    logger.warning(
        "push_provider_not_implemented",
        extra={"provider": provider, "user_id": message.user_id},
    )
    return "skipped_unconfigured"


def _dispatch(db: Session, *, email: EmailMessage | None = None, push: PushMessage | None = None) -> NotificationDispatchResult:
    channel_results: dict[str, str] = {}
    success = True

    if email is not None:
        try:
            channel_results["email"] = _send_email(email)
        except Exception:  # pragma: no cover - defensive
            logger.exception("email_dispatch_failed")
            channel_results["email"] = "failed"
            success = False

    if push is not None:
        try:
            channel_results["push"] = _send_push(db, push)
        except Exception:  # pragma: no cover - defensive
            logger.exception("push_dispatch_failed")
            channel_results["push"] = "failed"
            success = False

    return NotificationDispatchResult(success=success, channel_results=channel_results)


def _user_email(db: Session, user_id: int) -> str | None:
    return db.execute(select(User.email).where(User.id == user_id)).scalar_one_or_none()


def _order_event_label(order: Order) -> str:
    event_title = getattr(order.event, "title", None)
    return event_title or f"Event #{order.event_id}"


def notify_order_completed(db: Session, order: Order) -> NotificationDispatchResult:
    email = _user_email(db, order.user_id)
    event_label = _order_event_label(order)
    return _dispatch(
        db,
        email=EmailMessage(
            to_email=email,
            subject=f"Order #{order.id} confirmed",
            body=f"Your order #{order.id} for {event_label} has been confirmed.",
        ) if email else None,
        push=PushMessage(
            user_id=order.user_id,
            title="Order confirmed",
            body=f"Order #{order.id} is complete.",
            data={"type": "order_completed", "order_id": str(order.id), "event_id": str(order.event_id)},
        ),
    )


def notify_tickets_issued(db: Session, order: Order, tickets: list[Ticket]) -> NotificationDispatchResult:
    if not tickets:
        return NotificationDispatchResult(success=True, channel_results={"email": "skipped_no_tickets", "push": "skipped_no_tickets"})

    email = _user_email(db, order.user_id)
    quantity = len(tickets)
    first_ticket = tickets[0]
    return _dispatch(
        db,
        email=EmailMessage(
            to_email=email,
            subject=f"{quantity} ticket(s) issued for order #{order.id}",
            body=f"{quantity} ticket(s) are now available for your order #{order.id}.",
        ) if email else None,
        push=PushMessage(
            user_id=order.user_id,
            title="Tickets issued",
            body=f"{quantity} ticket(s) are ready.",
            data={
                "type": "tickets_issued",
                "order_id": str(order.id),
                "event_id": str(order.event_id),
                "ticket_id": str(first_ticket.id),
            },
        ),
    )


def notify_ticket_transferred(db: Session, ticket: Ticket, *, from_user_id: int, to_user_id: int) -> dict[str, NotificationDispatchResult]:
    sender_email = _user_email(db, from_user_id)
    receiver_email = _user_email(db, to_user_id)
    sender = _dispatch(
        db,
        email=EmailMessage(
            to_email=sender_email,
            subject=f"Ticket #{ticket.id} transferred",
            body=f"Ticket #{ticket.id} has been transferred successfully.",
        ) if sender_email else None,
        push=PushMessage(
            user_id=from_user_id,
            title="Ticket transferred",
            body=f"You transferred ticket #{ticket.id}.",
            data={"type": "ticket_transferred_out", "ticket_id": str(ticket.id), "event_id": str(ticket.event_id)},
        ),
    )
    recipient = _dispatch(
        db,
        email=EmailMessage(
            to_email=receiver_email,
            subject=f"You received ticket #{ticket.id}",
            body=f"Ticket #{ticket.id} was transferred to you.",
        ) if receiver_email else None,
        push=PushMessage(
            user_id=to_user_id,
            title="Ticket received",
            body=f"You now own ticket #{ticket.id}.",
            data={"type": "ticket_transferred_in", "ticket_id": str(ticket.id), "event_id": str(ticket.event_id)},
        ),
    )
    return {"sender": sender, "recipient": recipient}


def notify_ticket_voided(db: Session, ticket: Ticket, *, actor_user_id: int) -> NotificationDispatchResult:
    owner_email = _user_email(db, ticket.owner_user_id)
    _ = actor_user_id
    return _dispatch(
        db,
        email=EmailMessage(
            to_email=owner_email,
            subject=f"Ticket #{ticket.id} voided",
            body=f"Ticket #{ticket.id} is now voided and cannot be used.",
        ) if owner_email else None,
        push=PushMessage(
            user_id=ticket.owner_user_id,
            title="Ticket voided",
            body=f"Ticket #{ticket.id} is no longer valid.",
            data={"type": "ticket_voided", "ticket_id": str(ticket.id), "event_id": str(ticket.event_id)},
        ),
    )


def notify_ticket_transfer_invite_created(db: Session, invite: TicketTransferInvite) -> NotificationDispatchResult:
    recipient_email = invite.recipient_email
    if not recipient_email and invite.recipient_user_id:
        recipient_email = _user_email(db, invite.recipient_user_id)
    return _dispatch(
        db,
        email=EmailMessage(
            to_email=recipient_email,
            subject=f"Ticket transfer invite for ticket #{invite.ticket_id}",
            body=f"You have a pending invite for ticket #{invite.ticket_id}.",
        ) if recipient_email else None,
        push=PushMessage(
            user_id=invite.recipient_user_id,
            title="Ticket transfer invite",
            body=f"You have been invited to claim ticket #{invite.ticket_id}.",
            data={"type": "ticket_transfer_invite_created", "ticket_id": str(invite.ticket_id), "invite_token": invite.invite_token},
        ) if invite.recipient_user_id else None,
    )


def notify_ticket_transfer_invite_accepted(
    db: Session,
    invite: TicketTransferInvite,
    ticket: Ticket,
) -> dict[str, NotificationDispatchResult]:
    sender_email = _user_email(db, invite.sender_user_id)
    recipient_email = _user_email(db, ticket.owner_user_id)
    sender = _dispatch(
        db,
        email=EmailMessage(
            to_email=sender_email,
            subject=f"Transfer invite accepted for ticket #{ticket.id}",
            body=f"Your transfer invite for ticket #{ticket.id} was accepted.",
        ) if sender_email else None,
        push=PushMessage(
            user_id=invite.sender_user_id,
            title="Transfer accepted",
            body=f"Ticket #{ticket.id} transfer completed.",
            data={"type": "ticket_transfer_invite_accepted", "ticket_id": str(ticket.id), "invite_id": str(invite.id)},
        ),
    )
    recipient = _dispatch(
        db,
        email=EmailMessage(
            to_email=recipient_email,
            subject=f"You now own ticket #{ticket.id}",
            body=f"Ticket #{ticket.id} transfer is complete.",
        ) if recipient_email else None,
        push=PushMessage(
            user_id=ticket.owner_user_id,
            title="Ticket received",
            body=f"You now own ticket #{ticket.id}.",
            data={"type": "ticket_transfer_invite_claimed", "ticket_id": str(ticket.id), "invite_id": str(invite.id)},
        ),
    )
    return {"sender": sender, "recipient": recipient}


def notify_ticket_transfer_invite_revoked(db: Session, invite: TicketTransferInvite) -> NotificationDispatchResult:
    recipient_email = invite.recipient_email
    if not recipient_email and invite.recipient_user_id:
        recipient_email = _user_email(db, invite.recipient_user_id)
    return _dispatch(
        db,
        email=EmailMessage(
            to_email=recipient_email,
            subject=f"Transfer invite revoked for ticket #{invite.ticket_id}",
            body=f"Ticket transfer invite for ticket #{invite.ticket_id} has been revoked.",
        ) if recipient_email else None,
        push=PushMessage(
            user_id=invite.recipient_user_id,
            title="Transfer invite revoked",
            body=f"Invite for ticket #{invite.ticket_id} was revoked.",
            data={"type": "ticket_transfer_invite_revoked", "ticket_id": str(invite.ticket_id), "invite_id": str(invite.id)},
        ) if invite.recipient_user_id else None,
    )


def notify_order_cancelled(order: Order, *, actor_user_id: int) -> None:
    logger.info(
        "order_notification_cancelled",
        extra={
            "order_id": order.id,
            "event_id": order.event_id,
            "owner_user_id": order.user_id,
            "actor_user_id": actor_user_id,
        },
    )


def notify_order_refunded(order: Order, *, actor_user_id: int) -> NotificationDispatchResult:
    db = object_session(order)
    if db is None:
        raise ValueError("Order must be attached to an active session for notifications.")

    email = _user_email(db, order.user_id)
    _ = actor_user_id
    return _dispatch(
        db,
        email=EmailMessage(
            to_email=email,
            subject=f"Order #{order.id} refunded",
            body=f"Your order #{order.id} has been refunded.",
        ) if email else None,
        push=PushMessage(
            user_id=order.user_id,
            title="Order refunded",
            body=f"Order #{order.id} has been refunded.",
            data={"type": "order_refunded", "order_id": str(order.id), "event_id": str(order.event_id)},
        ),
    )


def notify_event_cancelled(event: Event, *, actor_user_id: int) -> NotificationDispatchResult:
    db = object_session(event)
    if db is None:
        raise ValueError("Event must be attached to an active session for notifications.")

    _ = actor_user_id
    order_user_ids = db.execute(select(Order.user_id).where(Order.event_id == event.id)).scalars().all()
    unique_user_ids = sorted(set(order_user_ids))
    last = NotificationDispatchResult(success=True, channel_results={})
    for user_id in unique_user_ids:
        email = _user_email(db, user_id)
        last = _dispatch(
            db,
            email=EmailMessage(
                to_email=email,
                subject=f"Event cancelled: {event.title}",
                body=f"The event '{event.title}' has been cancelled.",
            ) if email else None,
            push=PushMessage(
                user_id=user_id,
                title="Event cancelled",
                body=f"{event.title} has been cancelled.",
                data={"type": "event_cancelled", "event_id": str(event.id)},
            ),
        )
    return last


def register_push_token(db: Session, *, user_id: int, token: str, platform: str | None) -> PushToken:
    normalized = token.strip()
    existing = db.execute(select(PushToken).where(PushToken.token == normalized)).scalar_one_or_none()
    if existing is not None:
        existing.user_id = user_id
        existing.platform = platform
        existing.is_active = True
        db.flush()
        return existing

    push_token = PushToken(user_id=user_id, token=normalized, platform=platform, is_active=True)
    db.add(push_token)
    db.flush()
    return push_token


def deactivate_push_token(db: Session, *, user_id: int, token: str) -> bool:
    normalized = token.strip()
    push_token = db.execute(
        select(PushToken).where(PushToken.user_id == user_id, PushToken.token == normalized)
    ).scalar_one_or_none()
    if push_token is None:
        return False
    push_token.is_active = False
    db.flush()
    return True


def _to_aware(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _format_event_start_for_message(event: Event) -> str:
    return _to_aware(event.start_at).astimezone(ZoneInfo("America/Guyana")).strftime("%Y-%m-%d %H:%M %Z")


def _reminder_message(reminder_type: ReminderType) -> tuple[str, str]:
    if reminder_type == ReminderType.HOURS_24_BEFORE:
        return ("Your event is tomorrow", "starts tomorrow")
    if reminder_type == ReminderType.HOURS_3_BEFORE:
        return ("Your event starts in 3 hours", "starts in about 3 hours")
    return ("Your event starts soon", "starts in about 30 minutes")


def notify_event_reminder(
    db: Session,
    *,
    event: Event,
    user: User,
    reminder_type: ReminderType,
    ticket_count: int,
) -> NotificationDispatchResult:
    subject_prefix, body_phrase = _reminder_message(reminder_type)
    local_start = _format_event_start_for_message(event)
    email = EmailMessage(
        to_email=user.email,
        subject=f"{subject_prefix}: {event.title}",
        body=(
            f"{event.title} {body_phrase}. Start time: {local_start}. "
            f"You currently have {ticket_count} valid ticket(s)."
        ),
    ) if user.email else None

    push = PushMessage(
        user_id=user.id,
        title=subject_prefix,
        body=f"{event.title} starts at {local_start}.",
        data={
            "type": "event_reminder",
            "event_id": str(event.id),
            "reminder_type": reminder_type.value,
        },
    )
    return _dispatch(db, email=email, push=push)
