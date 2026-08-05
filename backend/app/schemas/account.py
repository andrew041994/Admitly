from datetime import datetime

from pydantic import BaseModel, field_validator

from app.lib.phone_numbers import InvalidPhoneNumberError, normalize_phone_number


class UpdateProfileRequest(BaseModel):
    full_name: str
    phone_number: str | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        try:
            return normalize_phone_number(value)
        except InvalidPhoneNumberError as exc:
            raise ValueError(str(exc)) from exc


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AccountProfileResponse(BaseModel):
    id: int
    email: str
    full_name: str
    phone_number: str | None
    phone_is_verified: bool
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
