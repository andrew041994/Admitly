from datetime import datetime

from pydantic import BaseModel


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


class EventDiscoveryDetailResponse(EventDiscoveryItemResponse):
    long_description: str | None


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


class EventStaffCreateRequest(BaseModel):
    user_id: int
    role: str


class EventStaffUpdateRequest(BaseModel):
    role: str
