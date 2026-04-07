from datetime import datetime

from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["integrations:read"])


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class ApiKeyCreateResponse(ApiKeyResponse):
    raw_key: str


class WebhookEndpointCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_url: str = Field(min_length=1, max_length=1024)
    subscribed_events: list[str]


class WebhookEndpointPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_url: str | None = Field(default=None, min_length=1, max_length=1024)
    subscribed_events: list[str] | None = None
    is_active: bool | None = None


class WebhookEndpointResponse(BaseModel):
    id: int
    name: str
    target_url: str
    subscribed_events: list[str]
    schema_version: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


class WebhookEndpointCreateResponse(WebhookEndpointResponse):
    signing_secret: str


class WebhookDeliveryResponse(BaseModel):
    id: int
    endpoint_id: int
    endpoint_url: str
    event_id: str
    event_type: str
    schema_version: str
    attempt_number: int
    status: str
    requested_at: datetime
    response_status_code: int | None
    failure_reason: str | None
    next_retry_at: datetime | None
    delivered_at: datetime | None
    delivery_kind: str
    redelivery_of_delivery_id: int | None


class IntegrationCatalogResponse(BaseModel):
    version: str
    supported_events: list[str]
    signature_headers: dict[str, str]
