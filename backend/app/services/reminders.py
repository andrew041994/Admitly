from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import logging

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import EventStatus, ReminderType, TicketStatus
from app.models.event import Event
from app.models.event_reminder_log import EventReminderLog
from app.models.ticket import Ticket
from app.models.user import User
from app.services.notifications import notify_event_reminder
from app.services.ticket_holds import get_guyana_now

logger = logging.getLogger(__name__)

POLL_WINDOW = timedelta(minutes=10)
REMINDER_OFFSETS: dict[ReminderType, timedelta] = {
    ReminderType.HOURS_24_BEFORE: timedelta(hours=24),
    ReminderType.MINUTES_30_BEFORE: timedelta(minutes=30),
}
EVENT_DAY_REMINDER_LOCAL_TIME = time(hour=9)


@dataclass(slots=True)
class ReminderDispatchSummary:
    events_considered: int = 0
    reminders_sent: int = 0
    reminders_skipped: int = 0
    sent_per_type: dict[ReminderType, int] = field(default_factory=dict)


def _to_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _event_timezone(event: Event) -> ZoneInfo:
    return ZoneInfo(event.timezone or "America/Guyana")


def get_reminder_due_times_for_event(event: Event) -> dict[ReminderType, datetime]:
    event_start = _to_aware(event.start_at)
    today_due_local = datetime.combine(
        event_start.astimezone(_event_timezone(event)).date(),
        EVENT_DAY_REMINDER_LOCAL_TIME,
        tzinfo=_event_timezone(event),
    )
    today_due = today_due_local.astimezone(timezone.utc)
    if today_due >= event_start:
        today_due = event_start - timedelta(hours=3)

    return {
        ReminderType.HOURS_24_BEFORE: event_start - timedelta(hours=24),
        ReminderType.HOURS_3_BEFORE: today_due,
        ReminderType.MINUTES_30_BEFORE: event_start - timedelta(minutes=30),
    }


def get_reminder_windows(now: datetime | None = None) -> dict[ReminderType, tuple[datetime, datetime]]:
    reference_now = _to_aware(now) if now is not None else get_guyana_now()
    windows: dict[ReminderType, tuple[datetime, datetime]] = {}
    for reminder_type in (ReminderType.HOURS_24_BEFORE, ReminderType.HOURS_3_BEFORE, ReminderType.MINUTES_30_BEFORE):
        windows[reminder_type] = (reference_now, reference_now + POLL_WINDOW)
    return windows


def should_send_reminder_for_event(
    event: Event,
    reminder_type: ReminderType,
    now: datetime | None = None,
) -> bool:
    if event.status == EventStatus.CANCELLED:
        return False
    reference_now = _to_aware(now) if now is not None else get_guyana_now()
    event_start = _to_aware(event.start_at)
    if event_start <= reference_now:
        return False

    window_start, window_end = get_reminder_windows(reference_now)[reminder_type]
    due_at = get_reminder_due_times_for_event(event)[reminder_type]
    return window_start <= due_at < window_end


def _due_events_query(reminder_type: ReminderType, now: datetime) -> Select[tuple[Event]]:
    window_start, window_end = get_reminder_windows(now)[reminder_type]
    if reminder_type == ReminderType.HOURS_24_BEFORE:
        earliest_start = window_start + timedelta(hours=24)
        latest_start = window_end + timedelta(hours=24)
    elif reminder_type == ReminderType.MINUTES_30_BEFORE:
        earliest_start = window_start + timedelta(minutes=30)
        latest_start = window_end + timedelta(minutes=30)
    else:
        earliest_start = window_start
        latest_start = window_end + timedelta(days=1)
    return (
        select(Event)
        .where(
            Event.status != EventStatus.CANCELLED,
            Event.start_at > now,
            Event.start_at >= earliest_start,
            Event.start_at < latest_start,
        )
        .order_by(Event.id.asc())
    )


def get_eligible_event_reminder_recipients(
    db: Session,
    *,
    event_id: int,
    reminder_type: ReminderType,
    now: datetime | None = None,
) -> list[tuple[User, int]]:
    reference_now = _to_aware(now) if now is not None else get_guyana_now()

    event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
    if event is None or not should_send_reminder_for_event(event, reminder_type, now=reference_now):
        return []

    rows = (
        db.execute(
            select(User, func.count(Ticket.id))
            .join(Ticket, Ticket.owner_user_id == User.id)
            .where(
                Ticket.event_id == event_id,
                Ticket.status == TicketStatus.ISSUED,
            )
            .group_by(User.id)
            .order_by(User.id.asc())
        )
        .all()
    )
    return [(user, int(ticket_count)) for user, ticket_count in rows]


def dispatch_due_event_reminders(
    db: Session,
    now: datetime | None = None,
) -> ReminderDispatchSummary:
    reference_now = _to_aware(now) if now is not None else get_guyana_now()
    summary = ReminderDispatchSummary(
        sent_per_type={
            ReminderType.HOURS_24_BEFORE: 0,
            ReminderType.HOURS_3_BEFORE: 0,
            ReminderType.MINUTES_30_BEFORE: 0,
        }
    )

    for reminder_type in REMINDER_OFFSETS:
        events = db.execute(_due_events_query(reminder_type, reference_now)).scalars().all()
        summary.events_considered += len(events)
        for event in events:
            recipients = get_eligible_event_reminder_recipients(
                db,
                event_id=event.id,
                reminder_type=reminder_type,
                now=reference_now,
            )
            for user, ticket_count in recipients:
                existing = db.execute(
                    select(EventReminderLog.id).where(
                        EventReminderLog.event_id == event.id,
                        EventReminderLog.user_id == user.id,
                        EventReminderLog.reminder_type == reminder_type,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    summary.reminders_skipped += 1
                    continue

                result = notify_event_reminder(
                    db,
                    event=event,
                    user=user,
                    reminder_type=reminder_type,
                    ticket_count=ticket_count,
                )
                if not result.success:
                    logger.warning(
                        "Reminder dispatch failed",
                        extra={"event_id": event.id, "user_id": user.id, "reminder_type": reminder_type.value},
                    )
                    summary.reminders_skipped += 1
                    continue
                

                log = EventReminderLog(
                    event_id=event.id,
                    user_id=user.id,
                    reminder_type=reminder_type,
                    sent_at=reference_now,
                )
                try:
                    db.add(log)
                    db.flush()
                except IntegrityError:
                    logger.info(
                        "Duplicate reminder log detected",
                        extra={"event_id": event.id, "user_id": user.id, "reminder_type": reminder_type.value},
                    )
                    summary.reminders_skipped += 1
                    continue

                summary.reminders_sent += 1
                summary.sent_per_type[reminder_type] += 1

    return summary


def run_event_reminder_dispatch_job(db: Session, now: datetime | None = None) -> ReminderDispatchSummary:
    return dispatch_due_event_reminders(db, now=now)
