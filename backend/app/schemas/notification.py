from pydantic import BaseModel


class NotificationDispatchResponse(BaseModel):
    success: bool
    channel_results: dict[str, str]


class PushTokenRegisterRequest(BaseModel):
    token: str
    platform: str | None = None


class PushTokenRegisterResponse(BaseModel):
    success: bool
    token: str
    platform: str | None = None
    is_active: bool


class PushTokenDeleteRequest(BaseModel):
    token: str


class PushTokenDeleteResponse(BaseModel):
    success: bool
