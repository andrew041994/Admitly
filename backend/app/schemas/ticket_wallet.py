from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WalletEventSummary(BaseModel):
    id: int
    title: str
    start_at: datetime
    end_at: datetime | None = None
    timezone: str | None = None
    banner_image_url: str | None = None
    is_upcoming: bool
    status: str | None = None


class WalletVenueSummary(BaseModel):
    name: str | None = None
    address_summary: str | None = None


class WalletOrganizerSummary(BaseModel):
    name: str | None = None


class WalletOwnershipSummary(BaseModel):
    is_current_owner: bool
    purchaser_user_id: int
    owner_user_id: int
    acquired_via_transfer: bool


class WalletTicketCardItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_code: str
    ticket_status: str
    display_status: str
    is_valid_for_entry: bool
    can_display_entry_code: bool
    event: WalletEventSummary
    venue: WalletVenueSummary
    organizer: WalletOrganizerSummary
    ticket_tier_name: str
    ownership: WalletOwnershipSummary
    order_id: int
    order_reference: str | None = None
    issued_at: datetime
    checked_in_at: datetime | None = None
    transferred_at: datetime | None = None
    transfer_count: int


class WalletTicketDetailResponse(WalletTicketCardItemResponse):
    qr_payload: str
    check_in_token: str
    check_in_method: str | None = None
    voided_at: datetime | None = None
    void_reason: str | None = None
    order_status: str
    order_refund_status: str
