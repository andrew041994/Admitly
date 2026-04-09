from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.event import Event
from app.models.enums import EventStatus
from app.models.organizer_profile import OrganizerProfile
from app.models.user import User
from pydantic import BaseModel

router = APIRouter(prefix="/users", tags=["users"])


class UserSearchResult(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str | None


def _mask_email(email: str) -> str:
    left, _, domain = email.partition("@")
    if len(left) <= 2:
        safe_left = left[0] + "*" if left else "*"
    else:
        safe_left = left[:2] + "*" * (len(left) - 2)
    return f"{safe_left}@{domain}" if domain else safe_left


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


@router.get("/search", response_model=list[UserSearchResult])
def search_users(
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[UserSearchResult]:
    has_active_organizer_event = db.execute(
        select(func.count(Event.id))
        .join(OrganizerProfile, OrganizerProfile.id == Event.organizer_id)
        .where(
            OrganizerProfile.user_id == user_id,
            Event.status != EventStatus.CANCELLED,
            Event.end_at > func.now(),
        )
    ).scalar_one()
    if not has_active_organizer_event:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User search is available for organizers with active events.",
        )

    cleaned = q.strip()
    like_q = f"%{cleaned}%"
    users = db.execute(
        select(User)
        .where(
            or_(
                User.full_name.ilike(like_q),
                User.email.ilike(like_q),
                User.phone.ilike(like_q),
            ),
            User.id != user_id,
        )
        .order_by(User.full_name.asc(), User.id.asc())
        .limit(limit)
    ).scalars().all()
    return [
        UserSearchResult(
            id=user.id,
            full_name=user.full_name,
            email=_mask_email(user.email),
            phone=_mask_phone(user.phone),
        )
        for user in users
    ]
