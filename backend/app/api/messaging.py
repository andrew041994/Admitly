from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.enums import MessageChannel, MessageTemplateType, TicketStatus
from app.models.event import Event
from app.models.message_delivery_log import MessageDeliveryLog
from app.models.order import Order
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.messaging import (
    EventBroadcastSendRequest,
    EventBroadcastSendResponse,
    MessageLogResponse,
    MessageResendResponse,
)
from app.services.event_permissions import EventPermissionAction, has_event_permission_by_id
from app.services.messaging import dispatch_templated_message, list_message_history

router = APIRouter(tags=["messaging"])


def _can_operate_event_messages(db: Session, *, user_id: int, event_id: int) -> bool:
    return has_event_permission_by_id(db, user_id=user_id, event_id=event_id, action=EventPermissionAction.VIEW_ORDERS)


@router.get("/orders/{order_id}/messages", response_model=list[MessageLogResponse])
def get_order_message_history(
    order_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[MessageLogResponse]:
    order = db.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

    actor = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if actor is None or (not actor.is_admin and order.user_id != user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this order.")

    rows = list_message_history(db, related_entity_type="order", related_entity_id=order_id)
    return [MessageLogResponse(**_to_dict(row)) for row in rows]


@router.get("/events/{event_id}/messages", response_model=list[MessageLogResponse])
def get_event_message_history(
    event_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[MessageLogResponse]:
    if not _can_operate_event_messages(db, user_id=user_id, event_id=event_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this event.")
    rows = list_message_history(db, related_entity_type="event", related_entity_id=event_id)
    return [MessageLogResponse(**_to_dict(row)) for row in rows]


@router.post("/events/{event_id}/messages/broadcast", response_model=EventBroadcastSendResponse)
def send_event_broadcast_message(
    event_id: int,
    payload: EventBroadcastSendRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> EventBroadcastSendResponse:
    if not _can_operate_event_messages(db, user_id=user_id, event_id=event_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this event.")

    event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")

    channels: list[MessageChannel] = []
    if payload.include_email:
        channels.append(MessageChannel.EMAIL)
    if payload.include_push:
        channels.append(MessageChannel.PUSH)
    if not channels:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one channel must be selected.")

    recipients = db.execute(
        select(Ticket.owner_user_id, User.email)
        .join(User, User.id == Ticket.owner_user_id)
        .where(Ticket.event_id == event_id, Ticket.status == TicketStatus.ISSUED)
        .distinct()
    ).all()

    sent_attempts = 0
    success = True
    for recipient_user_id, recipient_email in recipients:
        result = dispatch_templated_message(
            db,
            template_type=MessageTemplateType.EVENT_DAY_UPDATE,
            channels=tuple(channels),
            recipient_user_id=recipient_user_id,
            recipient_email=recipient_email,
            related_entity_type="event",
            related_entity_id=event_id,
            context={"subject": payload.subject, "body": payload.body, "event_id": str(event_id)},
            actor_user_id=user_id,
            is_manual_resend=True,
            idempotency_key=f"event_broadcast:{event_id}:{payload.subject.strip().lower()}",
        )
        sent_attempts += len(result.log_ids)
        success = success and result.success

    return EventBroadcastSendResponse(success=success, attempted_recipients=len(recipients), sent_attempts=sent_attempts)


@router.post("/messages/{message_log_id}/resend", response_model=MessageResendResponse)
def resend_message(
    message_log_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> MessageResendResponse:
    source = db.execute(select(MessageDeliveryLog).where(MessageDeliveryLog.id == message_log_id)).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message log not found.")

    if source.related_entity_type == "event":
        if source.related_entity_id is None or not _can_operate_event_messages(db, user_id=user_id, event_id=source.related_entity_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to resend this message.")
    elif source.related_entity_type == "order":
        order = db.execute(select(Order).where(Order.id == source.related_entity_id)).scalar_one_or_none()
        actor = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if order is None or actor is None or (not actor.is_admin and order.user_id != user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to resend this message.")

    result = dispatch_templated_message(
        db,
        template_type=source.template_type,
        channels=(source.channel,),
        recipient_user_id=source.recipient_user_id,
        recipient_email=source.recipient_email,
        related_entity_type=source.related_entity_type,
        related_entity_id=source.related_entity_id,
        context={"subject": "Resent message", "body": "Operational message resent.", "event_id": str(source.related_entity_id or "")},
        actor_user_id=user_id,
        is_manual_resend=True,
        resend_of_message_id=source.id,
    )
    return MessageResendResponse(success=result.success, message="Resend attempted.", log_ids=result.log_ids)


def _to_dict(row: MessageDeliveryLog) -> dict:
    return {
        "id": row.id,
        "template_type": row.template_type.value,
        "channel": row.channel.value,
        "status": row.status.value,
        "recipient_user_id": row.recipient_user_id,
        "recipient_email": row.recipient_email,
        "related_entity_type": row.related_entity_type,
        "related_entity_id": row.related_entity_id,
        "provider_status": row.provider_status,
        "error_reason": row.error_reason,
        "idempotency_key": row.idempotency_key,
        "is_manual_resend": row.is_manual_resend,
        "resend_of_message_id": row.resend_of_message_id,
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at,
    }
