from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.db.session import get_db

DATABASE_URL = "postgresql://neondb_owner:npg_jKSZablLD72J@ep-still-paper-anfodm11-pooler.c-6.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

os.environ["DATABASE_URL"] = DATABASE_URL

engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, future=True)


@pytest.fixture(scope="session", autouse=True)
def apply_test_migrations() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    subprocess.run(["alembic", "upgrade", "head"], cwd=backend_dir, check=True)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    connection: Connection = engine.connect()
    outer_transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess: Session, transaction) -> None:  # noqa: ANN001
        parent = getattr(transaction, "_parent", None)
        if transaction.nested and parent is not None and not parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        event.remove(session, "after_transaction_end", _restart_savepoint)
        session.close()
        if outer_transaction.is_active:
            outer_transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def override_fastapi_db_dependency(db_session: Session) -> Generator[None, None, None]:
    def _get_db_override() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
