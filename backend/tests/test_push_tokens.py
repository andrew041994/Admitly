from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.notifications import delete_my_push_token, register_my_push_token
from app.db.base import Base
from app.models import User
from app.schemas.notification import PushTokenDeleteRequest, PushTokenRegisterRequest
from app.services.notifications import PushMessage, _send_push, register_push_token
from tests.utils import unique_email



def _seed_user(db: Session, suffix: str) -> User:
    user = User(email=unique_email(f"push_{suffix}"), full_name="Push User")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_push_token_registration_reregistration_and_delete(db_session: Session) -> None:
    user = _seed_user(db_session, "reg")

    first = register_my_push_token(
        PushTokenRegisterRequest(token="tok-1", platform="ios"),
        db=db_session,
        user_id=user.id,
    )
    assert first.is_active is True

    second = register_my_push_token(
        PushTokenRegisterRequest(token="tok-1", platform="android"),
        db=db_session,
        user_id=user.id,
    )
    assert second.platform == "android"

    deleted = delete_my_push_token(PushTokenDeleteRequest(token="tok-1"), db=db_session, user_id=user.id)
    assert deleted.success is True


def test_push_sender_fans_out_active_tokens(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user = _seed_user(db_session, "fanout")
    register_push_token(db_session, user_id=user.id, token="tok-a", platform="ios")
    register_push_token(db_session, user_id=user.id, token="tok-b", platform="android")

    monkeypatch.setattr("app.services.notifications.settings.push_notifications_enabled", True)
    monkeypatch.setattr("app.services.notifications.settings.push_provider", "mock")

    result = _send_push(db_session, PushMessage(user_id=user.id, title="Hello", body="World", data={"type": "test"}))
    assert result == "sent_mock:2"


def test_push_sender_skips_when_disabled(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user = _seed_user(db_session, "disabled")
    register_push_token(db_session, user_id=user.id, token="tok-c", platform="ios")

    monkeypatch.setattr("app.services.notifications.settings.push_notifications_enabled", False)

    result = _send_push(db_session, PushMessage(user_id=user.id, title="Hello", body="World", data={"type": "test"}))
    assert result == "skipped_disabled"
