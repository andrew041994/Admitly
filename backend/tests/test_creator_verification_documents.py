from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from collections.abc import Iterator
import json

from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy.orm import Session

from app.api.creator_verification_documents import get_verification_document_storage
from app.core.config import Settings, settings
from app.main import app
from app.models.creator_verification_document import CreatorVerificationDocument
from app.models.user import User
from app.schemas.creator_verification_document import CreatorVerificationDocumentStatusResponse
from app.services.creator_verification import verify_creator_account
from app.services.creator_verification_documents import (
    cleanup_verification_documents,
    reject_pending_creator_document,
)
from app.services.verification_document_storage import (
    PrivateDocumentStream,
    VerificationImageValidationError,
    VerificationDocumentStorage,
    VerificationStorageConfigurationError,
    normalize_verification_image,
    validate_verification_storage_configuration,
)
from tests.utils import auth_headers, unique_email

UTC = timezone.utc


class FakePrivateStorage:
    def __init__(self, *, fail_delete: bool = False, on_put=None) -> None:  # noqa: ANN001
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.fail_delete = fail_delete
        self.on_put = on_put
        self.counter = 0

    def new_object_key(self) -> str:
        self.counter += 1
        return f"creator-verification/{self.counter:032x}.jpg"

    def put_document(self, *, object_key: str, image) -> None:  # noqa: ANN001
        self.objects[object_key] = image.data
        if self.on_put is not None:
            self.on_put()

    def get_document(self, *, object_key: str) -> PrivateDocumentStream:
        if object_key not in self.objects:
            from app.services.verification_document_storage import VerificationStorageError

            raise VerificationStorageError("unavailable")
        data = self.objects[object_key]
        return PrivateDocumentStream(BytesIO(data), "image/jpeg", len(data))

    def delete_document(self, *, object_key: str) -> None:
        if self.fail_delete:
            from app.services.verification_document_storage import VerificationStorageError

            raise VerificationStorageError("cleanup unavailable")
        self.objects.pop(object_key, None)
        self.deleted.append(object_key)


def _image_bytes(format_name: str = "PNG", *, size: tuple[int, int] = (48, 32), exif: bool = False) -> bytes:
    output = BytesIO()
    image = Image.new("RGB", size, color=(30, 90, 160))
    metadata = None
    if exif:
        metadata = Image.Exif()
        metadata[0x010E] = "synthetic private metadata"
    save_kwargs = {"exif": metadata} if metadata is not None else {}
    image.save(output, format=format_name, **save_kwargs)
    return output.getvalue()


def _configure_private_storage(monkeypatch, storage: FakePrivateStorage) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "verification_document_upload_enabled", True)
    monkeypatch.setattr(settings, "s3_verification_bucket", "private-verification-test")
    monkeypatch.setattr(settings, "s3_verification_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_verification_prefix", "creator-verification/")
    monkeypatch.setattr(settings, "s3_event_bucket", "public-event-covers-test")
    monkeypatch.setattr(settings, "rate_limit_verification_document_upload_count", 100)
    app.dependency_overrides[get_verification_document_storage] = lambda: storage


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_verification_document_storage, None)


