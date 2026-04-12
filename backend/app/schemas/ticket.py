from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    order_id: int
    order_item_id: int
    purchaser_user_id: int
    owner_user_id: int
    ticket_tier_id: int
    status: str
    ticket_code: str
    display_code: str | None = None
    qr_payload: str
    public_ticket_url: str
    qr_image_url: str
    event_title: str | None = None
    starts_at: datetime | None = None
    venue_name: str | None = None
    ticket_tier_name: str | None = None
    issued_at: datetime
    checked_in_at: datetime | None
    check_in_method: str | None = None
    transferred_at: datetime | None
    voided_at: datetime | None
    voided_by_user_id: int | None
    void_reason: str | None
    transfer_count: int


class TicketDetailResponse(TicketResponse):
    ticket_id: int
    ticket_public_id: str | None = None
    attendee_name: str | None = None
    attendee_email: str | None = None
    event_description: str | None = None
    venue_address: str | None = None
    ends_at: datetime | None = None
    timezone: str | None = None
    order_reference: str | None = None
    ticket_tier_name: str | None = None
    ticket_status: str
    transferred_from_user_id: int | None = None
    transferred_to_user_id: int | None = None
    created_at: datetime
    subtitle: str | None = None


class TicketTransferRequest(BaseModel):
    to_user_id: int | None = None
    recipient_email: str | None = None
    recipient_phone: str | None = None
    recipient_name: str | None = None


class TicketTransferPendingResponse(BaseModel):
    transfer_id: int
    ticket_id: int
    status: str
    recipient_user_id: int | None = None
    recipient_email: str | None = None
    recipient_phone: str | None = None
    recipient_name: str | None = None
    expires_at: datetime | None = None
    claim_url: str
    created_at: datetime


class TicketCheckInRequest(BaseModel):
    qr_payload: str | None = None
    ticket_code: str | None = None


class TicketCheckInResponse(BaseModel):
    success: bool
    code: str | None = None
    ticket_id: int | None
    event_id: int
    status: str | None
    checked_in_at: datetime | None
    checked_in_by_user_id: int | None
    message: str
    ui_signal: str


class TicketCheckInValidateRequest(BaseModel):
    qr_payload: str | None = None
    ticket_code: str | None = None


class TicketCheckInValidateResponse(BaseModel):
    valid: bool
    code: str
    message: str
    ticket_id: int | None
    ticket_code: str | None
    event_id: int
    checked_in_at: datetime | None


class TicketCheckInConfirmRequest(BaseModel):
    qr_payload: str | None = None
    ticket_code: str | None = None
    method: str | None = None


class TicketCheckInSummaryResponse(BaseModel):
    event_id: int
    total_admittable_tickets: int
    checked_in_tickets: int
    remaining_tickets: int


class TicketCheckInOverrideRequest(BaseModel):
    qr_payload: str | None = None
    ticket_code: str | None = None
    admit: bool
    notes: str


class TicketCheckInAttemptResponse(BaseModel):
    id: int
    ticket_id: int | None
    event_id: int
    actor_user_id: int | None
    attempted_at: datetime
    result_code: str
    reason_code: str | None
    reason_message: str | None
    method: str | None
    source: str | None
    notes: str | None


class TicketVoidRequest(BaseModel):
    reason: str | None = None


class TicketQrResponse(BaseModel):
    ticket_public_token: str
    qr_payload: str
    public_ticket_url: str
    qr_image_url: str
    qr_data_uri: str


class TicketScanRequest(BaseModel):
    payload: dict[str, object] | str
    selected_event_id: int | None = None


class TicketScanResponse(BaseModel):
    status: str
    ticket_id: int | None = None
    checked_in_at: datetime | None = None
    message: str | None = None
