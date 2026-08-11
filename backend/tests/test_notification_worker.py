from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread

import pytest
from sqlalchemy.exc import OperationalError

from scripts import run_notification_worker as worker


def test_continuous_worker_remains_alive_while_idle_and_stops_cleanly(monkeypatch) -> None:
    stop_event = Event()
    cycle_ran = Event()

    def idle_cycle() -> None:
        cycle_ran.set()

    monkeypatch.setattr(worker, "run_once", idle_cycle)
    thread = Thread(
        target=worker.run_forever,
        kwargs={
            "interval_seconds": 60,
            "max_consecutive_db_failures": 5,
            "stop_event": stop_event,
        },
    )
    thread.start()

    assert cycle_ran.wait(timeout=2)
    assert thread.is_alive()
    stop_event.set()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_transient_database_failure_is_retried(monkeypatch) -> None:
    stop_event = Event()
    attempts = 0

    def transient_then_success() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError("SELECT 1", {}, RuntimeError("database unavailable"))
        stop_event.set()

    monkeypatch.setattr(worker, "run_once", transient_then_success)
    worker.run_forever(
        interval_seconds=0,
        max_consecutive_db_failures=3,
        stop_event=stop_event,
    )
    assert attempts == 2


def test_repeated_database_failure_becomes_fatal(monkeypatch) -> None:
    def unavailable() -> None:
        raise OperationalError("SELECT 1", {}, RuntimeError("database unavailable"))

    monkeypatch.setattr(worker, "run_once", unavailable)
    with pytest.raises(OperationalError):
        worker.run_forever(
            interval_seconds=0,
            max_consecutive_db_failures=2,
            stop_event=Event(),
        )


def test_unexpected_cycle_failure_is_immediately_fatal(monkeypatch) -> None:
    monkeypatch.setattr(
        worker,
        "run_once",
        lambda: (_ for _ in ()).throw(RuntimeError("unexpected")),
    )
    with pytest.raises(RuntimeError, match="unexpected"):
        worker.run_forever(
            interval_seconds=0,
            max_consecutive_db_failures=5,
            stop_event=Event(),
        )


def test_exact_worker_command_fails_clearly_without_database_url(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    script = Path(worker.__file__).resolve()
    result = subprocess.run(
        [sys.executable, str(script), "--once"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    assert "notification_worker_fatal_error" in result.stderr
    assert "DATABASE_URL" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
