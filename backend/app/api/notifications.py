from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.schemas.notification import (
    PushTokenDeleteRequest,
    PushTokenDeleteResponse,
    PushTokenRegisterRequest,
    PushTokenRegisterResponse,
)
from app.services.notifications import deactivate_push_token, register_push_token

router = APIRouter(tags=["notifications"])


@router.post("/me/push-tokens", response_model=PushTokenRegisterResponse, status_code=status.HTTP_201_CREATED)
def register_my_push_token(
    payload: PushTokenRegisterRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> PushTokenRegisterResponse:
    token = register_push_token(db, user_id=user_id, token=payload.token, platform=payload.platform)
    return PushTokenRegisterResponse(success=True, token=token.token, platform=token.platform, is_active=token.is_active)


@router.delete("/me/push-tokens", response_model=PushTokenDeleteResponse)
def delete_my_push_token(
    payload: PushTokenDeleteRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> PushTokenDeleteResponse:
    deleted = deactivate_push_token(db, user_id=user_id, token=payload.token)
    return PushTokenDeleteResponse(success=deleted)
