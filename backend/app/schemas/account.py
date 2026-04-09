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
