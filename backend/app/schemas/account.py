from datetime import datetime

from pydantic import BaseModel


class UpdateProfileRequest(BaseModel):
    full_name: str
    phone_number: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AccountProfileResponse(BaseModel):
    id: int
    email: str
    full_name: str
    phone_number: str | None
    is_active: bool
    is_verified: bool
    my_tickets_count: int
    my_events_count: int
    staff_events_count: int


class AccountStaffEventResponse(BaseModel):
    event_id: int
    title: str
    start_at: datetime
    end_at: datetime | None
    timezone: str | None
    venue_name: str | None
    role: str | None
    status: str | None
