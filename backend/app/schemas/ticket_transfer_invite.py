from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class ResolveTicketTransferRecipientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        if len(normalized) > 255 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class ResolveTicketTransferRecipientResponse(BaseModel):
    recipient_display_name: str
    recipient_email: str
    masked_email: str
    recipient_resolution_reference: str
    resolution_expires_at: datetime


class CreateTicketTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_resolution_reference: str

    @field_validator("recipient_resolution_reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        reference = value.strip()
        if not 32 <= len(reference) <= 256:
            raise ValueError("Recipient confirmation has expired. Look up the recipient again.")
        return reference


class TicketTransferSummaryResponse(BaseModel):
    id: int
    ticket_id: int
    direction: Literal["incoming", "outgoing"]
    status: str
    recipient_identifier: str
    event_title: str
    ticket_tier_name: str
    starts_at: datetime
    expires_at: datetime | None
    accepted_at: datetime | None
    declined_at: datetime | None
    canceled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TicketTransferActionResponse(BaseModel):
    id: int
    ticket_id: int
    status: str
    accepted_at: datetime | None = None
    declined_at: datetime | None = None
    canceled_at: datetime | None = None
