from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from collections.abc import Iterator

from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy.orm import Session

from app.api import events as events_api
from app.core.config import settings
from app.main import app
from app.models.admin_action_audit import AdminActionAudit
from app.models.enums import EventStaffRole
from app.models.event import Event
from app.models.event_staff import EventStaff
from app.models.organizer_profile import OrganizerProfile
from app.models.user import User
from tests.utils import auth_headers, unique_email


UTC = timezone.utc


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


class FakeS3Client:
    def __init__(self, *, fail: bool = False, on_put=None) -> None:  # noqa: ANN001
        self.fail = fail
        self.on_put = on_put
        self.puts: list[dict] = []

    def put_object(self, **kwargs) -> None:  # noqa: ANN003
        if self.fail:
            raise ClientError({"Error": {"Code": "ServiceUnavailable", "Message": "unavailable"}}, "PutObject")
        self.puts.append(kwargs)
        if self.on_put is not None:
            self.on_put()


def _seed_user(db: Session, name: str, *, is_admin: bool = False) -> User:
    user = User(email=unique_email(name), full_name=name, is_admin=is_admin)
    db.add(user)
    db.flush()
    return user


def _seed_event(db: Session, owner: User, *, cover_image_url: str | None = None) -> Event:
    profile = OrganizerProfile(user_id=owner.id, business_name=owner.full_name, display_name=owner.full_name)
    db.add(profile)
    db.flush()
    event = Event(
        organizer_id=profile.id,
        title=f"Cover event {owner.id}",
        slug=f"cover-event-{owner.id}",
        cover_image_url=cover_image_url,
        start_at=datetime.now(UTC) + timedelta(days=1),
        end_at=datetime.now(UTC) + timedelta(days=1, hours=2),
    )
    db.add(event)
    db.flush()
    return event


def _image_bytes(format_name: str = "PNG", *, size: tuple[int, int] = (32, 24)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(20, 80, 140)).save(output, format=format_name)
    return output.getvalue()


def _configure_s3(monkeypatch, client: FakeS3Client) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "aws_access_key_id", "test-access-key")
    monkeypatch.setattr(settings, "aws_secret_access_key", "test-secret-key")
    monkeypatch.setattr(settings, "aws_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_event_bucket", "test-event-covers")
    monkeypatch.setattr(settings, "s3_event_prefix", "event-covers/")
    monkeypatch.setattr(settings, "s3_public_base_url", "https://images.test.local")
    monkeypatch.setattr(events_api.boto3, "client", lambda *_args, **_kwargs: client)


def _upload(client: TestClient, event: Event, user: User, *, data: bytes | None = None, mime: str = "image/png"):
    return client.post(
        f"/events/{event.id}/cover-image",
        headers=auth_headers(user),
        files={"file": ("cover.png", data if data is not None else _image_bytes(), mime)},
    )


def test_event_creator_can_replace_cover_and_audit_change(client: TestClient, db_session: Session, monkeypatch) -> None:  # noqa: ANN001
    owner = _seed_user(db_session, "cover-owner")
    event = _seed_event(db_session, owner, cover_image_url="https://images.test.local/event-covers/old.png")
    s3 = FakeS3Client()
    _configure_s3(monkeypatch, s3)

    response = _upload(client, event, owner)

    assert response.status_code == 201
    db_session.refresh(event)
    assert event.cover_image_url == response.json()["url"]
    assert len(s3.puts) == 1
    assert s3.puts[0]["ContentType"] == "image/png"
    audit = db_session.query(AdminActionAudit).filter_by(action_type="event_cover_replaced").one()
    assert audit.actor_user_id == owner.id
    assert audit.target_id == str(event.id)
    assert audit.metadata_json["object_key"] in response.json()["url"]
    assert audit.metadata_json["previous_object_key"] == "event-covers/old.png"


