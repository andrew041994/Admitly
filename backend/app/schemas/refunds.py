from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RefundRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: int
    reason: str
    note: str | None = None


class RefundApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

    resolution: str | None = None
    admin_notes: str | None = None
    refund_full_order: bool = False
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
