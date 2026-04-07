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


class SupportCaseStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    WAITING_ON_CUSTOMER = "waiting_on_customer"
    WAITING_ON_PAYMENT_PROVIDER = "waiting_on_payment_provider"
    RESOLVED = "resolved"
    CLOSED = "closed"


class SupportCasePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class MessageTemplateType(str, Enum):
    ORDER_CONFIRMATION = "order_confirmation"
    TICKET_ISSUED = "ticket_issued"
    TRANSFER_INVITE = "transfer_invite"
    TRANSFER_ACCEPTED = "transfer_accepted"
    REFUND_PROCESSED = "refund_processed"
    REMINDER = "reminder"
    EVENT_DAY_UPDATE = "event_day_update"
    ORGANIZER_BROADCAST = "organizer_broadcast"


class MessageChannel(str, Enum):
    EMAIL = "email"
    PUSH = "push"


class MessageDeliveryStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
