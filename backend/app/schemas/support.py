from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SupportNoteCreateRequest(BaseModel):
    body: str = Field(min_length=1)


class SupportCasePatchRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to_user_id: int | None = None
    category: str | None = None


class SupportActionRequest(BaseModel):
    action_type: str = Field(min_length=1)
    reason: str | None = None
    payload: dict[str, Any] | None = None


class SupportActionResponse(BaseModel):
    action_type: str
    success: bool
    message: str


class SupportCaseNoteResponse(BaseModel):
    id: int
    support_case_id: int
    author_user_id: int
    body: str
    is_system_note: bool
    created_at: datetime


class SupportCaseResponse(BaseModel):
    id: int
    order_id: int
    status: str
    priority: str
    category: str
    created_by_user_id: int | None
    assigned_to_user_id: int | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SupportTimelineItemResponse(BaseModel):
    timestamp: datetime
    type: str
    title: str
    description: str
    actor: str | None = None
    metadata: dict[str, Any] | None = None


class AdminAuditResponse(BaseModel):
    id: int
    actor_user_id: int
    target_type: str
    target_id: str
    action_type: str
    reason: str | None
    metadata: dict[str, Any] | None
    created_at: datetime




class SupportMessageLogResponse(BaseModel):
    id: int
    template_type: str
    channel: str
    status: str
    provider_status: str | None
    is_manual_resend: bool
    resend_of_message_id: int | None
    actor_user_id: int | None
    created_at: datetime


class SupportSnapshotResponse(BaseModel):
    order_id: int
    event_id: int
    event_title: str | None
    buyer_user_id: int
    order_status: str
    quantity: int
    subtotal_amount: float
    discount_amount: float
    total_amount: float
    currency: str
    payment_reference: str | None
    payment_verification_status: str
    payment_submitted_at: datetime | None
    paid_at: datetime | None
    refund_status: str
    refunded_at: datetime | None
    dispute_count: int
    transfer_invite_count: int
    reconciliation_status: str
    payout_status: str
    promo_code_text: str | None
    support_case: SupportCaseResponse | None
    support_notes: list[SupportCaseNoteResponse]
    timeline: list[SupportTimelineItemResponse]
    admin_audits: list[AdminAuditResponse]
    message_history: list[SupportMessageLogResponse]
