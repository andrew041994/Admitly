from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.main import app

DATABASE_URL = "postgresql://neondb_owner:npg_jKSZablLD72J@ep-still-paper-anfodm11-pooler.c-6.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

os.environ["DATABASE_URL"] = DATABASE_URL

# Create engine once for the test process.
engine = create_engine(DATABASE_URL)


@pytest.fixture(scope="session", autouse=True)
def apply_test_migrations() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    subprocess.run(["alembic", "upgrade", "head"], cwd=backend_dir, check=True)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    connection: Connection = engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess: Session, trans) -> None:  # noqa: ANN001
        parent = getattr(trans, "_parent", None)
        if trans.nested and parent is not None and not parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        event.remove(session, "after_transaction_end", restart_savepoint)
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def override_fastapi_db_dependency(db_session: Session) -> Generator[None, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
