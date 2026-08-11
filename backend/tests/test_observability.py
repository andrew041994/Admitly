from fastapi.testclient import TestClient

from app.main import app
from app.core import observability


client = TestClient(app)


def test_request_id_is_returned_and_valid_caller_id_is_preserved() -> None:
    response = client.get("/health", headers={"X-Request-ID": "support-case_123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "support-case_123"


def test_invalid_request_id_is_replaced() -> None:
    response = client.get("/health", headers={"X-Request-ID": "invalid id with spaces"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "invalid id with spaces"
    assert len(response.headers["X-Request-ID"]) == 32


def test_sentry_receives_environment_and_resolved_release(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(observability.settings, "sentry_dsn", "https://public@example.invalid/1")
    monkeypatch.setattr(observability.settings, "env", "production")
    monkeypatch.setattr(observability.settings, "sentry_release", "release-123")
    monkeypatch.setattr(observability.sentry_sdk, "init", lambda **kwargs: captured.update(kwargs))

    observability.configure_sentry()

    assert captured["environment"] == "production"
    assert captured["release"] == "release-123"
    assert captured["send_default_pii"] is False


def test_sentry_is_not_initialized_without_dsn(monkeypatch, caplog) -> None:
    initialized = []
    monkeypatch.setattr(observability.settings, "sentry_dsn", None)
    monkeypatch.setattr(observability.settings, "env", "production")
    monkeypatch.setattr(observability.sentry_sdk, "init", lambda **kwargs: initialized.append(kwargs))

    observability.configure_sentry()

    assert initialized == []
    assert "production error reporting is disabled" in caplog.text
