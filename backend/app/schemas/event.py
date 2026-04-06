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
