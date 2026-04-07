from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import PricingSource, PromoCodeDiscountType
from app.models.promo_code import PromoCode
from app.models.promo_code_redemption import PromoCodeRedemption
from app.models.promo_code_ticket_tier import PromoCodeTicketTier
from app.services.ticket_holds import get_guyana_now

MONEY_QUANT = Decimal("0.01")


class PromoCodeError(ValueError):
    pass


class PromoCodeValidationError(PromoCodeError):
    pass


@dataclass(frozen=True)
class PricingResult:
    subtotal_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    pricing_source: PricingSource
    promo_code_id: int | None
    promo_code_text: str | None
    discount_type: str | None
    discount_value_snapshot: Decimal | None
    is_comp: bool


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def normalize_promo_code(code: str) -> str:
    return code.strip().upper()


def get_promo_code_by_code(db: Session, *, event_id: int, code: str) -> PromoCode | None:
    normalized = normalize_promo_code(code)
    return db.execute(
        select(PromoCode).where(PromoCode.event_id == event_id, PromoCode.code_normalized == normalized)
    ).scalar_one_or_none()


def validate_promo_code_for_order_context(
    db: Session,
    *,
    promo_code: PromoCode,
    user_id: int,
    tier_ids: list[int],
    subtotal_amount: Decimal,
    now: datetime | None = None,
) -> None:
    reference_now = now or get_guyana_now()
    if not promo_code.is_active:
        raise PromoCodeValidationError("Promo code is inactive.")
    if promo_code.valid_from and reference_now < promo_code.valid_from:
        raise PromoCodeValidationError("Promo code is not active yet.")
    if promo_code.valid_until and reference_now > promo_code.valid_until:
        raise PromoCodeValidationError("Promo code has expired.")
    if promo_code.min_order_amount and subtotal_amount < promo_code.min_order_amount:
        raise PromoCodeValidationError("Order does not meet minimum amount for this promo code.")

    total_redemptions = db.execute(
        select(func.count(PromoCodeRedemption.id)).where(PromoCodeRedemption.promo_code_id == promo_code.id)
    ).scalar_one()
    if promo_code.max_total_redemptions is not None and int(total_redemptions or 0) >= promo_code.max_total_redemptions:
        raise PromoCodeValidationError("Promo code redemption limit reached.")

    user_redemptions = db.execute(
        select(func.count(PromoCodeRedemption.id)).where(
            PromoCodeRedemption.promo_code_id == promo_code.id,
            PromoCodeRedemption.user_id == user_id,
        )
    ).scalar_one()
    if promo_code.max_redemptions_per_user is not None and int(user_redemptions or 0) >= promo_code.max_redemptions_per_user:
        raise PromoCodeValidationError("Promo code user limit reached.")

    if not promo_code.applies_to_all_tiers:
        allowed_tier_ids = set(
            db.execute(
                select(PromoCodeTicketTier.ticket_tier_id).where(PromoCodeTicketTier.promo_code_id == promo_code.id)
            ).scalars()
        )
        if not allowed_tier_ids or not set(tier_ids).issubset(allowed_tier_ids):
            raise PromoCodeValidationError("Promo code does not apply to selected ticket tiers.")


def calculate_discount_for_order_context(*, promo_code: PromoCode, subtotal_amount: Decimal) -> Decimal:
    subtotal = _money(subtotal_amount)
    if promo_code.discount_type == PromoCodeDiscountType.PERCENTAGE:
        discount = _money((subtotal * Decimal(promo_code.discount_value)) / Decimal("100"))
    else:
        discount = _money(Decimal(promo_code.discount_value))

    if discount < Decimal("0.00"):
        raise PromoCodeValidationError("Promo discount cannot be negative.")
    return min(discount, subtotal)


def apply_promo_code_to_order_pricing_context(
    db: Session,
    *,
    event_id: int,
    user_id: int,
    tier_ids: list[int],
    subtotal_amount: Decimal,
    promo_code_text: str,
    now: datetime | None = None,
) -> PricingResult:
    promo_code = get_promo_code_by_code(db, event_id=event_id, code=promo_code_text)
    if promo_code is None:
        raise PromoCodeValidationError("Promo code not found.")

    validate_promo_code_for_order_context(
        db,
        promo_code=promo_code,
        user_id=user_id,
        tier_ids=tier_ids,
        subtotal_amount=subtotal_amount,
        now=now,
    )
    discount_amount = calculate_discount_for_order_context(promo_code=promo_code, subtotal_amount=subtotal_amount)
    total = _money(max(_money(subtotal_amount) - discount_amount, Decimal("0.00")))

    return PricingResult(
        subtotal_amount=_money(subtotal_amount),
        discount_amount=discount_amount,
        total_amount=total,
        pricing_source=PricingSource.PROMO_CODE if discount_amount > Decimal("0.00") else PricingSource.STANDARD,
        promo_code_id=promo_code.id,
        promo_code_text=promo_code.code,
        discount_type=promo_code.discount_type.value,
        discount_value_snapshot=_money(Decimal(promo_code.discount_value)),
        is_comp=False,
    )


def standard_pricing(subtotal_amount: Decimal) -> PricingResult:
    subtotal = _money(subtotal_amount)
    return PricingResult(
        subtotal_amount=subtotal,
        discount_amount=Decimal("0.00"),
        total_amount=subtotal,
        pricing_source=PricingSource.STANDARD,
        promo_code_id=None,
        promo_code_text=None,
        discount_type=None,
        discount_value_snapshot=None,
        is_comp=False,
    )


def comp_pricing(subtotal_amount: Decimal) -> PricingResult:
    subtotal = _money(subtotal_amount)
    return PricingResult(
        subtotal_amount=subtotal,
        discount_amount=subtotal,
        total_amount=Decimal("0.00"),
        pricing_source=PricingSource.COMP,
        promo_code_id=None,
        promo_code_text=None,
        discount_type=None,
        discount_value_snapshot=None,
        is_comp=True,
    )


def record_promo_redemption_for_order(db: Session, *, order) -> None:
    if order.promo_code_id is None or Decimal(order.discount_amount) <= Decimal("0.00"):
        return
    existing = db.execute(
        select(PromoCodeRedemption).where(PromoCodeRedemption.order_id == order.id)
    ).scalar_one_or_none()
    if existing is not None:
        return

    db.add(
        PromoCodeRedemption(
            promo_code_id=order.promo_code_id,
            order_id=order.id,
            user_id=order.user_id,
            redeemed_at=get_guyana_now(),
            discount_amount=Decimal(order.discount_amount),
        )
    )
