"""Run Admitly's database-backed notification work once or continuously.

The worker is safe to run on multiple instances because claims use row locks and all
user-facing notifications have database uniqueness keys.
"""

from __future__ import annotations

import argparse
import logging
import time

from app.db.session import SessionLocal
from app.services.nearby_notifications import process_notification_jobs
from app.services.push_delivery import process_expo_receipts, process_push_dispatches
from app.services.reminders import dispatch_due_event_reminders

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("admitly.notification_worker")


def run_once() -> None:
    with SessionLocal() as db:
        reminders = dispatch_due_event_reminders(db)
        db.commit()
        jobs = process_notification_jobs(db)
        pushes = process_push_dispatches(db)
        receipts = process_expo_receipts(db)
    logger.info(
        "notification_worker_cycle_complete",
        extra={
            "reminders_sent": reminders.reminders_sent,
            "jobs_claimed": jobs["claimed"],
            "pushes_claimed": pushes["claimed"],
            "receipts_checked": receipts["checked"],
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process one cycle and exit.")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between cycles.")
    args = parser.parse_args()
    if args.once:
        run_once()
        return
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("notification_worker_cycle_failed")
        time.sleep(max(15, args.interval))


if __name__ == "__main__":
    main()
