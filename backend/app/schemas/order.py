from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreatePendingOrderFromHoldsRequest(BaseModel):
    hold_ids: list[int] = Field(min_length=1)


class OrderCancelRequest(BaseModel):
    reason: str | None = None


class OrderRefundRequest(BaseModel):
    reason: str | None = None


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_tier_id: int
    quantity: int
    unit_price: float


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    event_id: int
    status: str
    total_amount: float
    currency: str
    refund_status: str | None = None
    cancelled_at: datetime | None = None
    cancelled_by_user_id: int | None = None
    cancel_reason: str | None = None
    refunded_at: datetime | None = None
    refunded_by_user_id: int | None = None
    refund_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]
