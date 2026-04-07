from datetime import datetime

from pydantic import BaseModel, Field


class PromoCodeCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    description: str | None = None
    discount_type: str
    discount_value: float
    currency: str | None = None
    is_active: bool = True
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_total_redemptions: int | None = None
    max_redemptions_per_user: int | None = None
    min_order_amount: float | None = None
    applies_to_all_tiers: bool = True
    ticket_tier_ids: list[int] = Field(default_factory=list)


class PromoCodeUpdateRequest(BaseModel):
    description: str | None = None
    is_active: bool | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_total_redemptions: int | None = None
    max_redemptions_per_user: int | None = None
    min_order_amount: float | None = None


class PromoCodeResponse(BaseModel):
    id: int
    event_id: int
    code: str
    description: str | None
    discount_type: str
    discount_value: float
    currency: str | None
    is_active: bool
    valid_from: datetime | None
    valid_until: datetime | None
    max_total_redemptions: int | None
    max_redemptions_per_user: int | None
    min_order_amount: float | None
    applies_to_all_tiers: bool
    ticket_tier_ids: list[int]


class PromoCodeValidateRequest(BaseModel):
    hold_ids: list[int] = Field(min_length=1)
    code: str


class PromoCodeValidateResponse(BaseModel):
    valid: bool
    subtotal_amount: float | None = None
    discount_amount: float | None = None
    total_amount: float | None = None
    code: str | None = None
    reason: str | None = None


class CompOrderTicketRequest(BaseModel):
    ticket_tier_id: int
    quantity: int = Field(ge=1)


class CreateCompOrderRequest(BaseModel):
    purchaser_user_id: int
    reason: str | None = None
    tickets: list[CompOrderTicketRequest] = Field(min_length=1)
