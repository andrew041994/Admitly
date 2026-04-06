from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib

from app.core.config import settings


class MMGProviderError(ValueError):
    """Base provider error."""


class MMGLiveConfigError(MMGProviderError):
    """Raised when live mode lacks required values."""


class MMGVerificationResult(str, Enum):
    VERIFIED = "verified"
    PENDING = "pending_verification"
    REJECTED = "rejected"


@dataclass(slots=True)
class MMGCheckoutResult:
    payment_reference: str
    checkout_url: str


@dataclass(slots=True)
class MMGAgentVerificationOutcome:
    status: MMGVerificationResult
    message: str


@dataclass(slots=True)
class MMGCallbackPayload:
    payment_reference: str
    paid: bool


def _require_live_config() -> None:
    required = {
        "MMG_BASE_URL": settings.mmg_base_url,
        "MMG_MERCHANT_ID": settings.mmg_merchant_id,
        "MMG_API_KEY": settings.mmg_api_key,
        "MMG_API_SECRET": settings.mmg_api_secret,
        "MMG_CALLBACK_URL": settings.mmg_callback_url,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise MMGLiveConfigError(
            "MMG live mode is missing required config: " + ", ".join(sorted(missing))
        )


def _mock_checkout_url(reference: str) -> str:
    return f"https://mock.mmg.local/checkout/{reference}"


def create_checkout_for_order(
    *,
    order_id: int,
    amount: str,
    currency: str,
    existing_reference: str | None = None,
    existing_checkout_url: str | None = None,
) -> MMGCheckoutResult:
    if settings.mmg_provider_mode == "live":
        _require_live_config()
        # TODO: replace with real MMG checkout session creation once docs/credentials are available.
        raise MMGProviderError("MMG live checkout is not implemented yet.")

    reference = existing_reference or f"MMG-CHK-{order_id}"
    checkout_url = existing_checkout_url or _mock_checkout_url(reference)
    _ = (amount, currency)
    return MMGCheckoutResult(payment_reference=reference, checkout_url=checkout_url)


def create_agent_payment_reference(*, order_id: int, existing_reference: str | None = None) -> str:
    if existing_reference:
        return existing_reference

    digest = hashlib.sha1(f"order:{order_id}".encode("utf-8")).hexdigest()[:8].upper()
    return f"AGT-{order_id}-{digest}"


def verify_agent_payment_reference(
    *,
    order_reference: str,
    submitted_reference: str,
) -> MMGAgentVerificationOutcome:
    if submitted_reference.strip() != order_reference:
        return MMGAgentVerificationOutcome(
            status=MMGVerificationResult.REJECTED,
            message="Submitted reference does not match the order reference.",
        )

    if not settings.mmg_agent_auto_verify_enabled:
        return MMGAgentVerificationOutcome(
            status=MMGVerificationResult.PENDING,
            message="Awaiting manual verification.",
        )

    if settings.mmg_provider_mode == "live":
        _require_live_config()
        # TODO: replace with real MMG agent reference verification once provider API/callback docs are available.
        return MMGAgentVerificationOutcome(
            status=MMGVerificationResult.PENDING,
            message="Live verification not wired yet; pending manual verification.",
        )

    if submitted_reference.endswith("-PENDING"):
        return MMGAgentVerificationOutcome(
            status=MMGVerificationResult.PENDING,
            message="Payment submitted; verification is pending.",
        )
    if submitted_reference.endswith("-FAIL"):
        return MMGAgentVerificationOutcome(
            status=MMGVerificationResult.REJECTED,
            message="Payment reference rejected by provider.",
        )

    return MMGAgentVerificationOutcome(
        status=MMGVerificationResult.VERIFIED,
        message="Payment verified.",
    )


def parse_checkout_callback(payload: dict) -> MMGCallbackPayload:
    reference = str(payload.get("payment_reference") or payload.get("reference") or "").strip()
    if not reference:
        raise MMGProviderError("Callback payload missing payment reference.")

    raw_paid = payload.get("paid", payload.get("status"))
    paid = str(raw_paid).lower() in {"1", "true", "paid", "success", "verified"}
    return MMGCallbackPayload(payment_reference=reference, paid=paid)


@dataclass(slots=True)
class MMGRefundOutcome:
    status: str
    provider_reference: str | None = None
    message: str | None = None


def initiate_refund_with_provider(*, order_id: int, payment_reference: str | None) -> MMGRefundOutcome:
    if settings.mmg_provider_mode == "live":
        _require_live_config()
        # TODO: replace with real MMG refund initiation once provider refund APIs are available.
        return MMGRefundOutcome(status="pending", provider_reference=payment_reference, message="Refund queued.")

    return MMGRefundOutcome(status="refunded", provider_reference=payment_reference, message="Mock refund recorded.")


def verify_refund_status(*, provider_reference: str | None) -> MMGRefundOutcome:
    if settings.mmg_provider_mode == "live":
        _require_live_config()
        # TODO: replace with real MMG refund status lookup when available.
        return MMGRefundOutcome(status="pending", provider_reference=provider_reference)

    return MMGRefundOutcome(status="refunded", provider_reference=provider_reference)
