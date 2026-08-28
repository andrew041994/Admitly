from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import get_current_admin_id, get_current_user
from app.api.rate_limit import apply_rate_limit, request_client_ip
from app.core.config import settings
from app.db.session import get_db
from app.models.creator_verification_document import CreatorVerificationDocument
from app.models.user import User
from app.schemas.creator_verification_document import (
    AdminCreatorVerificationDocumentResponse,
    CreatorVerificationDocumentCleanupResponse,
    CreatorVerificationDocumentRejectionRequest,
    CreatorVerificationDocumentStatusResponse,
    CreatorVerificationDocumentVerificationRequest,
)
from app.services.creator_verification_documents import (
    active_document_for_user,
    delete_tracked_document,
    latest_document_for_user,
    reject_pending_creator_document,
)
from app.services.verification_document_storage import (
    VerificationDocumentStorage,
    VerificationImageValidationError,
    VerificationStorageConfigurationError,
    VerificationStorageError,
    normalize_verification_image,
    require_verification_document_upload_enabled,
)
from app.services.creator_verification import verify_creator_account

UTC = timezone.utc
router = APIRouter(tags=["creator-verification"])


def get_verification_document_storage() -> VerificationDocumentStorage:
    try:
        return VerificationDocumentStorage()
    except VerificationStorageConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Private verification storage is unavailable.",
        ) from None


def _user_status_response(
    user: User, document: CreatorVerificationDocument | None
) -> CreatorVerificationDocumentStatusResponse:
    upload_enabled = True
    try:
        require_verification_document_upload_enabled()
    except VerificationStorageConfigurationError:
        upload_enabled = False
    return CreatorVerificationDocumentStatusResponse(
        account_verification_status=user.creator_age_identity_verification_status,
        upload_enabled=upload_enabled,
        max_upload_bytes=settings.s3_verification_max_bytes,
        allowed_content_types=["image/jpeg", "image/png", "image/webp"],
        document_pending_review=document is not None and document.status == "pending",
        document_status=document.status if document is not None else None,
        review_outcome=document.review_outcome if document is not None else None,
        uploaded_at=document.uploaded_at if document is not None else None,
        reviewed_at=document.reviewed_at if document is not None else None,
        deleted_at=document.deleted_at if document is not None else None,
    )


def _admin_response(
    document: CreatorVerificationDocument, account_status: str
) -> AdminCreatorVerificationDocumentResponse:
    return AdminCreatorVerificationDocumentResponse(
        id=document.id,
        user_id=document.user_id,
        account_verification_status=account_status,
        status=document.status,
        review_outcome=document.review_outcome,
        uploaded_at=document.uploaded_at,
        reviewed_at=document.reviewed_at,
        reviewed_by_user_id=document.reviewed_by_user_id,
        deleted_at=document.deleted_at,
        cleanup_required_at=document.cleanup_required_at,
        cleanup_attempts=document.cleanup_attempts,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get(
    "/account/creator-verification/document",
    response_model=CreatorVerificationDocumentStatusResponse,
)
def get_own_creator_verification_document_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CreatorVerificationDocumentStatusResponse:
    return _user_status_response(
        current_user,
        latest_document_for_user(db, user_id=current_user.id),
    )


@router.post(
    "/account/creator-verification/document",
    response_model=CreatorVerificationDocumentStatusResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_own_creator_verification_document(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: VerificationDocumentStorage = Depends(get_verification_document_storage),
) -> CreatorVerificationDocumentStatusResponse:
    try:
        require_verification_document_upload_enabled()
    except VerificationStorageConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification document upload is not available.",
        ) from None
    if current_user.creator_age_identity_verification_status == "verified":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Creator account is already verified; reverification has not been requested.",
        )

    apply_rate_limit(
        scope="verification_document_upload",
        key=f"{current_user.id}:{request_client_ip(request)}",
        limit=settings.rate_limit_verification_document_upload_count,
        window_seconds=settings.rate_limit_verification_document_upload_window_seconds,
    )
    existing = active_document_for_user(db, user_id=current_user.id)
    if existing is not None:
        if existing.status == "pending":
            return _user_status_response(current_user, existing)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A previous verification upload requires cleanup before another submission.",
        )

    raw = await file.read(settings.s3_verification_max_bytes + 1)
    await file.close()
    if len(raw) > settings.s3_verification_max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image is too large.")
    try:
        normalized = normalize_verification_image(data=raw, declared_content_type=file.content_type)
    except VerificationImageValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    document = CreatorVerificationDocument(
        user_id=current_user.id,
        storage_object_key=storage.new_object_key(),
        status="uploading",
    )
    db.add(document)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = active_document_for_user(db, user_id=current_user.id)
        if existing is not None and existing.status == "pending":
            return _user_status_response(current_user, existing)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A verification upload is already active.",
        ) from None
    db.refresh(document)

    try:
        storage.put_document(object_key=document.storage_object_key, image=normalized)
    except VerificationStorageError:
        document.status = "cleanup_required"
        document.review_outcome = "upload_failed"
        document.cleanup_required_at = datetime.now(UTC)
        db.add(document)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification upload could not be completed safely. Please try again later.",
        ) from None

    locked_user = db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
    ).scalar_one()
    if locked_user.creator_age_identity_verification_status == "verified":
        document.status = "reviewed"
        document.review_outcome = "verified"
        document.reviewed_at = datetime.now(UTC)
        db.add(document)
        db.commit()
        delete_tracked_document(db, document_id=document.id, storage=storage)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Creator account was verified while the upload was being processed; temporary material was deleted.",
        )

    document.status = "pending"
    document.uploaded_at = datetime.now(UTC)
    db.add(document)
    db.commit()
    db.refresh(document)
    return _user_status_response(current_user, document)


