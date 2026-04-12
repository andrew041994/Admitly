import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.orders import complete_dev_test_checkout
from app.core.config import settings
from app.main import app


def test_dev_test_checkout_route_registered() -> None:
    route_paths = {route.path for route in app.routes}

    assert "/orders/{order_id}/payments/dev-test/complete" in route_paths


def test_dev_test_checkout_route_is_post_and_defaults_to_http_200() -> None:
    target_route = next(route for route in app.routes if route.path == "/orders/{order_id}/payments/dev-test/complete")

    assert "POST" in target_route.methods
    assert target_route.status_code is None


def test_dev_test_checkout_handler_returns_payload_when_enabled(monkeypatch) -> None:
    previous_enabled = settings.enable_dev_test_checkout
    previous_env = settings.env

    settings.enable_dev_test_checkout = True
    settings.env = "development"

    def _fake_complete_checkout(db, *, order_id: int, user_id: int):
        assert order_id == 77
        assert user_id == 123
        return SimpleNamespace(
            order_id=order_id,
            order_reference="ORD-77",
            provider="dev_test",
            payment_method="dev_test",
            payment_reference="pay-ref-77",
            status="completed",
            payment_verification_status="verified",
            message="Dev test checkout completed.",
        )

    monkeypatch.setattr("app.api.orders.apply_rate_limit", lambda **_: None)
    monkeypatch.setattr("app.api.orders.complete_dev_test_checkout_for_order", _fake_complete_checkout)

    try:
        response = complete_dev_test_checkout(
            order_id=77,
            db=object(),
            current_user=SimpleNamespace(id=123),
            client_ip="127.0.0.1",
        )
    finally:
        settings.enable_dev_test_checkout = previous_enabled
        settings.env = previous_env

    assert response.order_id == 77
    assert response.provider == "dev_test"
    assert response.payment_reference == "pay-ref-77"


def test_dev_test_checkout_handler_commits_after_success(monkeypatch) -> None:
    previous_enabled = settings.enable_dev_test_checkout
    previous_env = settings.env

    settings.enable_dev_test_checkout = True
    settings.env = "development"

    class _FakeDb:
        def __init__(self) -> None:
            self.commit_calls = 0

        def commit(self) -> None:
            self.commit_calls += 1

    def _fake_complete_checkout(db, *, order_id: int, user_id: int):
        assert order_id == 88
        assert user_id == 456
        return SimpleNamespace(
            order_id=order_id,
            order_reference="ORD-88",
            provider="dev_test",
            payment_method="dev_test",
            payment_reference="pay-ref-88",
            status="completed",
            payment_verification_status="verified",
            message="Dev test checkout completed.",
        )

    monkeypatch.setattr("app.api.orders.apply_rate_limit", lambda **_: None)
    monkeypatch.setattr("app.api.orders.complete_dev_test_checkout_for_order", _fake_complete_checkout)
    db = _FakeDb()

    try:
        complete_dev_test_checkout(
            order_id=88,
            db=db,
            current_user=SimpleNamespace(id=456),
            client_ip="127.0.0.1",
        )
    finally:
        settings.enable_dev_test_checkout = previous_enabled
        settings.env = previous_env

    assert db.commit_calls == 1


def test_dev_test_checkout_handler_returns_403_when_disabled(monkeypatch) -> None:
    previous_enabled = settings.enable_dev_test_checkout
    settings.enable_dev_test_checkout = False
    monkeypatch.setattr("app.api.orders.apply_rate_limit", lambda **_: None)

    try:
        with pytest.raises(HTTPException) as exc:
            complete_dev_test_checkout(
                order_id=77,
                db=object(),
                current_user=SimpleNamespace(id=123),
                client_ip="127.0.0.1",
            )
    finally:
        settings.enable_dev_test_checkout = previous_enabled

    assert exc.value.status_code == 403
    assert exc.value.detail == "Dev test checkout is disabled."
