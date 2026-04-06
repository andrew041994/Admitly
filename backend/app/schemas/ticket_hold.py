from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateTicketHoldRequest(BaseModel):
    ticket_tier_id: int
    quantity: int = Field(gt=0)


class TicketHoldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    ticket_tier_id: int
    quantity: int
    expires_at: datetime
    created_at: datetime
    availability_remaining: int | None = None
