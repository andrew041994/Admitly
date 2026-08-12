from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


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


class AdminEventApprovalItemResponse(BaseModel):
    id: int
    title: str
    slug: str
    organizer_name: str | None
    start_at: datetime
    venue_name: str | None
    custom_venue_name: str | None
    approval_status: str
    status: str
    created_at: datetime
    published_at: datetime | None
    creator_user_id: int
    creator_age_identity_verification_status: str
    creator_age_identity_verified_user_id: int | None
    creator_age_identity_verified_by_user_id: int | None
    creator_age_identity_verified_at: datetime | None
    creator_age_identity_verification_snapshot_at: datetime | None
    creator_account_verification_status: str
    creator_account_verified_at: datetime | None
    creator_account_verified_by_user_id: int | None
    creator_account_revoked_at: datetime | None
    creator_account_revoked_by_user_id: int | None
    creator_account_verification_note: str | None
    creator_account_revocation_reason: str | None
    creator_verification_manual_review_required: bool


class EventCreatorAgeIdentityVerificationRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class CreatorAgeIdentityRevocationRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("A revocation reason is required.")
        return normalized


class CreatorAgeIdentityHistoryResponse(BaseModel):
    id: int
    user_id: int
    action: str
    actor_user_id: int
    previous_status: str
    new_status: str
    note: str | None
    created_at: datetime


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
    username: str | None = None
    display_name: str | None = None
    full_name: str | None = None
    email: str | None = None
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
    cover_image_url: str | None = None
    start_at: datetime
    end_at: datetime
    doors_open_at: datetime | None = None
    sales_start_at: datetime | None = None
    sales_end_at: datetime | None = None
    timezone: str = Field(default="America/Guyana", min_length=1, max_length=64)
    venue_id: int | None = None
    custom_venue_name: str | None = None
    custom_address_text: str | None = None
    refund_policy_text: str | None = None
    terms_text: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    is_location_pinned: bool | None = None
    ticket_tiers: list["TicketTierCreateRequest"] = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("title is required.")
        return trimmed

    @model_validator(mode="after")
    def validate_times_and_location(self) -> "EventCreateRequest":
        if self.cover_image_url is not None:
            raise ValueError("cover_image_url must be set through the event cover image endpoint.")
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at.")
        if self.sales_start_at and self.sales_end_at and self.sales_end_at <= self.sales_start_at:
            raise ValueError("sales_end_at must be after sales_start_at.")
        if self.doors_open_at and self.doors_open_at > self.end_at:
            raise ValueError("doors_open_at must be before or at end_at.")
        if self.venue_id is None and not (self.custom_venue_name and self.custom_venue_name.strip()):
            raise ValueError("Provide either venue_id or custom_venue_name.")
        if self.latitude is not None and (self.latitude < Decimal("-90") or self.latitude > Decimal("90")):
            raise ValueError("latitude must be between -90 and 90.")
        if self.longitude is not None and (self.longitude < Decimal("-180") or self.longitude > Decimal("180")):
            raise ValueError("longitude must be between -180 and 180.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together.")
        return self


class TicketTierCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    price_amount: Decimal
    currency: str = Field(default="GYD", min_length=3, max_length=3)
    quantity_total: int
    min_per_order: int = 1
    max_per_order: int = 10
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("tier name is required.")
        return trimmed

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        upper = value.strip().upper()
        if len(upper) != 3:
            raise ValueError("currency must be a 3-letter code.")
        return upper

    @model_validator(mode="after")
    def validate_tier_constraints(self) -> "TicketTierCreateRequest":
        if self.price_amount < 0:
            raise ValueError("price_amount must not be negative.")
        if self.quantity_total <= 0:
            raise ValueError("quantity_total must be greater than zero.")
        if self.min_per_order < 1:
            raise ValueError("min_per_order must be at least 1.")
        if self.max_per_order < self.min_per_order:
            raise ValueError("max_per_order must be greater than or equal to min_per_order.")
        return self


class EventCreateTicketTierResponse(BaseModel):
    id: int
    event_id: int
    name: str
    description: str | None
    tier_code: str
    price_amount: str
    currency: str
    quantity_total: int
    min_per_order: int
    max_per_order: int
    is_active: bool
    sort_order: int


class EventCreateResponse(BaseModel):
    id: int
    organizer_id: int
    title: str
    slug: str
    status: str
    visibility: str
    approval_status: str
    start_at: datetime
    end_at: datetime
    doors_open_at: datetime | None
    sales_start_at: datetime | None
    sales_end_at: datetime | None
    timezone: str
    venue_id: int | None
    custom_venue_name: str | None
    custom_address_text: str | None
    refund_policy_text: str | None
    terms_text: str | None
    latitude: str | None
    longitude: str | None
    is_location_pinned: bool
    published_at: datetime | None
    created_at: datetime
    ticket_tiers: list[EventCreateTicketTierResponse]


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


