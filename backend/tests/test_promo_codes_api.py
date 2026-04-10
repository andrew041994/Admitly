import os

from app.main import app


def test_promo_and_comp_routes_registered() -> None:
    route_paths = {route.path for route in app.routes}

    assert "/organizer/events/{event_id}/promo-codes" in route_paths
    assert "/organizer/events/{event_id}/promo-codes/{promo_code_id}" in route_paths
    assert "/organizer/events/{event_id}/promo-codes/validate" in route_paths
    assert "/organizer/events/{event_id}/comp-orders" in route_paths
