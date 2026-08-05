from __future__ import annotations

import logging
import math
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload

from app.models.enums import EventApprovalStatus, EventStatus, EventVisibility
from app.models.event import Event
from app.models.push_dispatch import NotificationJob
from app.models.user import User
from app.models.user_notification import NotificationPreference
from app.services.notification_center import create_user_notification, utc_now

logger = logging.getLogger(__name__)
NEARBY_RADIUS_KM = 20.0
FANOUT_BATCH_SIZE = 500
MAX_JOB_ATTEMPTS = 5


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_event_discoverable(event: Event, *, now=None) -> bool:
    reference_now = now or utc_now()
    return bool(
        event.status == EventStatus.PUBLISHED
        and event.visibility == EventVisibility.PUBLIC
        and event.approval_status == EventApprovalStatus.APPROVED
        and event.published_at is not None
        and event.cancelled_at is None
        and event.start_at > reference_now
        and event.latitude is not None
        and event.longitude is not None
    )


def enqueue_nearby_event_job(db: Session, *, event_id: int) -> bool:
    dedupe_key = f"nearby-event:{event_id}:first-publication"
    if db.execute(select(NotificationJob.id).where(NotificationJob.dedupe_key == dedupe_key)).scalar_one_or_none():
        return False
    inserted = db.execute(
        pg_insert(NotificationJob)
        .values(
            job_type="nearby_event",
            dedupe_key=dedupe_key,
            related_entity_id=event_id,
            status="pending",
            run_at=utc_now(),
        )
        .on_conflict_do_nothing(index_elements=[NotificationJob.dedupe_key])
        .returning(NotificationJob.id)
    ).scalar_one_or_none()
    return inserted is not None


def enqueue_nearby_event_after_commit(db: Session, *, event_id: int) -> None:
    try:
        event = db.execute(select(Event).where(Event.id == event_id)).scalar_one_or_none()
        if event is None or not is_event_discoverable(event):
            return
        if enqueue_nearby_event_job(db, event_id=event_id):
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("nearby_event_job_enqueue_failed", extra={"event_id": event_id})


def _process_nearby_job(db: Session, job: NotificationJob) -> int:
    event = db.execute(
        select(Event).options(joinedload(Event.organizer)).where(Event.id == job.related_entity_id)
    ).scalar_one_or_none()
    if event is None or not is_event_discoverable(event):
        job.status = "completed"
        return 0

    event_lat = float(event.latitude)
    event_lon = float(event.longitude)
    # A latitude/longitude box is only a prefilter; Haversine below is authoritative.
    lat_delta = NEARBY_RADIUS_KM / 111.32
    lon_scale = max(0.01, math.cos(math.radians(event_lat)))
    lon_delta = NEARBY_RADIUS_KM / (111.32 * lon_scale)
    rows = db.execute(
        select(User, NotificationPreference)
        .join(NotificationPreference, NotificationPreference.user_id == User.id)
        .where(
            User.id > job.next_cursor_id,
            User.is_active.is_(True),
            User.id != event.organizer.user_id,
            NotificationPreference.nearby_events_push_enabled.is_(True),
            NotificationPreference.location_discovery_enabled.is_(True),
            NotificationPreference.latitude.is_not(None),
            NotificationPreference.longitude.is_not(None),
            NotificationPreference.latitude.between(event_lat - lat_delta, event_lat + lat_delta),
            NotificationPreference.longitude.between(event_lon - lon_delta, event_lon + lon_delta),
        )
        .order_by(User.id.asc())
        .limit(FANOUT_BATCH_SIZE)
    ).all()

    created = 0
    for user, preference in rows:
        job.next_cursor_id = user.id
        distance = haversine_km(float(preference.latitude), float(preference.longitude), event_lat, event_lon)
        if distance <= NEARBY_RADIUS_KM:
            _, was_created = create_user_notification(
                db,
                user_id=user.id,
                notification_type="nearby_event_created",
                title="New event near you",
                body=f"{event.title} is happening nearby.",
                dedupe_key=f"nearby-event:{event.id}:user:{user.id}",
                route_key="event",
                route_params={"event_id": event.id},
                related_entity_type="event",
                related_entity_id=event.id,
            )
            created += int(was_created)
    if len(rows) < FANOUT_BATCH_SIZE:
        job.status = "completed"
    else:
        job.status = "pending"
        job.run_at = utc_now()
    job.claimed_at = None
    return created


def process_notification_jobs(db: Session, *, limit: int = 10) -> dict[str, int]:
    now = utc_now()
    stale_before = now - timedelta(minutes=10)
    jobs = db.execute(
        select(NotificationJob)
        .where(
            NotificationJob.run_at <= now,
            or_(
                NotificationJob.status == "pending",
                (NotificationJob.status == "processing") & (NotificationJob.claimed_at < stale_before),
            ),
        )
        .order_by(NotificationJob.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
    ).scalars().all()
    for job in jobs:
        job.status = "processing"
        job.claimed_at = now
        job.attempts += 1
    db.commit()

    summary = {"claimed": len(jobs), "completed": 0, "notifications_created": 0, "failed": 0}
    for job in jobs:
        try:
            if job.job_type == "nearby_event":
                summary["notifications_created"] += _process_nearby_job(db, job)
            else:
                job.status = "failed"
                job.error_code = "unknown_job_type"
            db.commit()
            if job.status == "completed":
                summary["completed"] += 1
        except Exception:
            db.rollback()
            current = db.get(NotificationJob, job.id)
            if current is not None:
                current.status = "failed" if current.attempts >= MAX_JOB_ATTEMPTS else "pending"
                current.error_code = "processing_error"
                current.claimed_at = None
                current.run_at = utc_now() + timedelta(minutes=min(30, 2 ** current.attempts))
                db.commit()
            logger.exception("notification_job_failed", extra={"job_id": job.id})
            summary["failed"] += 1
    return summary
