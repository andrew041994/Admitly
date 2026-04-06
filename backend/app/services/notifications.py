from __future__ import annotations

import logging

from app.models.event import Event
from app.models.order import Order

logger = logging.getLogger(__name__)


def notify_order_cancelled(order: Order, *, actor_user_id: int) -> None:
    logger.info(
        "order_notification_cancelled",
        extra={
            "order_id": order.id,
            "event_id": order.event_id,
            "owner_user_id": order.user_id,
            "actor_user_id": actor_user_id,
        },
    )


def notify_order_refunded(order: Order, *, actor_user_id: int) -> None:
    logger.info(
        "order_notification_refunded",
        extra={
            "order_id": order.id,
            "event_id": order.event_id,
            "owner_user_id": order.user_id,
            "actor_user_id": actor_user_id,
        },
    )


def notify_event_cancelled(event: Event, *, actor_user_id: int) -> None:
    logger.info(
        "event_notification_cancelled",
        extra={
            "event_id": event.id,
            "actor_user_id": actor_user_id,
        },
    )
