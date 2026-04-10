from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.db.session import get_db

DATABASE_URL = "postgresql://neondb_owner:npg_jKSZablLD72J@ep-still-paper-anfodm11-pooler.c-6.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

os.environ["DATABASE_URL"] = DATABASE_URL

engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@pytest.fixture(scope="session", autouse=True)
def apply_test_migrations() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    subprocess.run(["alembic", "upgrade", "head"], cwd=backend_dir, check=True)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def override_fastapi_db_dependency(db_session: Session) -> Generator[None, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
