from datetime import datetime

from pydantic import BaseModel, Field


class MessageLogResponse(BaseModel):
    id: int
    template_type: str
    channel: str
    status: str
    recipient_user_id: int | None = None
    recipient_email: str | None = None
    related_entity_type: str | None = None
    related_entity_id: int | None = None
    provider_status: str | None = None
    error_reason: str | None = None
    idempotency_key: str | None = None
    is_manual_resend: bool
    resend_of_message_id: int | None = None
    actor_user_id: int | None = None
    created_at: datetime


class EventBroadcastSendRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=140)
    body: str = Field(min_length=1, max_length=2000)
    include_email: bool = True
    include_push: bool = True


class EventBroadcastSendResponse(BaseModel):
    success: bool
    attempted_recipients: int
    sent_attempts: int


class MessageResendResponse(BaseModel):
    success: bool
    message: str
    log_ids: list[int]
