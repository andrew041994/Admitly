from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.ticket_holds import get_current_user_id
from app.db.session import get_db
from app.models.user import User
from app.schemas.integrations import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    IntegrationCatalogResponse,
    WebhookDeliveryResponse,
    WebhookEndpointCreateRequest,
    WebhookEndpointCreateResponse,
    WebhookEndpointPatchRequest,
    WebhookEndpointResponse,
)
from app.services.integrations import (
    INTEGRATION_API_VERSION,
    SCOPE_READ,
    SCOPE_WRITE,
    SUPPORTED_WEBHOOK_EVENTS,
    authenticate_api_key,
    create_api_key,
    create_webhook_endpoint,
    dispatch_pending_webhook_deliveries,
    list_api_keys,
    list_deliveries,
    list_webhook_endpoints,
    require_scope,
    redeliver_webhook_delivery,
    revoke_api_key,
    scopes_from_csv,
    update_webhook_endpoint,
)

router = APIRouter(prefix="/admin/integrations", tags=["integrations"])
public_router = APIRouter(prefix="/public/integrations", tags=["public-integrations"])


def _require_admin(db: Session, *, user_id: int) -> None:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")


def _to_key_response(item) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=item.id,
        name=item.name,
        key_prefix=item.key_prefix,
        scopes=sorted(scopes_from_csv(item.scopes_csv)),
        created_at=item.created_at,
        revoked_at=item.revoked_at,
        last_used_at=item.last_used_at,
    )


def _to_endpoint_response(item) -> WebhookEndpointResponse:
    return WebhookEndpointResponse(
        id=item.id,
        name=item.name,
        target_url=item.target_url,
        subscribed_events=[part for part in item.subscribed_events_csv.split(",") if part],
        schema_version=item.schema_version,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
        disabled_at=item.disabled_at,
    )


def _to_delivery_response(item) -> WebhookDeliveryResponse:
    delivery = item.delivery
    return WebhookDeliveryResponse(
        id=delivery.id,
        endpoint_id=delivery.endpoint_id,
        endpoint_url=item.endpoint_url,
        event_id=delivery.event_id,
        event_type=delivery.event_type,
        schema_version=delivery.schema_version,
        attempt_number=delivery.attempt_number,
        status=delivery.status,
        requested_at=delivery.requested_at,
        response_status_code=delivery.response_status_code,
        failure_reason=delivery.failure_reason,
        next_retry_at=delivery.next_retry_at,
        delivered_at=delivery.delivered_at,
        delivery_kind=delivery.delivery_kind,
        redelivery_of_delivery_id=delivery.redelivery_of_delivery_id,
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse])
def get_api_keys(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[ApiKeyResponse]:
    _require_admin(db, user_id=user_id)
    return [_to_key_response(item) for item in list_api_keys(db, user_id=user_id)]


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_api_key_route(
    payload: ApiKeyCreateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> ApiKeyCreateResponse:
    _require_admin(db, user_id=user_id)
    key, raw_key = create_api_key(db, user_id=user_id, name=payload.name, scopes=payload.scopes)
    db.commit()
    db.refresh(key)
    response = _to_key_response(key)
    return ApiKeyCreateResponse(**response.model_dump(), raw_key=raw_key)


@router.post("/api-keys/{key_id}/revoke", response_model=ApiKeyResponse)
def revoke_api_key_route(
    key_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> ApiKeyResponse:
    _require_admin(db, user_id=user_id)
    key = revoke_api_key(db, key_id=key_id, user_id=user_id)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    db.commit()
    db.refresh(key)
    return _to_key_response(key)


@router.get("/webhooks", response_model=list[WebhookEndpointResponse])
def get_webhooks(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[WebhookEndpointResponse]:
    _require_admin(db, user_id=user_id)
    return [_to_endpoint_response(item) for item in list_webhook_endpoints(db, user_id=user_id)]


@router.post("/webhooks", response_model=WebhookEndpointCreateResponse, status_code=status.HTTP_201_CREATED)
def create_webhook(
    payload: WebhookEndpointCreateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> WebhookEndpointCreateResponse:
    _require_admin(db, user_id=user_id)
    endpoint, signing_secret = create_webhook_endpoint(
        db,
        user_id=user_id,
        name=payload.name,
        target_url=payload.target_url,
        subscribed_events=payload.subscribed_events,
    )
    db.commit()
    db.refresh(endpoint)
    body = _to_endpoint_response(endpoint)
    return WebhookEndpointCreateResponse(**body.model_dump(), signing_secret=signing_secret)


@router.patch("/webhooks/{endpoint_id}", response_model=WebhookEndpointResponse)
def patch_webhook(
    endpoint_id: int,
    payload: WebhookEndpointPatchRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> WebhookEndpointResponse:
    _require_admin(db, user_id=user_id)
    endpoint = update_webhook_endpoint(
        db,
        endpoint_id=endpoint_id,
        user_id=user_id,
        name=payload.name,
        target_url=payload.target_url,
        subscribed_events=payload.subscribed_events,
        is_active=payload.is_active,
    )
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")
    db.commit()
    db.refresh(endpoint)
    return _to_endpoint_response(endpoint)


@router.get("/deliveries", response_model=list[WebhookDeliveryResponse])
def get_deliveries(
    endpoint_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[WebhookDeliveryResponse]:
    _require_admin(db, user_id=user_id)
    return [_to_delivery_response(item) for item in list_deliveries(db, user_id=user_id, endpoint_id=endpoint_id)]


@router.post("/deliveries/{delivery_id}/redeliver", response_model=WebhookDeliveryResponse, status_code=status.HTTP_201_CREATED)
def redeliver_delivery_route(
    delivery_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> WebhookDeliveryResponse:
    _require_admin(db, user_id=user_id)
    attempt = redeliver_webhook_delivery(db, delivery_id=delivery_id, user_id=user_id)
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found.")
    db.commit()
    rows = list_deliveries(db, user_id=user_id)
    row = next((entry for entry in rows if entry.delivery.id == attempt.id), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load redelivery attempt.")
    return _to_delivery_response(row)


@router.post("/deliveries/dispatch")
def dispatch_pending(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> dict[str, int]:
    _require_admin(db, user_id=user_id)
    processed = dispatch_pending_webhook_deliveries(db)
    db.commit()
    return {"processed": processed}


def get_api_key_principal(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    key = authenticate_api_key(db, raw_key=x_api_key)
    if key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
    return key


@public_router.get("/catalog", response_model=IntegrationCatalogResponse)
def get_catalog(
    key=Depends(get_api_key_principal),
) -> IntegrationCatalogResponse:
    if not require_scope(key, SCOPE_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing integrations:read scope.")
    return IntegrationCatalogResponse(
        version=INTEGRATION_API_VERSION,
        supported_events=sorted(SUPPORTED_WEBHOOK_EVENTS),
        signature_headers={
            "timestamp": "X-Admitly-Timestamp",
            "signature": "X-Admitly-Signature",
            "format": "HMAC_SHA256(secret, `${timestamp}.${raw_body}`) as v1=<hex>",
        },
    )
