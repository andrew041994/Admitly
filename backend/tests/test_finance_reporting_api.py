import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.main import app


def test_finance_reporting_routes_registered() -> None:
    route_paths = {route.path for route in app.routes}

    assert "/organizer/events/{event_id}/finance-summary" in route_paths
    assert "/organizer/events/{event_id}/finance-orders" in route_paths
    assert "/organizer/events/payout-summary" in route_paths
    assert "/internal/orders/{order_id}/reconcile" in route_paths
    assert "/internal/orders/{order_id}/payout-status" in route_paths
    assert "/refunds/request" in route_paths
    assert "/refunds/my" in route_paths
    assert "/disputes" in route_paths
    assert "/admin/refunds" in route_paths
    assert "/admin/refunds/{refund_id}/approve" in route_paths
    assert "/admin/refunds/{refund_id}/reject" in route_paths
    assert "/admin/disputes" in route_paths
    assert "/admin/disputes/{dispute_id}/resolve" in route_paths
    assert "/admin/disputes/{dispute_id}/reject" in route_paths
