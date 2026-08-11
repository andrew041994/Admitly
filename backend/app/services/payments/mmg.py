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


class MMGCallbackAuthenticity(str, Enum):
    VERIFIED_MOCK = "verified_mock"
    UNVERIFIED = "unverified"


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
    provider_status: str
    authenticity: MMGCallbackAuthenticity


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


def validate_mmg_provider_config() -> None:
    if settings.mmg_provider_mode not in {"mock", "live"}:
        raise MMGProviderError("MMG_PROVIDER_MODE must be 'mock' or 'live'.")
    if settings.mmg_provider_mode == "live":
        _require_live_config()
    else:
        _require_mock_allowed()


def _require_mock_allowed() -> None:
    if settings.is_production:
        raise MMGProviderError("Mock MMG behavior is disabled in production.")


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

    _require_mock_allowed()

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

    _require_mock_allowed()

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
    if not isinstance(payload, dict):
        raise MMGProviderError("Callback payload must be an object.")
    raw_reference = payload.get("payment_reference") or payload.get("reference")
    if not isinstance(raw_reference, str):
        raise MMGProviderError("Callback payload missing payment reference.")
    reference = raw_reference.strip()
    if not reference:
        raise MMGProviderError("Callback payload missing payment reference.")
    if len(reference) > 255:
        raise MMGProviderError("Callback payment reference is too long.")

    if "paid" in payload:
        raw_paid = payload["paid"]
        if not isinstance(raw_paid, bool):
            raise MMGProviderError("Callback paid value must be boolean.")
        paid = raw_paid
        provider_status = "paid" if paid else "pending"
    else:
        raw_status = payload.get("status")
        if not isinstance(raw_status, str):
            raise MMGProviderError("Callback payload missing payment status.")
        normalized_status = raw_status.strip().lower()
        if normalized_status in {"paid", "success", "verified"}:
            paid = True
            provider_status = "paid"
        elif normalized_status in {"pending", "failed", "cancelled", "canceled"}:
            paid = False
            provider_status = "cancelled" if normalized_status in {"cancelled", "canceled"} else normalized_status
        else:
            raise MMGProviderError("Callback payment status is not recognized.")

    authenticity = MMGCallbackAuthenticity.UNVERIFIED
    if settings.mmg_provider_mode == "mock":
        _require_mock_allowed()
        authenticity = MMGCallbackAuthenticity.VERIFIED_MOCK
    return MMGCallbackPayload(
        payment_reference=reference,
        paid=paid,
        provider_status=provider_status,
        authenticity=authenticity,
    )


@dataclass(slots=True)
class MMGRefundOutcome:
    status: str
    provider_reference: str | None = None
    message: str | None = None


def initiate_refund_with_provider(*, order_id: int, payment_reference: str | None) -> MMGRefundOutcome:
    if settings.mmg_provider_mode == "live":
        _require_live_config()
        # TODO: replace with real MMG refund initiation once provider refund APIs are available.
        raise MMGProviderError("MMG live refunds are not implemented yet.")

    _require_mock_allowed()
    return MMGRefundOutcome(status="refunded", provider_reference=payment_reference, message="Mock refund recorded.")


def verify_refund_status(*, provider_reference: str | None) -> MMGRefundOutcome:
    if settings.mmg_provider_mode == "live":
        _require_live_config()
        # TODO: replace with real MMG refund status lookup when available.
        raise MMGProviderError("MMG live refund lookup is not implemented yet.")

    _require_mock_allowed()
    return MMGRefundOutcome(status="refunded", provider_reference=provider_reference)
