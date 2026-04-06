from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateTicketTransferInviteRequest(BaseModel):
    recipient_user_id: int | None = None
    recipient_email: str | None = None
    recipient_phone: str | None = None
    expires_at: datetime | None = None


class TicketTransferInviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    sender_user_id: int
    recipient_user_id: int | None
    recipient_email: str | None
    recipient_phone: str | None
    invite_token: str
    status: str
    expires_at: datetime | None
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AcceptTicketTransferInviteResponse(BaseModel):
    ticket_id: int
    owner_user_id: int
    status: str


class RevokeTicketTransferInviteResponse(BaseModel):
    id: int
    status: str
    revoked_at: datetime | None
