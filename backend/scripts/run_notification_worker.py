"""Run Admitly's database-backed notification worker.

The default mode polls continuously. ``--once`` is retained for local diagnostics.
Multiple instances are supported by the database claims and uniqueness constraints
in the notification services.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import signal
import sys
from threading import Event

from sqlalchemy.exc import SQLAlchemyError

# ``python scripts/run_notification_worker.py`` places ``backend/scripts`` rather
# than ``backend`` on sys.path. Add the service root so the documented Render
# command works without relying on an implicit PYTHONPATH.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_POLL_INTERVAL_SECONDS = 60
MIN_POLL_INTERVAL_SECONDS = 15
DEFAULT_MAX_CONSECUTIVE_DB_FAILURES = 5
SUPPORTED_PUSH_PROVIDERS = {"noop", "mock", "expo"}
REQUIRED_NOTIFICATION_TABLES = (
    "event_reschedules",
    "event_reminder_logs",
    "notification_jobs",
    "push_dispatches",
    "user_notifications",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("admitly.notification_worker")


def validate_startup() -> None:
    """Validate configuration, connectivity, and the required local schema."""
    from sqlalchemy import text

    from app.core.config import settings
    from app.db.session import engine

    configured_provider = settings.push_provider.strip()
    provider = configured_provider.lower()
    if provider not in SUPPORTED_PUSH_PROVIDERS:
        raise ValueError(
            "PUSH_PROVIDER must be one of: expo, mock, noop."
        )
    if configured_provider != provider:
        raise ValueError("PUSH_PROVIDER must use a lowercase value.")
    if settings.push_notifications_enabled and provider == "noop":
        raise ValueError(
            "PUSH_NOTIFICATIONS_ENABLED=true requires PUSH_PROVIDER=expo or mock."
        )

    # These read-only checks fail clearly if DATABASE_URL is unreachable or the
    # notification migration has not been applied. They never run migrations.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        for table_name in REQUIRED_NOTIFICATION_TABLES:
            connection.execute(text(f"SELECT 1 FROM {table_name} LIMIT 0"))

    logger.info(
        "notification_worker_startup_validated env=%s push_enabled=%s push_provider=%s",
        settings.env,
        settings.push_notifications_enabled,
        provider,
    )


def run_once() -> None:
    """Process one bounded cycle and release its database session."""
    from app.db.session import SessionLocal
    from app.services.nearby_notifications import process_notification_jobs
    from app.services.push_delivery import process_expo_receipts, process_push_dispatches
    from app.services.reminders import dispatch_due_event_reminders

    with SessionLocal() as db:
        reminders = dispatch_due_event_reminders(db)
        db.commit()
        jobs = process_notification_jobs(db)
        pushes = process_push_dispatches(db)
        receipts = process_expo_receipts(db)

    logger.info(
        "notification_worker_cycle_complete reminders_sent=%d "
        "jobs_claimed=%d jobs_completed=%d jobs_failed=%d "
        "pushes_claimed=%d pushes_sent=%d pushes_failed=%d "
        "receipts_checked=%d receipts_delivered=%d receipts_failed=%d",
        reminders.reminders_sent,
        jobs["claimed"],
        jobs["completed"],
        jobs["failed"],
        pushes["claimed"],
        pushes["sent"],
        pushes["failed"],
        receipts["checked"],
        receipts["delivered"],
        receipts["failed"],
    )


def run_forever(
    *,
    interval_seconds: int,
    max_consecutive_db_failures: int,
    stop_event: Event,
) -> None:
    """Poll until stopped, retrying transient database failures with a ceiling."""
    consecutive_db_failures = 0
    logger.info(
        "notification_worker_polling_started interval_seconds=%d",
        interval_seconds,
    )

    while not stop_event.is_set():
        try:
            run_once()
            consecutive_db_failures = 0
        except SQLAlchemyError:
            consecutive_db_failures += 1
            logger.exception(
                "notification_worker_transient_database_error "
                "consecutive_failures=%d max_consecutive_failures=%d",
                consecutive_db_failures,
                max_consecutive_db_failures,
            )
            if consecutive_db_failures >= max_consecutive_db_failures:
                raise
        except Exception:
            # Programming errors and other unexpected failures should terminate
            # non-zero so Render's process supervisor can restart the worker.
            logger.exception("notification_worker_unexpected_cycle_failure")
            raise

        if not stop_event.is_set():
            # Event.wait makes the idle poll interruptible and avoids busy-looping.
            stop_event.wait(interval_seconds)

    logger.info("notification_worker_polling_stopped")


def _install_signal_handlers(stop_event: Event) -> None:
    def request_shutdown(signum: int, _frame: object) -> None:
        signal_name = signal.Signals(signum).name
        logger.info("notification_worker_shutdown_requested signal=%s", signal_name)
        stop_event.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)


def _dispose_database_pool() -> None:
    try:
        from app.db.session import engine
    except Exception:
        return
    engine.dispose()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process one cycle and exit.")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"Seconds between cycles (minimum {MIN_POLL_INTERVAL_SECONDS}).",
    )
    parser.add_argument(
        "--max-consecutive-db-failures",
        type=int,
        default=DEFAULT_MAX_CONSECUTIVE_DB_FAILURES,
        help="Exit non-zero after this many consecutive database cycle failures.",
    )
    args = parser.parse_args(argv)
    if args.max_consecutive_db_failures < 1:
        parser.error("--max-consecutive-db-failures must be at least 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    stop_event = Event()
    exit_code = 0
    logger.info("notification_worker_starting mode=%s", "once" if args.once else "continuous")

    try:
        validate_startup()
        if args.once:
            run_once()
        else:
            _install_signal_handlers(stop_event)
            run_forever(
                interval_seconds=max(MIN_POLL_INTERVAL_SECONDS, args.interval),
                max_consecutive_db_failures=args.max_consecutive_db_failures,
                stop_event=stop_event,
            )
    except Exception:
        exit_code = 1
        logger.exception("notification_worker_fatal_error")
    finally:
        _dispose_database_pool()
        logger.info("notification_worker_exiting exit_code=%d", exit_code)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
