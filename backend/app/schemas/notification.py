from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class NotificationDispatchResponse(BaseModel):
    success: bool
    channel_results: dict[str, str]


class PushTokenRegisterRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    platform: str | None = Field(default=None, pattern="^(ios|android)$")
    installation_id: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("token", "installation_id")
    @classmethod
    def trim_values(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("token")
    @classmethod
    def require_expo_token(cls, value: str) -> str:
        if not (
            (value.startswith("ExponentPushToken[") or value.startswith("ExpoPushToken["))
            and value.endswith("]")
        ):
            raise ValueError("A valid Expo push token is required.")
        return value


class PushTokenRegisterResponse(BaseModel):
    success: bool
    device_registered: bool


class PushTokenDeleteRequest(BaseModel):
    token: str | None = Field(default=None, min_length=10, max_length=512)
    installation_id: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def require_identifier(self) -> "PushTokenDeleteRequest":
        if not (self.token or self.installation_id):
            raise ValueError("A token or installation identifier is required.")
        return self


class PushTokenDeleteResponse(BaseModel):
    success: bool


class InAppNotificationResponse(BaseModel):
    id: int
    notification_type: str
    title: str
    body: str
    is_read: bool
    read_at: datetime | None
    route_key: str | None
    route_params: dict[str, int | str]
    related_entity_type: str | None
    related_entity_id: int | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[InAppNotificationResponse]
    next_cursor: int | None


class UnreadCountResponse(BaseModel):
    unread_count: int


class MarkAllReadResponse(BaseModel):
    updated_count: int
    unread_count: int


class NotificationPreferencesResponse(BaseModel):
    ticket_activity_push_enabled: bool
    event_reminders_push_enabled: bool
    nearby_events_push_enabled: bool
    location_discovery_enabled: bool
    has_saved_location: bool
    location_updated_at: datetime | None


class NotificationPreferencesUpdateRequest(BaseModel):
    ticket_activity_push_enabled: bool | None = None
    event_reminders_push_enabled: bool | None = None
    nearby_events_push_enabled: bool | None = None
    location_discovery_enabled: bool | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def coordinates_are_paired(self) -> "NotificationPreferencesUpdateRequest":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be provided together.")
        if self.location_discovery_enabled is True and self.latitude is None:
            raise ValueError("A confirmed location is required to enable nearby events.")
        return self
