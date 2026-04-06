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
    issued_at: datetime
    checked_in_at: datetime | None
    transferred_at: datetime | None
    transfer_count: int


class TicketTransferRequest(BaseModel):
    to_user_id: int


class TicketCheckInRequest(BaseModel):
    qr_payload: str | None = None
    ticket_code: str | None = None


class TicketCheckInResponse(BaseModel):
    success: bool
    ticket_id: int | None
    event_id: int
    status: str | None
    checked_in_at: datetime | None
    checked_in_by_user_id: int | None
    message: str