def _user(db: Session, name: str, *, admin: bool = False, creator_status: str = "pending") -> User:
    user = User(
        email=unique_email(name),
        full_name=name,
        is_admin=admin,
        is_verified=True,
        email_verified_at=datetime.now(UTC),
        creator_age_identity_verification_status=creator_status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _tracked_document(
    db: Session,
    *,
    user: User,
    storage: FakePrivateStorage,
    document_status: str = "pending",
    created_at: datetime | None = None,
) -> CreatorVerificationDocument:
    key = storage.new_object_key()
    storage.objects[key] = _image_bytes("JPEG")
    document = CreatorVerificationDocument(
        user_id=user.id,
        storage_object_key=key,
        status=document_status,
        uploaded_at=datetime.now(UTC),
    )
    if created_at is not None:
        document.created_at = created_at
        document.updated_at = created_at
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def test_private_config_fails_closed_and_cannot_reuse_event_bucket(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "s3_verification_bucket", None)
    monkeypatch.setattr(settings, "s3_verification_region", None)
    with pytest.raises(VerificationStorageConfigurationError):
        validate_verification_storage_configuration()

    monkeypatch.setattr(settings, "s3_verification_bucket", "same-bucket")
    monkeypatch.setattr(settings, "s3_verification_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_event_bucket", "same-bucket")
    with pytest.raises(VerificationStorageConfigurationError):
        validate_verification_storage_configuration()

    with pytest.raises(ValueError, match="S3_VERIFICATION_BUCKET must be separate"):
        Settings(
            DATABASE_URL="postgresql+psycopg2://test:test@localhost/test",
            ENV="test",
            VERIFICATION_DOCUMENT_UPLOAD_ENABLED=True,
            S3_VERIFICATION_BUCKET="same-bucket",
            S3_VERIFICATION_REGION="us-east-1",
            S3_EVENT_BUCKET="same-bucket",
        )


def test_image_normalization_enforces_type_dimensions_and_strips_metadata(monkeypatch) -> None:  # noqa: ANN001
    normalized = normalize_verification_image(
        data=_image_bytes("JPEG", exif=True),
        declared_content_type="image/jpeg",
    )
    assert normalized.content_type == "image/jpeg"
    with Image.open(BytesIO(normalized.data)) as image:
        assert image.format == "JPEG"
        assert len(image.getexif()) == 0

    with pytest.raises(VerificationImageValidationError, match="does not match"):
        normalize_verification_image(data=_image_bytes("PNG"), declared_content_type="image/jpeg")
    with pytest.raises(VerificationImageValidationError, match="malformed"):
        normalize_verification_image(data=b"not-an-image", declared_content_type="image/png")
    with pytest.raises(VerificationImageValidationError, match="Only JPEG"):
        normalize_verification_image(data=b"synthetic", declared_content_type="application/pdf")

    monkeypatch.setattr(settings, "s3_verification_max_bytes", 10)
    with pytest.raises(VerificationImageValidationError, match="size limit"):
        normalize_verification_image(data=_image_bytes("PNG"), declared_content_type="image/png")


def test_private_storage_uses_opaque_keys_encryption_and_no_public_url(monkeypatch) -> None:  # noqa: ANN001
    class RecordingS3:
        def __init__(self) -> None:
            self.puts: list[dict] = []
            self.gets: list[dict] = []
            self.deletes: list[dict] = []

        def put_object(self, **kwargs) -> None:  # noqa: ANN003
            self.puts.append(kwargs)

        def get_object(self, **kwargs):  # noqa: ANN003, ANN201
            self.gets.append(kwargs)
            return {"Body": BytesIO(b"synthetic"), "ContentType": "image/jpeg", "ContentLength": 9}

        def delete_object(self, **kwargs) -> None:  # noqa: ANN003
            self.deletes.append(kwargs)

    fake_s3 = RecordingS3()
    monkeypatch.setattr(settings, "s3_verification_bucket", "private-verification-test")
    monkeypatch.setattr(settings, "s3_verification_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_verification_prefix", "creator-verification/")
    monkeypatch.setattr(settings, "s3_event_bucket", "public-covers-test")
    storage = VerificationDocumentStorage(client=fake_s3)
    key = storage.new_object_key()
    normalized = normalize_verification_image(data=_image_bytes("PNG"), declared_content_type="image/png")

    storage.put_document(object_key=key, image=normalized)
    stream = storage.get_document(object_key=key)
    storage.delete_document(object_key=key)

    assert key.startswith("creator-verification/") and key.endswith(".jpg")
    assert "synthetic" not in key
    assert fake_s3.puts[0]["Bucket"] == "private-verification-test"
    assert fake_s3.puts[0]["ServerSideEncryption"] == "AES256"
    assert fake_s3.puts[0]["CacheControl"] == "no-store, private, max-age=0"
    assert "ACL" not in fake_s3.puts[0]
    assert fake_s3.gets == [{"Bucket": "private-verification-test", "Key": key}]
    assert fake_s3.deletes == [{"Bucket": "private-verification-test", "Key": key}]
    assert stream.content_type == "image/jpeg"
    assert not hasattr(storage, "public_url")


def test_pending_and_revoked_accounts_can_upload_idempotently_without_public_reference(
    client: TestClient, db_session: Session, monkeypatch, caplog
) -> None:  # noqa: ANN001
    storage = FakePrivateStorage()
    _configure_private_storage(monkeypatch, storage)
    pending = _user(db_session, "pending-upload")

    first = client.post(
        "/account/creator-verification/document",
        headers=auth_headers(pending),
        files={"file": ("synthetic.png", _image_bytes("PNG"), "image/png")},
    )
    repeated = client.post(
        "/account/creator-verification/document",
        headers=auth_headers(pending),
        files={"file": ("different.png", _image_bytes("PNG"), "image/png")},
    )
    assert first.status_code == 201
    assert repeated.status_code == 201
    assert len(storage.objects) == 1
    assert first.json() == repeated.json()
    assert first.json()["document_pending_review"] is True
    serialized = first.text.lower()
    assert not any(term in serialized for term in ("object_key", "bucket", "url", "filename", "base64"))
    tracked = db_session.query(CreatorVerificationDocument).filter_by(user_id=pending.id).one()
    assert tracked.storage_object_key not in caplog.text

    revoked = _user(db_session, "revoked-upload", creator_status="revoked")
    response = client.post(
        "/account/creator-verification/document",
        headers=auth_headers(revoked),
        files={"file": ("synthetic.webp", _image_bytes("WEBP"), "image/webp")},
    )
    assert response.status_code == 201


def test_upload_authorization_validation_and_verified_account_policy(
    client: TestClient, db_session: Session, monkeypatch
) -> None:  # noqa: ANN001
    storage = FakePrivateStorage()
    _configure_private_storage(monkeypatch, storage)
    pending = _user(db_session, "upload-policy")
    verified = _user(db_session, "already-verified", creator_status="verified")

    unauthenticated = client.post(
        "/account/creator-verification/document",
        files={"file": ("synthetic.png", _image_bytes(), "image/png")},
    )
    assert unauthenticated.status_code == 401
    assert client.post(
        "/account/creator-verification/document",
        headers=auth_headers(verified),
        files={"file": ("synthetic.png", _image_bytes(), "image/png")},
    ).status_code == 409
    assert client.post(
        "/account/creator-verification/document",
        headers=auth_headers(pending),
        files={"file": ("synthetic.pdf", b"synthetic", "application/pdf")},
    ).status_code == 400
    assert client.post(
        "/account/creator-verification/document",
        headers=auth_headers(pending),
        files={"file": ("synthetic.png", b"malformed", "image/png")},
    ).status_code == 400


def test_upload_feature_is_disabled_by_default_and_rate_limited(
    client: TestClient, db_session: Session, monkeypatch
) -> None:  # noqa: ANN001
    creator = _user(db_session, "disabled-upload")
    monkeypatch.setattr(settings, "verification_document_upload_enabled", False)
    monkeypatch.setattr(settings, "s3_verification_bucket", None)
    monkeypatch.setattr(settings, "s3_verification_region", None)
    status_response = client.get(
        "/account/creator-verification/document",
        headers=auth_headers(creator),
    )
    assert status_response.status_code == 200
    assert status_response.json()["upload_enabled"] is False
    assert status_response.json()["max_upload_bytes"] == settings.s3_verification_max_bytes
    assert status_response.json()["allowed_content_types"] == ["image/jpeg", "image/png", "image/webp"]
    disabled = client.post(
        "/account/creator-verification/document",
        headers=auth_headers(creator),
        files={"file": ("synthetic.png", _image_bytes(), "image/png")},
    )
    assert disabled.status_code == 503

    storage = FakePrivateStorage()
    _configure_private_storage(monkeypatch, storage)
    monkeypatch.setattr(settings, "rate_limit_verification_document_upload_count", 1)
    first = client.post(
        "/account/creator-verification/document",
        headers=auth_headers(creator),
        files={"file": ("synthetic.png", b"malformed", "image/png")},
    )
    second = client.post(
        "/account/creator-verification/document",
        headers=auth_headers(creator),
        files={"file": ("synthetic.png", b"malformed", "image/png")},
    )
    assert first.status_code == 400
    assert second.status_code == 429
    assert "Retry-After" in second.headers


def test_concurrent_account_verification_deletes_uploaded_material(
    client: TestClient, db_session: Session, monkeypatch
) -> None:  # noqa: ANN001
    creator = _user(db_session, "concurrent-verification")

    def mark_verified() -> None:
        creator.creator_age_identity_verification_status = "verified"
        db_session.add(creator)
        db_session.commit()

    storage = FakePrivateStorage(on_put=mark_verified)
    _configure_private_storage(monkeypatch, storage)
    response = client.post(
        "/account/creator-verification/document",
        headers=auth_headers(creator),
        files={"file": ("synthetic.png", _image_bytes(), "image/png")},
    )
    assert response.status_code == 409
    document = db_session.query(CreatorVerificationDocument).filter_by(user_id=creator.id).one()
    assert document.status == "deleted"
    assert document.review_outcome == "verified"
    assert storage.objects == {}


def test_raw_content_is_admin_only_and_never_available_to_owner_or_other_user(
    client: TestClient, db_session: Session, monkeypatch
) -> None:  # noqa: ANN001
    storage = FakePrivateStorage()
    _configure_private_storage(monkeypatch, storage)
    owner = _user(db_session, "content-owner")
    other = _user(db_session, "content-other")
    admin = _user(db_session, "content-admin", admin=True)
    document = _tracked_document(db_session, user=owner, storage=storage)

    other_status = client.get(
        "/account/creator-verification/document", headers=auth_headers(other)
    )
    assert other_status.status_code == 200
    assert other_status.json()["document_status"] is None

    path = f"/admin/creator-verification/documents/{document.id}/content"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=auth_headers(owner)).status_code == 403
    assert client.get(path, headers=auth_headers(other)).status_code == 403
    response = client.get(path, headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == storage.objects[document.storage_object_key]


def test_verify_and_reject_delete_immediately_and_retain_safe_metadata(
    db_session: Session,
) -> None:
    storage = FakePrivateStorage()
    admin = _user(db_session, "review-admin", admin=True)
    creator = _user(db_session, "verify-delete")
    verified_document = _tracked_document(db_session, user=creator, storage=storage)

    verify_creator_account(
        db_session,
        creator_user_id=creator.id,
        actor_user_id=admin.id,
        note="Synthetic review completed.",
        document_storage=storage,
    )
    db_session.refresh(verified_document)
    assert creator.creator_age_identity_verification_status == "verified"
    assert verified_document.status == "deleted"
    assert verified_document.review_outcome == "verified"
    assert verified_document.deleted_at is not None
    assert verified_document.storage_object_key not in storage.objects

    rejected_creator = _user(db_session, "reject-delete", creator_status="revoked")
    rejected_document = _tracked_document(db_session, user=rejected_creator, storage=storage)
    result = reject_pending_creator_document(
        db_session,
        document_id=rejected_document.id,
        actor_user_id=admin.id,
        reason="Synthetic image did not meet verification requirements.",
        storage=storage,
    )
    assert result.status == "deleted"
    assert result.review_outcome == "rejected"
    assert rejected_creator.creator_age_identity_verification_status == "revoked"
    assert result.storage_object_key not in storage.objects


def test_admin_can_verify_pending_document_through_document_workflow(
    client: TestClient, db_session: Session, monkeypatch
) -> None:  # noqa: ANN001
    storage = FakePrivateStorage()
    _configure_private_storage(monkeypatch, storage)
    admin = _user(db_session, "document-verify-admin", admin=True)
    creator = _user(db_session, "document-verify-creator")
    document = _tracked_document(db_session, user=creator, storage=storage)
    path = f"/admin/creator-verification/documents/{document.id}/verify"

    assert client.post(path, headers=auth_headers(creator), json={"note": None}).status_code == 403
    response = client.post(
        path,
        headers=auth_headers(admin),
        json={"note": "Synthetic document review completed."},
    )
    assert response.status_code == 200
    assert response.json()["account_verification_status"] == "verified"
    assert response.json()["status"] == "deleted"
    assert response.json()["review_outcome"] == "verified"
    assert not any(key in response.json() for key in ("storage_object_key", "bucket", "url", "signed_url"))
    db_session.refresh(creator)
    assert creator.creator_age_identity_verification_status == "verified"
    assert storage.objects == {}


def test_delete_failure_records_cleanup_required_and_bounded_retry_is_idempotent(
    db_session: Session, monkeypatch
) -> None:  # noqa: ANN001
    failing_storage = FakePrivateStorage(fail_delete=True)
    admin = _user(db_session, "cleanup-admin", admin=True)
    creator = _user(db_session, "cleanup-creator")
    document = _tracked_document(db_session, user=creator, storage=failing_storage)

    verify_creator_account(
        db_session,
        creator_user_id=creator.id,
        actor_user_id=admin.id,
        note=None,
        document_storage=failing_storage,
    )
    db_session.refresh(document)
    assert creator.creator_age_identity_verification_status == "verified"
    assert document.status == "cleanup_required"
    assert document.cleanup_attempts == 1

    working_storage = FakePrivateStorage()
    working_storage.objects.update(failing_storage.objects)
    result = cleanup_verification_documents(db_session, storage=working_storage)
    db_session.refresh(document)
    assert result == {"selected": 1, "deleted": 1, "cleanup_required": 0}
    assert document.status == "deleted"
    assert document.cleanup_attempts == 2
    assert cleanup_verification_documents(db_session, storage=working_storage)["selected"] == 0


def test_expired_pending_document_cleanup_uses_configured_backstop(
    db_session: Session, monkeypatch
) -> None:  # noqa: ANN001
    storage = FakePrivateStorage()
    creator = _user(db_session, "expired-upload")
    now = datetime.now(UTC)
    document = _tracked_document(
        db_session,
        user=creator,
        storage=storage,
        created_at=now - timedelta(days=8),
    )
    monkeypatch.setattr(settings, "s3_verification_retention_days", 7)

    result = cleanup_verification_documents(db_session, storage=storage, now=now)
    db_session.refresh(document)
    assert result["deleted"] == 1
    assert document.status == "deleted"
    assert document.review_outcome == "expired"


def test_public_schemas_and_event_routes_expose_no_storage_fields() -> None:
    names = set(CreatorVerificationDocumentStatusResponse.model_fields)
    assert not names.intersection(
        {"storage_object_key", "object_key", "bucket", "public_url", "signed_url", "filename", "contents"}
    )
    source = Path("app/schemas/event.py").read_text()
    assert "CreatorVerificationDocument" not in source
    assert "storage_object_key" not in source


def test_private_bucket_policy_templates_are_narrow_and_expire_within_seven_days() -> None:
    root = Path("../infrastructure/verification-s3")
    public_access = json.loads((root / "public-access-block.json").read_text())
    assert all(public_access.values())
    ownership = json.loads((root / "ownership-controls.json").read_text())
    assert ownership["Rules"] == [{"ObjectOwnership": "BucketOwnerEnforced"}]
    encryption = json.loads((root / "default-encryption.json").read_text())
    assert encryption["Rules"][0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"

    lifecycle = json.loads((root / "lifecycle.json").read_text())["Rules"][0]
    assert lifecycle["Status"] == "Enabled"
    assert lifecycle["Filter"]["Prefix"] == "creator-verification/"
    assert lifecycle["Expiration"]["Days"] <= 7

    runtime = json.loads((root / "runtime-iam-policy.json").read_text())["Statement"]
    assert len(runtime) == 1
    assert set(runtime[0]["Action"]) == {"s3:PutObject", "s3:GetObject", "s3:DeleteObject"}
    assert runtime[0]["Resource"].endswith("/creator-verification/*")
    serialized = json.dumps(runtime)
    assert "s3:*" not in serialized
    assert "ListAllMyBuckets" not in serialized
    assert "event-covers" not in serialized

    bucket_policy = json.loads((root / "bucket-policy.json").read_text())["Statement"]
    tls_statement = next(row for row in bucket_policy if row["Sid"] == "DenyNonTLSRequests")
    assert tls_statement["Effect"] == "Deny"
    assert tls_statement["Condition"]["Bool"]["aws:SecureTransport"] == "false"
    assert all(row["Effect"] == "Deny" for row in bucket_policy)
