from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AccountProfileResponse(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    is_verified: bool
    email_verified_at: datetime | None
    requires_email_verification: bool
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
