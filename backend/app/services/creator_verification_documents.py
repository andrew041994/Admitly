from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.admin_action_audit import AdminActionAudit
from app.models.creator_age_identity_verification_history import CreatorAgeIdentityVerificationHistory
from app.models.creator_verification_document import CreatorVerificationDocument
from app.models.user import User
from app.services.verification_document_storage import (
    VerificationDocumentStorage,
    VerificationStorageConfigurationError,
    VerificationStorageError,
)

UTC = timezone.utc
ACTIVE_DOCUMENT_STATUSES = ("uploading", "pending", "cleanup_required")


def latest_document_for_user(db: Session, *, user_id: int) -> CreatorVerificationDocument | None:
    return db.execute(
        select(CreatorVerificationDocument)
        .where(CreatorVerificationDocument.user_id == user_id)
        .order_by(CreatorVerificationDocument.created_at.desc(), CreatorVerificationDocument.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def active_document_for_user(
    db: Session, *, user_id: int, for_update: bool = False
) -> CreatorVerificationDocument | None:
    query = select(CreatorVerificationDocument).where(
        CreatorVerificationDocument.user_id == user_id,
        CreatorVerificationDocument.status.in_(ACTIVE_DOCUMENT_STATUSES),
    )
    if for_update:
        query = query.with_for_update()
    return db.execute(query).scalar_one_or_none()


def pending_document_for_review(
    db: Session, *, user_id: int
) -> CreatorVerificationDocument | None:
    return db.execute(
        select(CreatorVerificationDocument)
        .where(
            CreatorVerificationDocument.user_id == user_id,
            CreatorVerificationDocument.status == "pending",
        )
        .with_for_update()
    ).scalar_one_or_none()


def mark_document_reviewed(
    db: Session,
    *,
    user_id: int,
    actor_user_id: int,
    outcome: str,
) -> CreatorVerificationDocument | None:
    document = pending_document_for_review(db, user_id=user_id)
    if document is None:
        return None
    document.status = "reviewed"
    document.review_outcome = outcome
    document.reviewed_at = datetime.now(UTC)
    document.reviewed_by_user_id = actor_user_id
    db.add(document)
    return document


def delete_tracked_document(
    db: Session,
    *,
    document_id: int,
    storage: VerificationDocumentStorage | None = None,
) -> bool:
    document = db.execute(
        select(CreatorVerificationDocument)
        .where(CreatorVerificationDocument.id == document_id)
        .with_for_update()
    ).scalar_one_or_none()
    if document is None or document.status == "deleted":
        return True

    try:
        private_storage = storage or VerificationDocumentStorage()
        private_storage.delete_document(object_key=document.storage_object_key)
    except (VerificationStorageConfigurationError, VerificationStorageError):
        now = datetime.now(UTC)
        document.status = "cleanup_required"
        document.cleanup_required_at = document.cleanup_required_at or now
        document.last_cleanup_attempt_at = now
        document.cleanup_attempts += 1
        db.add(document)
        db.commit()
        return False

    now = datetime.now(UTC)
    document.status = "deleted"
    document.deleted_at = now
    document.cleanup_required_at = None
    document.last_cleanup_attempt_at = now
    document.cleanup_attempts += 1
    db.add(document)
    db.commit()
    return True


def reject_pending_creator_document(
    db: Session,
    *,
    document_id: int,
    actor_user_id: int,
    reason: str,
    storage: VerificationDocumentStorage | None = None,
) -> CreatorVerificationDocument:
    document = db.execute(
        select(CreatorVerificationDocument)
        .where(CreatorVerificationDocument.id == document_id)
        .with_for_update()
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification submission not found.")
    if document.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Verification submission is not pending review.")
    user = db.execute(select(User).where(User.id == document.user_id).with_for_update()).scalar_one()
    if user.creator_age_identity_verification_status == "verified":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Creator account is already verified.")

    normalized_reason = reason.strip()
    if not normalized_reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A rejection reason is required.")
    previous_status = user.creator_age_identity_verification_status
    now = datetime.now(UTC)
    document.status = "reviewed"
    document.review_outcome = "rejected"
    document.reviewed_at = now
    document.reviewed_by_user_id = actor_user_id
    db.add(document)
    db.add(
        CreatorAgeIdentityVerificationHistory(
            user_id=user.id,
            action="rejected",
            actor_user_id=actor_user_id,
            previous_status=previous_status,
            new_status=previous_status,
            note=normalized_reason,
        )
    )
    db.add(
        AdminActionAudit(
            actor_user_id=actor_user_id,
            target_type="user",
            target_id=str(user.id),
            action_type="reject_creator_age_identity",
            reason=normalized_reason,
            metadata_json={
                "account_status": previous_status,
                "temporary_material_retention": "delete_immediately",
            },
        )
    )
    db.commit()
    delete_tracked_document(db, document_id=document.id, storage=storage)
    return db.get(CreatorVerificationDocument, document.id) or document


def cleanup_verification_documents(
    db: Session,
    *,
    storage: VerificationDocumentStorage | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Delete a bounded batch; S3 lifecycle may already have removed an object."""
    current_time = now or datetime.now(UTC)
    cutoff = current_time - timedelta(days=settings.s3_verification_retention_days)
    document_ids = list(
        db.execute(
            select(CreatorVerificationDocument.id)
            .where(
                or_(
                    CreatorVerificationDocument.status.in_(("reviewed", "cleanup_required")),
                    (
                        CreatorVerificationDocument.status.in_(("uploading", "pending"))
                        & (CreatorVerificationDocument.created_at <= cutoff)
                    ),
                )
            )
            .order_by(CreatorVerificationDocument.created_at.asc(), CreatorVerificationDocument.id.asc())
            .limit(settings.verification_document_cleanup_batch_size)
        ).scalars()
    )

    deleted = 0
    cleanup_required = 0
    for document_id in document_ids:
        document = db.get(CreatorVerificationDocument, document_id)
        if document is not None and document.status in {"uploading", "pending"}:
            document.review_outcome = "expired"
            db.add(document)
            db.commit()
        if delete_tracked_document(db, document_id=document_id, storage=storage):
            deleted += 1
        else:
            cleanup_required += 1
    return {"selected": len(document_ids), "deleted": deleted, "cleanup_required": cleanup_required}
