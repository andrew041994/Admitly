from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.cors import install_cors


def _client(*, environment: str) -> TestClient:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://database.example/admitly",
        ENV=environment,
        JWT_SECRET="a-production-secret-that-is-longer-than-32-characters",
        REDIS_URL="rediss://redis.example:6380/0",
        ENABLE_DEV_TEST_CHECKOUT=False,
    )
    app = FastAPI()
    install_cors(app, settings)

    @app.get("/probe")
    def probe() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/probe",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )


def test_production_admitly_origin_is_allowed() -> None:
    response = _preflight(_client(environment="production"), "https://www.admitlyevents.com")
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://www.admitlyevents.com"


def test_localhost_is_rejected_in_production() -> None:
    response = _preflight(_client(environment="production"), "http://localhost:5173")
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_unknown_origin_is_rejected_in_production() -> None:
    response = _preflight(_client(environment="production"), "https://unexpected.example")
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_localhost_is_allowed_in_development() -> None:
    response = _preflight(_client(environment="development"), "http://localhost:5173")
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_non_browser_request_does_not_require_an_origin() -> None:
    response = _client(environment="production").get("/probe")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "access-control-allow-origin" not in response.headers