class OrganizerTicketTierUpsertRequest(BaseModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    price_amount: Decimal
    currency: str = Field(default="GYD", min_length=3, max_length=3)
    quantity_total: int
    min_per_order: int = 1
    max_per_order: int = 10
    is_active: bool | None = None
    sort_order: int | None = None
    delete: bool = False


class OrganizerEventUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    short_description: str | None = None
    long_description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    cover_image_url: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    doors_open_at: datetime | None = None
    sales_start_at: datetime | None = None
    sales_end_at: datetime | None = None
    visibility: str | None = None
    venue_id: int | None = None
    custom_venue_name: str | None = None
    custom_address_text: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    is_location_pinned: bool | None = None
    ticket_tiers: list[OrganizerTicketTierUpsertRequest] | None = None

    @model_validator(mode="after")
    def validate_cover_image_update(self) -> "OrganizerEventUpdateRequest":
        if self.cover_image_url is not None:
            raise ValueError("cover_image_url must be set through the event cover image endpoint.")
        return self


class EventRescheduleRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=128)
    start_at: datetime
    end_at: datetime
    doors_open_at: datetime | None
    sales_start_at: datetime | None
    sales_end_at: datetime | None
    venue_id: int | None
    custom_venue_name: str | None
    custom_address_text: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    is_location_pinned: bool
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("idempotency_key", "reason")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_schedule(self) -> "EventRescheduleRequest":
        values = [self.start_at, self.end_at, self.doors_open_at, self.sales_start_at, self.sales_end_at]
        if any(value is not None and value.tzinfo is None for value in values):
            raise ValueError("Reschedule date/times must include a UTC offset.")
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at.")
        if self.doors_open_at is not None and self.doors_open_at > self.start_at:
            raise ValueError("doors_open_at must be before or at start_at.")
        if self.sales_start_at is not None and self.sales_end_at is not None and self.sales_end_at <= self.sales_start_at:
            raise ValueError("sales_end_at must be after sales_start_at.")
        if self.sales_end_at is not None and self.sales_end_at > self.start_at:
            raise ValueError("sales_end_at must be before or at start_at.")
        if self.venue_id is not None and (self.custom_venue_name or self.custom_address_text):
            raise ValueError("Use either venue_id or custom venue fields, not both.")
        if self.venue_id is None and not (self.custom_venue_name and self.custom_venue_name.strip()):
            raise ValueError("Provide either venue_id or custom_venue_name.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together.")
        if self.latitude is not None and not Decimal("-90") <= self.latitude <= Decimal("90"):
            raise ValueError("latitude must be between -90 and 90.")
        if self.longitude is not None and not Decimal("-180") <= self.longitude <= Decimal("180"):
            raise ValueError("longitude must be between -180 and 180.")
        if self.is_location_pinned and self.latitude is None:
            raise ValueError("Pinned locations require latitude and longitude.")
        return self


class EventRescheduleResponse(BaseModel):
    id: int
    event_id: int
    actor_user_id: int
    previous_start_at: datetime
    previous_end_at: datetime
    previous_doors_open_at: datetime | None
    new_start_at: datetime
    new_end_at: datetime
    new_doors_open_at: datetime | None
    sales_start_at: datetime | None
    sales_end_at: datetime | None
    previous_venue_id: int | None
    new_venue_id: int | None
    previous_custom_venue_name: str | None
    new_custom_venue_name: str | None
    previous_custom_address_text: str | None
    new_custom_address_text: str | None
    previous_latitude: str | None
    new_latitude: str | None
    previous_longitude: str | None
    new_longitude: str | None
    previous_is_location_pinned: bool
    new_is_location_pinned: bool
    reason: str
    rescheduled_at: datetime
    notifications_required: bool


class OrganizerEventDashboardItemResponse(BaseModel):
    id: int
    title: str
    cover_image_url: str | None
    venue_name: str | None
    city: str | None
    start_at: datetime
    end_at: datetime
    status: str
    approval_status: str
    is_publicly_visible: bool
    visibility_state: str | None = None
    total_ticket_types: int
    total_quantity: int
    sold_count: int
    gross_revenue: float
    created_at: datetime
    updated_at: datetime


class OrganizerEventDetailResponse(BaseModel):
    id: int
    title: str
    short_description: str | None
    long_description: str | None
    category: str | None
    cover_image_url: str | None
    start_at: datetime
    end_at: datetime
    doors_open_at: datetime | None
    sales_start_at: datetime | None
    sales_end_at: datetime | None
    timezone: str
    visibility: str
    status: str
    approval_status: str
    is_publicly_visible: bool
    visibility_state: str | None = None
    venue_id: int | None
    venue_name: str | None
    venue_address_text: str | None
    custom_venue_name: str | None
    custom_address_text: str | None
    latitude: str | None
    longitude: str | None
    is_location_pinned: bool
    ticket_tiers: list[EventCreateTicketTierResponse]


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
