from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.enums import PromoCodeDiscountType
from app.models.promo_code import PromoCode
from app.models.promo_code_ticket_tier import PromoCodeTicketTier
from app.models.ticket_hold import TicketHold
from app.models.ticket_tier import TicketTier
from app.schemas.order import OrderResponse
from app.schemas.promo_code import (
    CreateCompOrderRequest,
    PromoCodeCreateRequest,
    PromoCodeResponse,
    PromoCodeUpdateRequest,
    PromoCodeValidateRequest,
    PromoCodeValidateResponse,
)
from app.services.orders import OrderAuthorizationError, OrderFlowError, create_comp_order_for_user
from app.services.promo_codes import (
    PromoCodeValidationError,
    apply_promo_code_to_order_pricing_context,
    normalize_promo_code,
)
from app.services.reporting import EventReportingAuthorizationError, EventReportingNotFoundError, validate_event_reporting_access

router = APIRouter(prefix="/organizer/events", tags=["organizer-promos"])


def _authorize(db: Session, *, user_id: int, event_id: int) -> None:
    try:
        validate_event_reporting_access(db, user_id=user_id, event_id=event_id)
    except EventReportingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EventReportingAuthorizationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def _to_promo_response(promo: PromoCode, tier_ids: list[int]) -> PromoCodeResponse:
    return PromoCodeResponse(
        id=promo.id,
        event_id=promo.event_id,
        code=promo.code,
        description=promo.description,
        discount_type=promo.discount_type.value,
        discount_value=float(promo.discount_value),
        currency=promo.currency,
        is_active=promo.is_active,
        valid_from=promo.valid_from,
        valid_until=promo.valid_until,
        max_total_redemptions=promo.max_total_redemptions,
        max_redemptions_per_user=promo.max_redemptions_per_user,
        min_order_amount=float(promo.min_order_amount) if promo.min_order_amount is not None else None,
        applies_to_all_tiers=promo.applies_to_all_tiers,
        ticket_tier_ids=tier_ids,
    )


