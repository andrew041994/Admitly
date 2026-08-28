from datetime import datetime

from pydantic import BaseModel, Field


class CreatorVerificationDocumentStatusResponse(BaseModel):
    account_verification_status: str
    document_pending_review: bool
    document_status: str | None
    review_outcome: str | None
    uploaded_at: datetime | None
    reviewed_at: datetime | None
    deleted_at: datetime | None


class AdminCreatorVerificationDocumentResponse(BaseModel):
    id: int
    user_id: int
    account_verification_status: str
    status: str
    review_outcome: str | None
    uploaded_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_user_id: int | None
    deleted_at: datetime | None
    cleanup_required_at: datetime | None
    cleanup_attempts: int
    created_at: datetime
    updated_at: datetime


class CreatorVerificationDocumentRejectionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class CreatorVerificationDocumentCleanupResponse(BaseModel):
    success: bool
    status: str
