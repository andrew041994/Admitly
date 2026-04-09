from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateTicketTransferInviteRequest(BaseModel):
    recipient_user_id: int | None = None
    recipient_email: str | None = None
    recipient_phone: str | None = None
    recipient_name: str | None = None
    expires_at: datetime | None = None


class TicketTransferInviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    sender_user_id: int
    recipient_user_id: int | None
    recipient_email: str | None
    recipient_phone: str | None
    recipient_name: str | None
    invite_token: str
    status: str
    expires_at: datetime | None
    accepted_at: datetime | None
    revoked_at: datetime | None
    claim_url: str
    created_at: datetime
    updated_at: datetime


class TicketTransferInvitePreviewResponse(BaseModel):
    transfer_id: int
    ticket_id: int
    event_title: str | None = None
    starts_at: datetime | None = None
    venue_name: str | None = None
    ticket_tier_name: str | None = None
    sender_name: str | None = None
    recipient_name: str | None = None
    recipient_email: str | None = None
    recipient_phone: str | None = None
    status: str
    expires_at: datetime | None = None
    accepted_at: datetime | None = None
    canceled_at: datetime | None = None
    claim_url: str


class AcceptTicketTransferInviteResponse(BaseModel):
    ticket_id: int
    owner_user_id: int
    status: str


class RevokeTicketTransferInviteResponse(BaseModel):
    id: int
    status: str
    revoked_at: datetime | None
