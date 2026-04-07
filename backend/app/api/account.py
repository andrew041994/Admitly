from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.account import ChangePasswordRequest, UpdateProfileRequest
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


@router.post("/change-password")
def post_change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    change_password(db, user=current_user, current_password=payload.current_password, new_password=payload.new_password)
    return {"success": True}
