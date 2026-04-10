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



engine = create_engine(DATABASE_URL)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False)


@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()

    session = TestingSessionLocal(bind=connection)

    # Start SAVEPOINT
    session.begin_nested()

    # Restart SAVEPOINT after each commit
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    # Override FastAPI dependency
    def override_get_db():
        try:
            yield session
        finally:
            pass

    # Apply override if using FastAPI
    try:
        from app.main import app
        app.dependency_overrides[get_db] = override_get_db
    except Exception:
        pass

    yield session

    # CLEANUP (CRITICAL ORDER)
    session.close()
    transaction.rollback()
    connection.close()