def test_admin_can_replace_any_event_cover(client: TestClient, db_session: Session, monkeypatch) -> None:  # noqa: ANN001
    owner = _seed_user(db_session, "admin-cover-owner")
    admin = _seed_user(db_session, "cover-admin", is_admin=True)
    event = _seed_event(db_session, owner)
    _configure_s3(monkeypatch, FakeS3Client())

    response = _upload(client, event, admin)

    assert response.status_code == 201
    audit = db_session.query(AdminActionAudit).filter_by(action_type="event_cover_uploaded").one()
    assert audit.actor_user_id == admin.id


def test_unrelated_user_and_event_staff_cannot_change_cover(client: TestClient, db_session: Session, monkeypatch) -> None:  # noqa: ANN001
    owner = _seed_user(db_session, "restricted-cover-owner")
    other = _seed_user(db_session, "unrelated-cover-user")
    scanner = _seed_user(db_session, "scanner-cover-user")
    event = _seed_event(db_session, owner)
    db_session.add(EventStaff(event_id=event.id, user_id=scanner.id, role=EventStaffRole.CHECKIN, is_active=True, invited_by_user_id=owner.id))
    db_session.flush()
    s3 = FakeS3Client()
    _configure_s3(monkeypatch, s3)

    assert _upload(client, event, other).status_code == 403
    assert _upload(client, event, scanner).status_code == 403
    assert s3.puts == []


def test_unauthenticated_cover_upload_is_rejected(client: TestClient, db_session: Session) -> None:
    owner = _seed_user(db_session, "unauth-cover-owner")
    event = _seed_event(db_session, owner)
    response = client.post(
        f"/events/{event.id}/cover-image",
        files={"file": ("cover.png", _image_bytes(), "image/png")},
    )
    assert response.status_code == 401


def test_cover_upload_rejects_oversized_unsupported_malformed_and_mismatched_files(
    client: TestClient, db_session: Session
) -> None:
    owner = _seed_user(db_session, "invalid-cover-owner")
    event = _seed_event(db_session, owner)

    oversized = _upload(client, event, owner, data=b"x" * (events_api.MAX_EVENT_COVER_IMAGE_BYTES + 1))
    unsupported = _upload(client, event, owner, data=b"plain", mime="text/plain")
    malformed = _upload(client, event, owner, data=b"not-an-image")
    mismatch = _upload(client, event, owner, data=_image_bytes("JPEG"), mime="image/png")

    assert oversized.status_code == 413
    assert unsupported.status_code == 400
    assert malformed.status_code == 400
    assert mismatch.status_code == 400


def test_cover_upload_reencodes_and_strips_image_metadata(client: TestClient, db_session: Session, monkeypatch) -> None:  # noqa: ANN001
    owner = _seed_user(db_session, "metadata-cover-owner")
    event = _seed_event(db_session, owner)
    s3 = FakeS3Client()
    _configure_s3(monkeypatch, s3)
    source = Image.new("RGB", (40, 30), color=(100, 20, 30))
    exif = Image.Exif()
    exif[0x010E] = "private test metadata"
    payload = BytesIO()
    source.save(payload, format="JPEG", exif=exif)

    response = _upload(client, event, owner, data=payload.getvalue(), mime="image/jpeg")

    assert response.status_code == 201
    with Image.open(BytesIO(s3.puts[0]["Body"])) as normalized:
        assert normalized.format == "JPEG"
        assert len(normalized.getexif()) == 0


def test_cover_upload_rejects_excessive_dimensions(client: TestClient, db_session: Session, monkeypatch) -> None:  # noqa: ANN001
    owner = _seed_user(db_session, "dimension-cover-owner")
    event = _seed_event(db_session, owner)
    monkeypatch.setattr(events_api, "MAX_EVENT_COVER_IMAGE_PIXELS", 100)

    response = _upload(client, event, owner, data=_image_bytes(size=(20, 20)))

    assert response.status_code == 400
    assert response.json()["detail"] == "Cover image dimensions are too large."


