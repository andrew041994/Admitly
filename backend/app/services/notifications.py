from __future__ import annotations

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dataclasses import dataclass
from datetime import timezone
from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from app.core.config import settings
from app.models.event import Event
from app.models.dispute import Dispute
from app.models.enums import MessageChannel, MessageTemplateType, ReminderType
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.push_token import PushToken
from app.models.ticket import Ticket
from app.models.ticket_transfer_invite import TicketTransferInvite
from app.models.user import User
from app.services.messaging import dispatch_templated_message
from app.services.ticket_qr import get_ticket_public_url
from app.services.notification_center import create_user_notification, utc_now

logger = logging.getLogger(__name__)


def _mask_log_email(value: str) -> str:
    local, _, domain = value.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


class NotificationEventType(str, Enum):
    ORDER_COMPLETED = "order_completed"
    REFUND_PROCESSED = "refund_processed"
    EVENT_CANCELLED = "event_cancelled"
    TICKET_TRANSFER_RECEIVED = "ticket_transfer_received"
    TICKET_TRANSFER_ACCEPTED = "ticket_transfer_accepted"
    DISPUTE_RESOLVED = "dispute_resolved"
    EVENT_TOMORROW_REMINDER = "event_tomorrow_reminder"
    EVENT_TODAY_REMINDER = "event_today_reminder"
    EVENT_STARTING_SOON_REMINDER = "event_starting_soon_reminder"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    PUSH = "push"


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


def get_notification_channels(event_type: NotificationEventType) -> tuple[NotificationChannel, ...]:
    if event_type in {
        NotificationEventType.ORDER_COMPLETED,
        NotificationEventType.REFUND_PROCESSED,
    }:
        return (NotificationChannel.EMAIL, NotificationChannel.PUSH)
    if event_type in {
        NotificationEventType.EVENT_CANCELLED,
        NotificationEventType.DISPUTE_RESOLVED,
    }:
        return (NotificationChannel.EMAIL, NotificationChannel.PUSH)
    if event_type in {
        NotificationEventType.TICKET_TRANSFER_RECEIVED,
        NotificationEventType.TICKET_TRANSFER_ACCEPTED,
        NotificationEventType.EVENT_TOMORROW_REMINDER,
        NotificationEventType.EVENT_TODAY_REMINDER,
        NotificationEventType.EVENT_STARTING_SOON_REMINDER,
    }:
        return (NotificationChannel.PUSH,)
    return tuple()


def should_send_email(event_type: NotificationEventType) -> bool:
    return NotificationChannel.EMAIL in get_notification_channels(event_type)


def should_send_push(event_type: NotificationEventType) -> bool:
    return NotificationChannel.PUSH in get_notification_channels(event_type)


