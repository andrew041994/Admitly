from datetime import datetime

from pydantic import BaseModel, Field


class RefundRequestCreate(BaseModel):
    order_id: int
    reason: str
    amount: float | None = None
    note: str | None = None


class RefundApproveRequest(BaseModel):
    amount: float | None = None
    admin_notes: str | None = None


class RefundProviderConfirmRequest(BaseModel):
    provider_refund_reference: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=3, max_length=1000)


class RefundRejectRequest(BaseModel):
    admin_notes: str


class RefundResponse(BaseModel):
    id: int
    order_id: int
    user_id: int
    amount: float
    status: str
    reason: str
    admin_notes: str | None
    processed_at: datetime | None
    payment_provider: str | None
    provider_refund_reference: str | None
    provider_status: str
    provider_submitted_at: datetime | None
    provider_verified_at: datetime | None
    created_at: datetime


class DisputeCreateRequest(BaseModel):
    order_id: int
    message: str


class DisputeResolveRequest(BaseModel):
    resolution: str | None = None
    admin_notes: str | None = None
    refund_amount: float | None = None
    refund_reason: str | None = None


class DisputeRejectRequest(BaseModel):
    admin_notes: str


class DisputeResponse(BaseModel):
    id: int
    order_id: int
    user_id: int
    message: str
    status: str
    admin_notes: str | None
    resolution: str | None
    resolved_at: datetime | None
    created_at: datetime
