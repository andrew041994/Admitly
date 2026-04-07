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
    qr_payload: str
    public_ticket_url: str
    qr_image_url: str
    issued_at: datetime
    checked_in_at: datetime | None
    check_in_method: str | None = None
    transferred_at: datetime | None
    voided_at: datetime | None
    voided_by_user_id: int | None
    void_reason: str | None
    transfer_count: int


class TicketTransferRequest(BaseModel):
    to_user_id: int


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


class TicketVoidRequest(BaseModel):
    reason: str | None = None


class TicketQrResponse(BaseModel):
    ticket_public_token: str
    qr_payload: str
    public_ticket_url: str
    qr_image_url: str
    qr_data_uri: str
