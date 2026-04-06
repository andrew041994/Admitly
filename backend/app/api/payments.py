from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.mmg import MMGCallbackResponse
from app.services.orders import OrderNotPayableError
from app.services.payments import MMGProviderError, PaymentError, handle_mmg_callback

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/mmg/callback", response_model=MMGCallbackResponse)
def mmg_callback(payload: dict, db: Session = Depends(get_db)) -> MMGCallbackResponse:
    try:
        snapshot = handle_mmg_callback(db, payload=payload)
    except MMGProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OrderNotPayableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PaymentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return MMGCallbackResponse(
        order_id=snapshot.order_id,
        status=snapshot.status,
        payment_verification_status=snapshot.payment_verification_status,
    )


@router.get("/mmg/return")
def mmg_return() -> dict[str, str]:
    return {
        "message": "Return acknowledged. Payment is only finalized after backend verification.",
    }