@router.get(
    "/admin/creator-verification/documents",
    response_model=list[AdminCreatorVerificationDocumentResponse],
)
def list_creator_verification_documents(
    document_status: str = Query(default="pending", alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin_user_id: int = Depends(get_current_admin_id),
) -> list[AdminCreatorVerificationDocumentResponse]:
    allowed = {"uploading", "pending", "reviewed", "deleted", "cleanup_required"}
    if document_status not in allowed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status.")
    rows = db.execute(
        select(CreatorVerificationDocument, User.creator_age_identity_verification_status)
        .join(User, User.id == CreatorVerificationDocument.user_id)
        .where(CreatorVerificationDocument.status == document_status)
        .order_by(CreatorVerificationDocument.created_at.asc(), CreatorVerificationDocument.id.asc())
        .limit(limit)
    ).all()
    return [_admin_response(document, account_status) for document, account_status in rows]


def _stream_private_body(body: object) -> Iterator[bytes]:
    try:
        if hasattr(body, "iter_chunks"):
            yield from body.iter_chunks(chunk_size=64 * 1024)  # type: ignore[attr-defined]
            return
        while True:
            chunk = body.read(64 * 1024)  # type: ignore[attr-defined]
            if not chunk:
                break
            yield chunk
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()


@router.get("/admin/creator-verification/documents/{document_id}/content")
def review_creator_verification_document_content(
    document_id: int,
    db: Session = Depends(get_db),
    _admin_user_id: int = Depends(get_current_admin_id),
    storage: VerificationDocumentStorage = Depends(get_verification_document_storage),
) -> StreamingResponse:
    document = db.execute(
        select(CreatorVerificationDocument).where(CreatorVerificationDocument.id == document_id)
    ).scalar_one_or_none()
    if document is None or document.status != "pending":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending verification submission not found.")
    try:
        private_stream = storage.get_document(object_key=document.storage_object_key)
    except VerificationStorageError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification image is temporarily unavailable.",
        ) from None
    headers = {
        "Cache-Control": "no-store, private, max-age=0",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": 'inline; filename="verification-image.jpg"',
    }
    if private_stream.content_length is not None:
        headers["Content-Length"] = str(private_stream.content_length)
    return StreamingResponse(
        _stream_private_body(private_stream.body),
        media_type=private_stream.content_type,
        headers=headers,
    )


@router.post(
    "/admin/creator-verification/documents/{document_id}/verify",
    response_model=AdminCreatorVerificationDocumentResponse,
)
def verify_creator_verification_document(
    document_id: int,
    payload: CreatorVerificationDocumentVerificationRequest,
    db: Session = Depends(get_db),
    admin_user_id: int = Depends(get_current_admin_id),
    storage: VerificationDocumentStorage = Depends(get_verification_document_storage),
) -> AdminCreatorVerificationDocumentResponse:
    document = db.execute(
        select(CreatorVerificationDocument).where(CreatorVerificationDocument.id == document_id)
    ).scalar_one_or_none()
    if document is None or document.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending verification submission not found.",
        )
    verify_creator_account(
        db,
        creator_user_id=document.user_id,
        actor_user_id=admin_user_id,
        note=payload.note.strip() if payload.note and payload.note.strip() else None,
        document_storage=storage,
    )
    refreshed = db.get(CreatorVerificationDocument, document.id)
    if refreshed is None:  # pragma: no cover - defensive; records are retained as safe metadata
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification submission not found.")
    account_status = db.execute(
        select(User.creator_age_identity_verification_status).where(User.id == refreshed.user_id)
    ).scalar_one()
    return _admin_response(refreshed, account_status)


@router.post(
    "/admin/creator-verification/documents/{document_id}/reject",
    response_model=AdminCreatorVerificationDocumentResponse,
)
def reject_creator_verification_document(
    document_id: int,
    payload: CreatorVerificationDocumentRejectionRequest,
    db: Session = Depends(get_db),
    admin_user_id: int = Depends(get_current_admin_id),
    storage: VerificationDocumentStorage = Depends(get_verification_document_storage),
) -> AdminCreatorVerificationDocumentResponse:
    document = reject_pending_creator_document(
        db,
        document_id=document_id,
        actor_user_id=admin_user_id,
        reason=payload.reason,
        storage=storage,
    )
    account_status = db.execute(
        select(User.creator_age_identity_verification_status).where(User.id == document.user_id)
    ).scalar_one()
    return _admin_response(document, account_status)


@router.post(
    "/admin/creator-verification/documents/{document_id}/cleanup",
    response_model=CreatorVerificationDocumentCleanupResponse,
)
def retry_creator_verification_document_cleanup(
    document_id: int,
    db: Session = Depends(get_db),
    _admin_user_id: int = Depends(get_current_admin_id),
    storage: VerificationDocumentStorage = Depends(get_verification_document_storage),
) -> CreatorVerificationDocumentCleanupResponse:
    document = db.get(CreatorVerificationDocument, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification submission not found.")
    if document.status not in {"reviewed", "cleanup_required"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Verification submission is not ready for cleanup.")
    success = delete_tracked_document(db, document_id=document.id, storage=storage)
    refreshed = db.get(CreatorVerificationDocument, document.id)
    return CreatorVerificationDocumentCleanupResponse(
        success=success,
        status=refreshed.status if refreshed is not None else "deleted",
    )
