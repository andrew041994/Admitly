from __future__ import annotations


ORDER_REFERENCE_PREFIX = "ORD"
ORDER_REFERENCE_PAD = 8


def format_order_reference(order_id: int) -> str:
    return f"{ORDER_REFERENCE_PREFIX}-{order_id:0{ORDER_REFERENCE_PAD}d}"