def test_cover_upload_is_rate_limited(client: TestClient, db_session: Session, monkeypatch) -> None:  # noqa: ANN001
    owner = _seed_user(db_session, "limited-cover-owner")
    event = _seed_event(db_session, owner)
    _configure_s3(monkeypatch, FakeS3Client())
    monkeypatch.setattr(settings, "rate_limit_event_cover_upload_count", 1)

    assert _upload(client, event, owner).status_code == 201
    limited = _upload(client, event, owner)

    assert limited.status_code == 429
    assert "Retry-After" in limited.headers


def test_failed_storage_update_preserves_active_cover(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    owner = _seed_user(db_session, "failed-cover-owner")
    original_url = "https://images.test.local/event-covers/original.png"
    event = _seed_event(db_session, owner, cover_image_url=original_url)

    _configure_s3(monkeypatch, FakeS3Client(fail=True))
    storage_failure = _upload(client, event, owner)
    assert storage_failure.status_code == 502
    db_session.refresh(event)
    assert event.cover_image_url == original_url
    failed_audit = db_session.query(AdminActionAudit).filter_by(action_type="event_cover_upload_failed").one()
    assert failed_audit.metadata_json["status"] == "failed"


def test_concurrent_cover_change_is_not_overwritten_and_new_object_is_tracked_for_cleanup(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    owner = _seed_user(db_session, "concurrent-cover-owner")
    original_url = "https://images.test.local/event-covers/original.png"
    concurrent_url = "https://images.test.local/event-covers/concurrent.png"
    event = _seed_event(db_session, owner, cover_image_url=original_url)

    def change_cover() -> None:
        event.cover_image_url = concurrent_url
        db_session.commit()

    _configure_s3(monkeypatch, FakeS3Client(on_put=change_cover))
    response = _upload(client, event, owner)

    assert response.status_code == 409
    db_session.refresh(event)
    assert event.cover_image_url == concurrent_url
    audit = db_session.query(AdminActionAudit).filter_by(action_type="event_cover_upload_orphaned").one()
    assert audit.metadata_json["status"] == "cleanup_required"


def test_cover_changes_do_not_change_general_event_edit_permissions(
    client: TestClient, db_session: Session
) -> None:
    owner = _seed_user(db_session, "ordinary-edit-owner")
    event = _seed_event(db_session, owner, cover_image_url="https://images.test.local/event-covers/current.png")

    response = client.patch(
        f"/events/organizer/events/{event.id}",
        headers=auth_headers(owner),
        json={"title": "Still editable"},
    )

    assert response.status_code == 200
    db_session.refresh(event)
    assert event.title == "Still editable"
    assert event.cover_image_url == "https://images.test.local/event-covers/current.png"


def test_direct_cover_url_changes_are_rejected(client: TestClient, db_session: Session) -> None:
    owner = _seed_user(db_session, "direct-cover-owner")
    event = _seed_event(db_session, owner)

    response = client.patch(
        f"/events/organizer/events/{event.id}",
        headers=auth_headers(owner),
        json={"cover_image_url": "https://untrusted.example/cover.png"},
    )

    assert response.status_code == 422


def test_owner_can_remove_cover_without_deleting_s3_object(client: TestClient, db_session: Session, monkeypatch) -> None:  # noqa: ANN001
    owner = _seed_user(db_session, "remove-cover-owner")
    event = _seed_event(db_session, owner, cover_image_url="https://images.test.local/event-covers/current.png")
    monkeypatch.setattr(settings, "s3_public_base_url", "https://images.test.local")

    response = client.delete(f"/events/{event.id}/cover-image", headers=auth_headers(owner))

    assert response.status_code == 204
    db_session.refresh(event)
    assert event.cover_image_url is None
    audit = db_session.query(AdminActionAudit).filter_by(action_type="event_cover_removed").one()
    assert audit.metadata_json["previous_object_key"] == "event-covers/current.png"
