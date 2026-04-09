from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class EventCancelRequest(BaseModel):
    reason: str | None = None


class EventResponse(BaseModel):
    id: int
    organizer_id: int
    status: str
    cancelled_at: datetime | None
    cancelled_by_user_id: int | None
    cancellation_reason: str | None
    updated_at: datetime
    refund_batch_id: int | None = None
    refund_batch_status: str | None = None


class EventPriceSummaryResponse(BaseModel):
    currency: str
    min_price: str
    is_free: bool


class EventDiscoveryItemResponse(BaseModel):
    id: int
    title: str
    short_description: str | None
    category: str | None
    cover_image_url: str | None
    start_at: datetime
    end_at: datetime
    venue_name: str | None
    venue_city: str | None
    venue_country: str | None
    custom_venue_name: str | None
    custom_address_text: str | None
    organizer_name: str | None
    price_summary: EventPriceSummaryResponse | None


class EventDiscoveryTicketTierResponse(BaseModel):
    id: int
    name: str
    description: str | None
    price_amount: str
    currency: str
    min_per_order: int
    max_per_order: int
    available_quantity: int
    is_active: bool


class EventDiscoveryDetailResponse(EventDiscoveryItemResponse):
    long_description: str | None
    ticket_tiers: list[EventDiscoveryTicketTierResponse]


class EventRefundBatchResponse(BaseModel):
    id: int
    event_id: int
    status: str
    total_orders: int
    processed_orders: int
    successful_refunds: int
    skipped_orders: int
    failed_orders: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    last_error: str | None


class EventStaffResponse(BaseModel):
    id: int
    event_id: int
    user_id: int
    role: str
    created_at: datetime
    invited_by_user_id: int | None
    is_active: bool
    is_effective_active: bool


class EventStaffCreateRequest(BaseModel):
    user_id: int
    role: str


class EventStaffUpdateRequest(BaseModel):
    role: str


class EventCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    short_description: str | None = None
    long_description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    start_at: datetime
    end_at: datetime
    timezone: str = Field(min_length=1, max_length=64)
    venue_id: int | None = None
    custom_venue_name: str | None = None
    custom_address_text: str | None = None
    cover_image_url: str | None = None
    visibility: str | None = None

    @model_validator(mode="after")
    def validate_times_and_location(self) -> "EventCreateRequest":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at.")
        if self.venue_id is None and not (self.custom_venue_name and self.custom_venue_name.strip()):
            raise ValueError("Provide either venue_id or custom_venue_name.")
        return self


class EventCreateResponse(BaseModel):
    id: int
    organizer_id: int
    title: str
    status: str
    visibility: str
    approval_status: str
    start_at: datetime
    end_at: datetime
    timezone: str
    venue_id: int | None
    custom_venue_name: str | None
    custom_address_text: str | None
    created_at: datetime


class MyEventItemResponse(BaseModel):
    id: int
    title: str
    start_at: datetime
    end_at: datetime
    timezone: str
    status: str
    visibility: str
    venue_name: str | None
    venue_city: str | None
    custom_venue_name: str | None
    is_active: bool
    is_upcoming: bool
    is_ended: bool


class EventDashboardTierResponse(BaseModel):
    ticket_tier_id: int
    name: str
    sold_count: int
    remaining_count: int
    gross_revenue: float
    currency: str


class EventDashboardCheckInRow(BaseModel):
    ticket_id: int
    checked_in_at: datetime
    checked_in_by_user_id: int | None


class EventDashboardResponse(BaseModel):
    event_id: int
    tickets_sold: int
    gross_revenue: float
    attendees_admitted: int
    attendees_remaining: int
    total_ticket_capacity: int
    transfer_count: int
    voided_ticket_count: int
    refunded_ticket_count: int
    live_checkin_percentage: float
    active_staff_assigned: int
    tier_metrics: list[EventDashboardTierResponse]
    recent_checkins: list[EventDashboardCheckInRow]
