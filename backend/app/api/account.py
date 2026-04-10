from sqlalchemy import func, select
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.event import Event
from app.models.event_staff import EventStaff
from app.models.organizer_profile import OrganizerProfile
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.account import AccountProfileResponse, ChangePasswordRequest, UpdateProfileRequest
from app.schemas.auth import UserResponse
from app.services.auth import change_password, update_profile

router = APIRouter(prefix="/account", tags=["account"])


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone_number=user.phone,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_admin=user.is_admin,
        auth_provider=user.auth_provider,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


@router.patch("/profile", response_model=UserResponse)
def patch_profile(
    payload: UpdateProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    updated = update_profile(db, user=current_user, full_name=payload.full_name, phone_number=payload.phone_number)
    return _to_user_response(updated)


@router.get("/profile", response_model=AccountProfileResponse)
def get_profile(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> AccountProfileResponse:
    current_user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    my_tickets_count = db.execute(select(func.count(Ticket.id)).where(Ticket.owner_user_id == current_user.id)).scalar_one()
    my_events_count = db.execute(
        select(func.count(Event.id))
        .join(OrganizerProfile, OrganizerProfile.id == Event.organizer_id)
        .where(OrganizerProfile.user_id == current_user.id)
    ).scalar_one()
    staff_events_count = db.execute(
        select(func.count(EventStaff.id)).where(
            EventStaff.user_id == current_user.id,
            EventStaff.is_active.is_(True),
        )
    ).scalar_one()
    return AccountProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        phone_number=current_user.phone,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        my_tickets_count=int(my_tickets_count or 0),
        my_events_count=int(my_events_count or 0),
        staff_events_count=int(staff_events_count or 0),
    )


@router.post("/change-password")
def post_change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    change_password(db, user=current_user, current_password=payload.current_password, new_password=payload.new_password)
    return {"success": True}