@router.post("/{event_id}/promo-codes", response_model=PromoCodeResponse, status_code=status.HTTP_201_CREATED)
def create_promo_code(
    event_id: int,
    payload: PromoCodeCreateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> PromoCodeResponse:
    _authorize(db, user_id=user_id, event_id=event_id)
    normalized = normalize_promo_code(payload.code)
    existing = db.execute(
        select(PromoCode).where(PromoCode.event_id == event_id, PromoCode.code_normalized == normalized)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Promo code already exists for event.")

    try:
        discount_type = PromoCodeDiscountType(payload.discount_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid discount_type.") from exc

    promo = PromoCode(
        event_id=event_id,
        code=payload.code.strip(),
        code_normalized=normalized,
        description=payload.description,
        discount_type=discount_type,
        discount_value=Decimal(str(payload.discount_value)),
        currency=payload.currency,
        is_active=payload.is_active,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        max_total_redemptions=payload.max_total_redemptions,
        max_redemptions_per_user=payload.max_redemptions_per_user,
        min_order_amount=Decimal(str(payload.min_order_amount)) if payload.min_order_amount is not None else None,
        applies_to_all_tiers=payload.applies_to_all_tiers,
        created_by_user_id=user_id,
    )
    db.add(promo)
    db.flush()

    tier_ids = list(dict.fromkeys(payload.ticket_tier_ids))
    if not payload.applies_to_all_tiers and tier_ids:
        tiers = db.execute(select(TicketTier.id).where(TicketTier.event_id == event_id, TicketTier.id.in_(tier_ids))).scalars().all()
        if len(tiers) != len(tier_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ticket tier scope.")
        db.add_all([PromoCodeTicketTier(promo_code_id=promo.id, ticket_tier_id=tier_id) for tier_id in tier_ids])
    db.commit()
    return _to_promo_response(promo, tier_ids)


@router.get("/{event_id}/promo-codes", response_model=list[PromoCodeResponse])
def list_promo_codes(
    event_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[PromoCodeResponse]:
    _authorize(db, user_id=user_id, event_id=event_id)
    promos = db.execute(select(PromoCode).where(PromoCode.event_id == event_id).order_by(PromoCode.created_at.desc())).scalars().all()
    response: list[PromoCodeResponse] = []
    for promo in promos:
        tier_ids = db.execute(select(PromoCodeTicketTier.ticket_tier_id).where(PromoCodeTicketTier.promo_code_id == promo.id)).scalars().all()
        response.append(_to_promo_response(promo, list(tier_ids)))
    return response


@router.patch("/{event_id}/promo-codes/{promo_code_id}", response_model=PromoCodeResponse)
def update_promo_code(
    event_id: int,
    promo_code_id: int,
    payload: PromoCodeUpdateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> PromoCodeResponse:
    _authorize(db, user_id=user_id, event_id=event_id)
    promo = db.execute(select(PromoCode).where(PromoCode.id == promo_code_id, PromoCode.event_id == event_id)).scalar_one_or_none()
    if promo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promo code not found.")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "min_order_amount" and value is not None:
            value = Decimal(str(value))
        setattr(promo, key, value)

    db.commit()
    tier_ids = db.execute(select(PromoCodeTicketTier.ticket_tier_id).where(PromoCodeTicketTier.promo_code_id == promo.id)).scalars().all()
    return _to_promo_response(promo, list(tier_ids))


@router.post("/{event_id}/promo-codes/validate", response_model=PromoCodeValidateResponse)
def validate_promo_code(
    event_id: int,
    payload: PromoCodeValidateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> PromoCodeValidateResponse:
    holds = db.execute(
        select(TicketHold).join(TicketTier, TicketTier.id == TicketHold.ticket_tier_id).where(
            TicketHold.user_id == user_id,
            TicketHold.id.in_(payload.hold_ids),
            TicketHold.event_id == event_id,
            TicketHold.order_id.is_(None),
        )
    ).scalars().all()
    if len(holds) != len(set(payload.hold_ids)):
        return PromoCodeValidateResponse(valid=False, reason="Invalid hold selection.")

    subtotal = sum((Decimal(h.quantity) * Decimal(h.ticket_tier.price_amount) for h in holds), Decimal("0.00"))
    tier_ids = [h.ticket_tier_id for h in holds]
    try:
        pricing = apply_promo_code_to_order_pricing_context(
            db,
            event_id=event_id,
            user_id=user_id,
            tier_ids=tier_ids,
            subtotal_amount=subtotal,
            promo_code_text=payload.code,
        )
    except PromoCodeValidationError as exc:
        return PromoCodeValidateResponse(valid=False, reason=str(exc))

    return PromoCodeValidateResponse(
        valid=True,
        subtotal_amount=float(pricing.subtotal_amount),
        discount_amount=float(pricing.discount_amount),
        total_amount=float(pricing.total_amount),
        code=pricing.promo_code_text,
    )


@router.post("/{event_id}/comp-orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_comp_order(
    event_id: int,
    payload: CreateCompOrderRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> OrderResponse:
    try:
        order = create_comp_order_for_user(
            db,
            event_id=event_id,
            purchaser_user_id=payload.purchaser_user_id,
            actor_user_id=user_id,
            ticket_requests=[item.model_dump() for item in payload.tickets],
            reason=payload.reason,
        )
        db.commit()
    except (OrderAuthorizationError,) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except OrderFlowError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return OrderResponse(
        id=order.id,
        user_id=order.user_id,
        event_id=order.event_id,
        status=order.status.value,
        subtotal_amount=float(order.subtotal_amount),
        discount_amount=float(order.discount_amount),
        total_amount=float(order.total_amount),
        pricing_source=order.pricing_source.value,
        is_comp=order.is_comp,
        promo_code_text=order.promo_code_text,
        currency=order.currency,
        refund_status=order.refund_status,
        cancelled_at=order.cancelled_at,
        cancelled_by_user_id=order.cancelled_by_user_id,
        cancel_reason=order.cancel_reason,
        refunded_at=order.refunded_at,
        refunded_by_user_id=order.refunded_by_user_id,
        refund_reason=order.refund_reason,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=[
            {
                "id": item.id,
                "ticket_tier_id": item.ticket_tier_id,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
            }
            for item in order.order_items
        ],
    )
