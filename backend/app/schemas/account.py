from pydantic import BaseModel


class UpdateProfileRequest(BaseModel):
    full_name: str
    phone_number: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
