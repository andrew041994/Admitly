from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin_action_audit import AdminActionAudit
from app.models.creator_age_identity_verification_history import CreatorAgeIdentityVerificationHistory
from app.models.user import User
from app.services.creator_verification_documents import (
    delete_tracked_document,
    mark_document_reviewed,
)
from app.services.verification_document_storage import VerificationDocumentStorage

UTC = timezone.utc


def get_creator_verification_user_for_update(db: Session, *, user_id: int) -> User:
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


def verify_creator_account(
    db: Session,
    *,
    creator_user_id: int,
    actor_user_id: int,
    note: str | None,
    document_storage: VerificationDocumentStorage | None = None,
) -> User:
    user = get_creator_verification_user_for_update(db, user_id=creator_user_id)
    if user.creator_age_identity_verification_status == "verified":
        return user

    previous_status = user.creator_age_identity_verification_status
    verified_at = datetime.now(UTC)
    temporary_material = mark_document_reviewed(
        db,
        user_id=user.id,
        actor_user_id=actor_user_id,
        outcome="verified",
    )
    user.creator_age_identity_verification_status = "verified"
    user.creator_age_identity_verified_at = verified_at
    user.creator_age_identity_verified_by_user_id = actor_user_id
    user.creator_age_identity_verification_note = note
    user.creator_age_identity_revoked_at = None
    user.creator_age_identity_revoked_by_user_id = None
    user.creator_age_identity_revocation_reason = None
    db.add(user)
    db.add(
        CreatorAgeIdentityVerificationHistory(
            user_id=user.id,
            action="verified",
            actor_user_id=actor_user_id,
            previous_status=previous_status,
            new_status="verified",
            note=note,
        )
    )
    db.add(
        AdminActionAudit(
            actor_user_id=actor_user_id,
            target_type="user",
            target_id=str(user.id),
            action_type="verify_creator_age_identity",
            reason=note,
            metadata_json={
                "previous_status": previous_status,
                "new_status": "verified",
                "verified_at": verified_at.isoformat(),
                "temporary_material_submitted": temporary_material is not None,
                "temporary_material_retention": "delete_immediately",
            },
        )
    )
    db.commit()
    db.refresh(user)
    if temporary_material is not None:
        delete_tracked_document(
            db,
            document_id=temporary_material.id,
            storage=document_storage,
        )
    return user


def revoke_creator_account_verification(
    db: Session,
    *,
    creator_user_id: int,
    actor_user_id: int,
    reason: str,
) -> User:
    user = get_creator_verification_user_for_update(db, user_id=creator_user_id)
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A revocation reason is required.")
    if user.creator_age_identity_verification_status != "verified":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Creator verification is not currently active.")

    revoked_at = datetime.now(UTC)
    user.creator_age_identity_verification_status = "revoked"
    user.creator_age_identity_revoked_at = revoked_at
    user.creator_age_identity_revoked_by_user_id = actor_user_id
    user.creator_age_identity_revocation_reason = normalized_reason
    db.add(user)
    db.add(
        CreatorAgeIdentityVerificationHistory(
            user_id=user.id,
            action="revoked",
            actor_user_id=actor_user_id,
            previous_status="verified",
            new_status="revoked",
            note=normalized_reason,
        )
    )
    db.add(
        AdminActionAudit(
            actor_user_id=actor_user_id,
            target_type="user",
            target_id=str(user.id),
            action_type="revoke_creator_age_identity",
            reason=normalized_reason,
            metadata_json={
                "previous_status": "verified",
                "new_status": "revoked",
                "revoked_at": revoked_at.isoformat(),
                "existing_approved_events_unchanged": True,
            },
        )
    )
    db.commit()
    db.refresh(user)
    return user
