from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import MessageChannel, MessageDeliveryStatus, MessageTemplateType
from app.models.message_delivery_log import MessageDeliveryLog


@dataclass(slots=True)
class MessageDispatchResult:
    success: bool
    channel_results: dict[str, str]
    log_ids: list[int]


@dataclass(slots=True)
class RenderedMessage:
    email_subject: str | None = None
    email_body: str | None = None
    push_title: str | None = None
    push_body: str | None = None
    push_data: dict[str, str] | None = None


def _render_template(template_type: MessageTemplateType, context: dict[str, str]) -> RenderedMessage:
    if template_type == MessageTemplateType.ORDER_CONFIRMATION:
        return RenderedMessage(
            email_subject=f"Order #{context['order_id']} confirmed",
            email_body=f"Your order #{context['order_id']} for {context['event_title']} has been confirmed.",
            push_title="Order confirmed",
            push_body=f"Order #{context['order_id']} is complete.",
            push_data={"type": "order_completed", "order_id": context["order_id"], "event_id": context["event_id"]},
        )
    if template_type == MessageTemplateType.TICKET_ISSUED:
        return RenderedMessage(
            email_subject=f"{context['quantity']} ticket(s) issued for order #{context['order_id']}",
            email_body=context["email_body"],
            push_title="Tickets issued",
            push_body=f"{context['quantity']} ticket(s) are ready.",
            push_data={"type": "tickets_issued", "order_id": context["order_id"], "event_id": context["event_id"]},
        )
    if template_type == MessageTemplateType.TRANSFER_INVITE:
        return RenderedMessage(
            email_subject=f"Ticket transfer invite #{context['ticket_id']}",
            email_body=f"You have been invited to claim ticket #{context['ticket_id']}.",
            push_title="Ticket transfer invite",
            push_body=f"You have been invited to claim ticket #{context['ticket_id']}.",
            push_data={"type": "ticket_transfer_invite_created", "ticket_id": context["ticket_id"], "invite_token": context.get("invite_token", "")},
        )
    if template_type == MessageTemplateType.TRANSFER_ACCEPTED:
        return RenderedMessage(
            push_title="Transfer accepted",
            push_body=f"Ticket #{context['ticket_id']} transfer completed.",
            push_data={"type": "ticket_transfer_invite_accepted", "ticket_id": context["ticket_id"], "invite_id": context.get("invite_id", "")},
        )
    if template_type == MessageTemplateType.REFUND_PROCESSED:
        return RenderedMessage(
            email_subject=f"Order #{context['order_id']} refunded",
            email_body=f"Your order #{context['order_id']} has been refunded.",
            push_title="Order refunded",
            push_body=f"Order #{context['order_id']} has been refunded.",
            push_data={"type": "order_refunded", "order_id": context["order_id"], "event_id": context["event_id"]},
        )
    if template_type == MessageTemplateType.REMINDER:
        return RenderedMessage(
            push_title=context["title"],
            push_body=context["body"],
            push_data={"type": "event_reminder", "event_id": context["event_id"], "reminder_type": context["reminder_type"]},
        )
    body = context.get("body", "")
    return RenderedMessage(
        email_subject=context.get("subject") or "Event update",
        email_body=body,
        push_title=context.get("subject") or "Event update",
        push_body=body,
        push_data={"type": "event_update", "event_id": context.get("event_id", "")},
    )


def dispatch_templated_message(
    db: Session,
    *,
    template_type: MessageTemplateType,
    channels: tuple[MessageChannel, ...],
    recipient_user_id: int | None,
    recipient_email: str | None,
    related_entity_type: str | None,
    related_entity_id: int | None,
    context: dict[str, str],
    actor_user_id: int | None = None,
    idempotency_key: str | None = None,
    is_manual_resend: bool = False,
    resend_of_message_id: int | None = None,
) -> MessageDispatchResult:
    from app.services.notifications import EmailMessage, PushMessage, _send_email, _send_push

    rendered = _render_template(template_type, context)
    channel_results: dict[str, str] = {}
    success = True
    log_ids: list[int] = []

    for channel in channels:
        if idempotency_key and not is_manual_resend:
            prior = db.execute(
                select(MessageDeliveryLog.id).where(
                    MessageDeliveryLog.idempotency_key == idempotency_key,
                    MessageDeliveryLog.template_type == template_type,
                    MessageDeliveryLog.channel == channel,
                    MessageDeliveryLog.status == MessageDeliveryStatus.SENT,
                )
            ).scalar_one_or_none()
            if prior is not None:
                channel_results[channel.value] = "skipped_duplicate"
                continue

        provider_status = ""
        status = MessageDeliveryStatus.SENT
        error_reason = None
        try:
            if channel == MessageChannel.EMAIL:
                if not recipient_email or not rendered.email_subject or not rendered.email_body:
                    provider_status = "skipped_no_recipient"
                    status = MessageDeliveryStatus.SKIPPED
                else:
                    provider_status = _send_email(EmailMessage(to_email=recipient_email, subject=rendered.email_subject, body=rendered.email_body))
            elif channel == MessageChannel.PUSH:
                if recipient_user_id is None or not rendered.push_title or not rendered.push_body:
                    provider_status = "skipped_no_recipient"
                    status = MessageDeliveryStatus.SKIPPED
                else:
                    provider_status = _send_push(
                        db,
                        PushMessage(user_id=recipient_user_id, title=rendered.push_title, body=rendered.push_body, data=rendered.push_data or {}),
                    )
            if provider_status.startswith("failed"):
                status = MessageDeliveryStatus.FAILED
                success = False
            if provider_status.startswith("skipped"):
                status = MessageDeliveryStatus.SKIPPED
        except Exception as exc:  # pragma: no cover
            provider_status = "failed"
            status = MessageDeliveryStatus.FAILED
            error_reason = str(exc)
            success = False

        log = MessageDeliveryLog(
            template_type=template_type,
            channel=channel,
            status=status,
            recipient_user_id=recipient_user_id,
            recipient_email=recipient_email,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            provider_status=provider_status,
            error_reason=error_reason,
            idempotency_key=idempotency_key,
            is_manual_resend=is_manual_resend,
            resend_of_message_id=resend_of_message_id,
            actor_user_id=actor_user_id,
        )
        db.add(log)
        db.flush()
        log_ids.append(log.id)
        channel_results[channel.value] = provider_status

    return MessageDispatchResult(success=success, channel_results=channel_results, log_ids=log_ids)


def list_message_history(
    db: Session,
    *,
    related_entity_type: str,
    related_entity_id: int,
) -> list[MessageDeliveryLog]:
    return (
        db.execute(
            select(MessageDeliveryLog)
            .where(
                MessageDeliveryLog.related_entity_type == related_entity_type,
                MessageDeliveryLog.related_entity_id == related_entity_id,
            )
            .order_by(MessageDeliveryLog.created_at.desc(), MessageDeliveryLog.id.desc())
        )
        .scalars()
        .all()
    )
