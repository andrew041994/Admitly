from enum import Enum


class EventStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class EventVisibility(str, Enum):
    PUBLIC = "public"
    UNLISTED = "unlisted"
    PRIVATE = "private"


class EventApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class EventStaffRole(str, Enum):
    OWNER = "owner"
    MANAGER = "manager"
    CHECKIN = "checkin"
    SUPPORT = "support"


class OrderStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ReconciliationStatus(str, Enum):
    UNRECONCILED = "unreconciled"
    RECONCILED = "reconciled"
    DISPUTED = "disputed"
    EXCLUDED = "excluded"


class PayoutStatus(str, Enum):
    NOT_READY = "not_ready"
    ELIGIBLE = "eligible"
    INCLUDED = "included"
    PAID = "paid"
    HELD = "held"


class TicketStatus(str, Enum):
    ISSUED = "issued"
    CHECKED_IN = "checked_in"
    VOIDED = "voided"


class TransferInviteStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ReminderType(str, Enum):
    HOURS_24_BEFORE = "24_hours_before"
    HOURS_3_BEFORE = "3_hours_before"
    MINUTES_30_BEFORE = "30_minutes_before"


class PromoCodeDiscountType(str, Enum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"


class PricingSource(str, Enum):
    STANDARD = "standard"
    PROMO_CODE = "promo_code"
    COMP = "comp"


class RefundStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSED = "processed"


class DisputeStatus(str, Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class RefundReason(str, Enum):
    EVENT_CANCELED = "event_canceled"
    DUPLICATE_PURCHASE = "duplicate_purchase"
    FRAUD = "fraud"
    USER_REQUEST = "user_request"
    OTHER = "other"


class FinancialEntryType(str, Enum):
    REFUND_REVERSAL = "refund_reversal"


class BalanceAdjustmentType(str, Enum):
    REFUND_OFFSET = "refund_offset"


class EventRefundBatchStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
