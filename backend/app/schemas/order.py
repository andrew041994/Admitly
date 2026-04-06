from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreatePendingOrderFromHoldsRequest(BaseModel):
    hold_ids: list[int] = Field(min_length=1)


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
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]
