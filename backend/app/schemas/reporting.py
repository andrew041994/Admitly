from datetime import datetime

from pydantic import BaseModel


class OrganizerEventSummaryResponse(BaseModel):
    event_id: int
    event_title: str
    event_status: str
    starts_at: datetime
    ends_at: datetime | None
    gross_revenue: float
    refunded_amount: float
    net_revenue: float
    completed_order_count: int
    pending_order_count: int
    cancelled_order_count: int
    refunded_order_count: int
    tickets_sold_count: int
    tickets_issued_count: int
    tickets_checked_in_count: int
    tickets_voided_count: int
    tickets_remaining_count: int
    check_in_rate: float
    total_capacity: int
    generated_at: datetime


class OrganizerTierSummaryRowResponse(BaseModel):
    ticket_tier_id: int
    name: str
    price: float
    currency: str
    configured_quantity: int
    sold_count: int
    active_hold_count: int
    issued_count: int
    checked_in_count: int
    voided_count: int
    remaining_count: int
    gross_revenue: float


class OrganizerOrderRowResponse(BaseModel):
    order_id: int
    user_id: int
    status: str
    refund_status: str
    payment_provider: str | None
    payment_method: str | None
    total_amount: float
    currency: str
    item_count: int
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None
    refunded_at: datetime | None


class OrganizerTicketRowResponse(BaseModel):
    ticket_id: int
    order_id: int
    order_item_id: int
    ticket_tier_id: int
    purchaser_user_id: int
    owner_user_id: int
    status: str
    transfer_count: int
    ticket_code: str
    issued_at: datetime
    checked_in_at: datetime | None
    checked_in_by_user_id: int | None
    voided_at: datetime | None


class OrganizerCheckInSummaryResponse(BaseModel):
    event_id: int
    total_checked_in: int
    total_not_checked_in: int
    first_check_in_at: datetime | None
    last_check_in_at: datetime | None
    check_in_rate: float


class OrganizerCheckInRowResponse(BaseModel):
    ticket_id: int
    ticket_tier_id: int
    checked_in_at: datetime
    checked_in_by_user_id: int | None
    purchaser_user_id: int
    owner_user_id: int
    order_id: int