def _send_email(message: EmailMessage) -> str:
    if not settings.email_notifications_enabled:
        return "skipped_disabled"
    provider = settings.email_provider
    if provider == "noop":
        return "skipped_noop"
    if provider == "mock":
        logger.info(
            "mock_email_sent",
            extra={"to_email": _mask_log_email(message.to_email), "subject": message.subject},
        )
        return "sent_mock"
    logger.warning(
        "email_provider_not_implemented",
        extra={"provider": provider, "to_email": _mask_log_email(message.to_email)},
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


def dispatch_notification_event(
    db: Session,
    *,
    event_type: NotificationEventType,
    email: EmailMessage | None = None,
    push: PushMessage | None = None,
) -> NotificationDispatchResult:
    return _dispatch(
        db,
        email=email if should_send_email(event_type) else None,
        push=push if should_send_push(event_type) else None,
    )


def notify_order_completed(db: Session, order: Order) -> NotificationDispatchResult:
    email = _user_email(db, order.user_id)
    event_label = _order_event_label(order)
    result = dispatch_templated_message(
        db,
        template_type=MessageTemplateType.ORDER_CONFIRMATION,
        channels=(MessageChannel.EMAIL,),
        recipient_user_id=order.user_id,
        recipient_email=email,
        related_entity_type="order",
        related_entity_id=order.id,
        context={"order_id": str(order.id), "event_id": str(order.event_id), "event_title": event_label},
    )
    result.channel_results["push"] = "handled_by_ticket_delivery"
    return NotificationDispatchResult(success=result.success, channel_results=result.channel_results)


def notify_tickets_issued(db: Session, order: Order, tickets: list[Ticket]) -> NotificationDispatchResult:
    if not tickets:
        return NotificationDispatchResult(success=True, channel_results={"email": "skipped_no_tickets", "push": "skipped_no_tickets"})

    email = _user_email(db, order.user_id)
    quantity = len(tickets)
    ticket_lines = "\n".join(f"- Ticket #{ticket.id}: {get_ticket_public_url(ticket)}" for ticket in tickets)
    result = dispatch_templated_message(
        db,
        template_type=MessageTemplateType.TICKET_ISSUED,
        channels=(MessageChannel.EMAIL,),
        recipient_user_id=order.user_id,
        recipient_email=email,
        related_entity_type="order",
        related_entity_id=order.id,
        context={
            "quantity": str(quantity),
            "order_id": str(order.id),
            "event_id": str(order.event_id),
            "email_body": (
                f"{quantity} ticket(s) are now available for your order #{order.id}.\n\n"
                f"Ticket access links:\n{ticket_lines}"
            ),
        },
    )
    expected_quantity = int(db.execute(
        select(func.coalesce(func.sum(OrderItem.quantity), 0)).where(OrderItem.order_id == order.id)
    ).scalar_one())
    if quantity == expected_quantity:
        event_label = _order_event_label(order)
        create_user_notification(
            db,
            user_id=order.user_id,
            notification_type="ticket_purchase_completed",
            title="Tickets ready",
            body=f"{quantity} ticket(s) for {event_label} are now in your wallet.",
            dedupe_key=f"order:{order.id}:tickets-issued",
            route_key="wallet",
            route_params={"order_id": order.id, "event_id": order.event_id},
            related_entity_type="order",
            related_entity_id=order.id,
        )
        result.channel_results["push"] = "queued_durable"
    else:
        result.channel_results["push"] = "deferred_until_order_fulfilled"
    return NotificationDispatchResult(success=result.success, channel_results=result.channel_results)


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
    result = dispatch_templated_message(
        db,
        template_type=MessageTemplateType.TRANSFER_INVITE,
        channels=(MessageChannel.EMAIL,),
        recipient_user_id=invite.recipient_user_id,
        recipient_email=recipient_email,
        related_entity_type="transfer_invite",
        related_entity_id=invite.id,
        context={
            "ticket_id": str(invite.ticket_id),
        },
        idempotency_key=f"transfer:{invite.id}:created",
    )
    if invite.recipient_user_id is not None:
        ticket = db.get(Ticket, invite.ticket_id)
        event = db.get(Event, ticket.event_id) if ticket is not None else None
        event_label = event.title if event is not None else "an event"
        create_user_notification(
            db,
            user_id=invite.recipient_user_id,
            notification_type="ticket_received",
            title="Ticket transfer awaiting you",
            body=f"A ticket for {event_label} is waiting for your acceptance.",
            dedupe_key=f"transfer:{invite.id}:created",
            route_key="transfers",
            route_params={"transfer_id": invite.id, "ticket_id": invite.ticket_id},
            related_entity_type="transfer",
            related_entity_id=invite.id,
        )
        result.channel_results["push"] = "queued_durable"
    return NotificationDispatchResult(success=result.success, channel_results=result.channel_results)


def notify_ticket_transfer_invite_accepted(
    db: Session,
    invite: TicketTransferInvite,
    ticket: Ticket,
) -> dict[str, NotificationDispatchResult]:
    event = db.get(Event, ticket.event_id)
    event_label = event.title if event is not None else "the event"
    create_user_notification(
        db,
        user_id=invite.sender_user_id,
        notification_type="ticket_transfer_accepted",
        title="Transfer accepted",
        body=f"Your ticket transfer for {event_label} was accepted.",
        dedupe_key=f"transfer:{invite.id}:accepted",
        route_key="transfers",
        route_params={"transfer_id": invite.id, "event_id": ticket.event_id},
        related_entity_type="transfer",
        related_entity_id=invite.id,
    )
    queued = NotificationDispatchResult(success=True, channel_results={"push": "queued_durable"})
    return {"sender": queued, "recipient": NotificationDispatchResult(success=True, channel_results={"push": "not_required"})}


def notify_ticket_transfer_canceled(db: Session, invite: TicketTransferInvite) -> NotificationDispatchResult:
    recipient_email = invite.recipient_email
    if not recipient_email and invite.recipient_user_id:
        recipient_email = _user_email(db, invite.recipient_user_id)
    result = _dispatch(
        db,
        email=EmailMessage(
            to_email=recipient_email,
            subject=f"Transfer canceled for ticket #{invite.ticket_id}",
            body=f"The pending transfer for ticket #{invite.ticket_id} was canceled.",
        ) if recipient_email else None,
        push=None,
    )
    if invite.recipient_user_id is not None:
        ticket = db.get(Ticket, invite.ticket_id)
        event = db.get(Event, ticket.event_id) if ticket is not None else None
        create_user_notification(
            db,
            user_id=invite.recipient_user_id,
            notification_type="ticket_transfer_canceled",
            title="Transfer canceled",
            body=f"The ticket transfer for {event.title if event else 'the event'} is no longer available.",
            dedupe_key=f"transfer:{invite.id}:canceled",
            route_key="transfers",
            route_params={"transfer_id": invite.id, "ticket_id": invite.ticket_id},
            related_entity_type="transfer",
            related_entity_id=invite.id,
        )
        result.channel_results["push"] = "queued_durable"
    return result


def notify_ticket_transfer_invite_declined(db: Session, invite: TicketTransferInvite) -> NotificationDispatchResult:
    ticket = db.get(Ticket, invite.ticket_id)
    event = db.get(Event, ticket.event_id) if ticket is not None else None
    create_user_notification(
        db,
        user_id=invite.sender_user_id,
        notification_type="ticket_transfer_declined",
        title="Transfer declined",
        body=f"Your ticket transfer for {event.title if event else 'the event'} was declined.",
        dedupe_key=f"transfer:{invite.id}:declined",
        route_key="transfers",
        route_params={"transfer_id": invite.id, "ticket_id": invite.ticket_id},
        related_entity_type="transfer",
        related_entity_id=invite.id,
    )
    return NotificationDispatchResult(success=True, channel_results={"push": "queued_durable"})


def notify_ticket_transfer_expired(db: Session, invite: TicketTransferInvite) -> dict[str, NotificationDispatchResult]:
    sender = _dispatch(
        db,
        push=PushMessage(
            user_id=invite.sender_user_id,
            title="Transfer expired",
            body=f"The transfer for ticket #{invite.ticket_id} expired.",
            data={"type": "ticket_transfer_expired", "ticket_id": str(invite.ticket_id), "transfer_id": str(invite.id)},
        ),
    )
    recipient = _dispatch(
        db,
        push=PushMessage(
            user_id=invite.recipient_user_id,
            title="Transfer expired",
            body=f"The transfer for ticket #{invite.ticket_id} expired.",
            data={"type": "ticket_transfer_expired", "ticket_id": str(invite.ticket_id), "transfer_id": str(invite.id)},
        ) if invite.recipient_user_id else None,
    )
    return {"sender": sender, "recipient": recipient}


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
    result = dispatch_templated_message(
        db,
        template_type=MessageTemplateType.REFUND_PROCESSED,
        channels=(MessageChannel.EMAIL, MessageChannel.PUSH),
        recipient_user_id=order.user_id,
        recipient_email=email,
        related_entity_type="order",
        related_entity_id=order.id,
        context={"order_id": str(order.id), "event_id": str(order.event_id)},
    )
    return NotificationDispatchResult(success=result.success, channel_results=result.channel_results)


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
        last = dispatch_notification_event(
            db,
            event_type=NotificationEventType.EVENT_CANCELLED,
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


def register_push_token(
    db: Session,
    *,
    user_id: int,
    token: str,
    platform: str | None,
    installation_id: str | None = None,
) -> PushToken:
    normalized = token.strip()
    normalized_installation = (installation_id or "").strip() or None
    by_token = db.execute(select(PushToken).where(PushToken.token == normalized)).scalar_one_or_none()
    by_installation = (
        db.execute(select(PushToken).where(PushToken.installation_id == normalized_installation)).scalar_one_or_none()
        if normalized_installation is not None
        else None
    )
    if by_token is not None and by_installation is not None and by_token.id != by_installation.id:
        by_installation.installation_id = None
        by_installation.is_active = False
        by_installation.disabled_reason = "token_rotated"
        db.flush()
    existing = by_token or by_installation
    if existing is not None:
        existing.user_id = user_id
        existing.token = normalized
        existing.installation_id = normalized_installation
        existing.platform = platform
        existing.is_active = True
        existing.disabled_reason = None
        existing.last_registered_at = utc_now()
        db.flush()
        return existing

    push_token = PushToken(
        user_id=user_id,
        token=normalized,
        installation_id=normalized_installation,
        platform=platform,
        is_active=True,
        last_registered_at=utc_now(),
    )
    db.add(push_token)
    db.flush()
    return push_token


def deactivate_push_token(
    db: Session,
    *,
    user_id: int,
    token: str | None = None,
    installation_id: str | None = None,
) -> bool:
    normalized = (token or "").strip() or None
    normalized_installation = (installation_id or "").strip() or None
    push_token = db.execute(
        select(PushToken).where(
            PushToken.user_id == user_id,
            ((PushToken.token == normalized) if normalized else (PushToken.installation_id == normalized_installation)),
        )
    ).scalars().first()
    if push_token is None:
        return False
    push_token.is_active = False
    push_token.disabled_reason = "logout_or_user_disabled"
    db.flush()
    return True


def _to_aware(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _format_event_start_for_message(event: Event) -> str:
    try:
        event_timezone = ZoneInfo(event.timezone or "America/Guyana")
    except ZoneInfoNotFoundError:
        event_timezone = ZoneInfo("America/Guyana")
    return _to_aware(event.start_at).astimezone(event_timezone).strftime("%Y-%m-%d %H:%M %Z")


def _reminder_message(reminder_type: ReminderType) -> tuple[str, str]:
    if reminder_type == ReminderType.HOURS_24_BEFORE:
        return ("Your event is tomorrow", "starts tomorrow")
    if reminder_type == ReminderType.HOURS_3_BEFORE:
        return ("Your event is today", "starts today")
    return ("Your event starts soon", "starts soon")


def _notification_event_for_reminder(reminder_type: ReminderType) -> NotificationEventType:
    if reminder_type == ReminderType.HOURS_24_BEFORE:
        return NotificationEventType.EVENT_TOMORROW_REMINDER
    if reminder_type == ReminderType.HOURS_3_BEFORE:
        return NotificationEventType.EVENT_TODAY_REMINDER
    return NotificationEventType.EVENT_STARTING_SOON_REMINDER


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
    _ = body_phrase
    _ = ticket_count
    create_user_notification(
        db,
        user_id=user.id,
        notification_type="event_starting_soon",
        title=push.title,
        body=push.body,
        dedupe_key=f"event:{event.id}:user:{user.id}:reminder:{reminder_type.value}",
        route_key="event",
        route_params={"event_id": event.id},
        related_entity_type="event",
        related_entity_id=event.id,
    )
    return NotificationDispatchResult(success=True, channel_results={"push": "queued_durable"})


def notify_dispute_resolved(
    db: Session,
    *,
    dispute: Dispute,
    order: Order | None,
) -> NotificationDispatchResult:
    email = _user_email(db, dispute.user_id)
    order_ref = order.id if order is not None else dispute.order_id
    return dispatch_notification_event(
        db,
        event_type=NotificationEventType.DISPUTE_RESOLVED,
        email=EmailMessage(
            to_email=email,
            subject=f"Dispute #{dispute.id} resolved",
            body=f"Dispute #{dispute.id} for order #{order_ref} has been resolved.",
        ) if email else None,
        push=PushMessage(
            user_id=dispute.user_id,
            title="Dispute resolved",
            body=f"Dispute #{dispute.id} has been resolved.",
            data={
                "type": NotificationEventType.DISPUTE_RESOLVED.value,
                "dispute_id": str(dispute.id),
                "order_id": str(order_ref),
            },
        ),
    )
