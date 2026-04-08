from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.rate_limit import apply_rate_limit, request_client_ip
from app.api.ticket_holds import get_current_user_id
from app.core.config import settings
from app.db.session import get_db
from app.models.admin_action_audit import AdminActionAudit
from app.models.dispute import Dispute
from app.models.enums import SupportCasePriority, SupportCaseStatus
from app.models.order import Order
from app.models.refund import Refund
from app.models.support_case_note import SupportCaseNote
from app.models.ticket import Ticket
from app.models.ticket_transfer_invite import TicketTransferInvite
from app.models.user import User
from app.schemas.support import (
    AdminAuditResponse,
    SupportActionRequest,
    SupportActionResponse,
    SupportCaseNoteResponse,
    SupportCasePatchRequest,
    SupportCaseResponse,
    SupportMessageLogResponse,
    SupportNoteCreateRequest,
    SupportSnapshotResponse,
    SupportTimelineItemResponse,
)
from app.services.messaging import list_message_history
from app.services.support import (
    SupportConflictError,
    SupportError,
    SupportNotFoundError,
    add_support_case_note,
    build_order_support_timeline,
    get_relevant_support_case_for_order,
    patch_support_case,
    run_admin_support_action,
)

router = APIRouter(prefix="/admin/support/orders", tags=["admin-support"])


def _require_admin(db: Session, *, user_id: int) -> None:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")


def _to_note_response(note: SupportCaseNote) -> SupportCaseNoteResponse:
    return SupportCaseNoteResponse(
        id=note.id,
        support_case_id=note.support_case_id,
        author_user_id=note.author_user_id,
        body=note.body,
        is_system_note=note.is_system_note,
        created_at=note.created_at,
    )


def _to_case_response(case) -> SupportCaseResponse:
    return SupportCaseResponse(
        id=case.id,
        order_id=case.order_id,
        status=case.status.value,
        priority=case.priority.value,
        category=case.category,
        created_by_user_id=case.created_by_user_id,
        assigned_to_user_id=case.assigned_to_user_id,
        closed_at=case.closed_at,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


@router.get("/{order_id}", response_model=SupportSnapshotResponse)
def get_support_snapshot(
    order_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> SupportSnapshotResponse:
    _require_admin(db, user_id=user_id)
    order = db.execute(select(Order).where(Order.id == order_id)).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

    case = get_relevant_support_case_for_order(db, order_id=order_id)
    notes = (
        db.execute(select(SupportCaseNote).where(SupportCaseNote.support_case_id == case.id).order_by(SupportCaseNote.created_at.asc()))
        .scalars()
        .all()
        if case
        else []
    )
    audits = db.execute(
        select(AdminActionAudit).where(
            or_(
                and_(AdminActionAudit.target_type == "order", AdminActionAudit.target_id == str(order_id)),
                and_(AdminActionAudit.target_type == "support_case", AdminActionAudit.target_id == str(case.id if case else "")),
            )
        ).order_by(AdminActionAudit.created_at.desc(), AdminActionAudit.id.desc())
    ).scalars().all()

    timeline = [SupportTimelineItemResponse(**item) for item in build_order_support_timeline(db, order_id)]
    quantity = int(sum(item.quantity for item in order.order_items))
    dispute_count = db.execute(select(Dispute).where(Dispute.order_id == order_id)).scalars().all()
    transfer_invite_count = db.execute(
        select(TicketTransferInvite)
        .join(Ticket, Ticket.id == TicketTransferInvite.ticket_id)
        .where(Ticket.order_id == order_id)
    ).scalars().all()
    message_history = list_message_history(db, related_entity_type="order", related_entity_id=order_id)

    return SupportSnapshotResponse(
        order_id=order.id,
        order_reference=order.reference_code,
        event_id=order.event_id,
        event_title=order.event.title if order.event else None,
        buyer_user_id=order.user_id,
        order_status=order.status.value,
        quantity=quantity,
        subtotal_amount=float(order.subtotal_amount),
        discount_amount=float(order.discount_amount),
        total_amount=float(order.total_amount),
        currency=order.currency,
        payment_reference=order.payment_reference,
        payment_verification_status=order.payment_verification_status,
        payment_submitted_at=order.payment_submitted_at,
        paid_at=order.paid_at,
        refund_status=order.refund_status,
        refunded_at=order.refunded_at,
        dispute_count=len(dispute_count),
        transfer_invite_count=len(transfer_invite_count),
        reconciliation_status=order.reconciliation_status.value,
        payout_status=order.payout_status.value,
        promo_code_text=order.promo_code_text,
        support_case=_to_case_response(case) if case else None,
        support_notes=[_to_note_response(note) for note in notes],
        timeline=timeline,
        admin_audits=[
            AdminAuditResponse(
                id=a.id,
                actor_user_id=a.actor_user_id,
                target_type=a.target_type,
                target_id=a.target_id,
                action_type=a.action_type,
                reason=a.reason,
                metadata=a.metadata_json,
                created_at=a.created_at,
            )
            for a in audits
        ],
        message_history=[
            SupportMessageLogResponse(
                id=item.id,
                template_type=item.template_type.value,
                channel=item.channel.value,
                status=item.status.value,
                provider_status=item.provider_status,
                is_manual_resend=item.is_manual_resend,
                resend_of_message_id=item.resend_of_message_id,
                actor_user_id=item.actor_user_id,
                created_at=item.created_at,
            )
            for item in message_history
        ],
    )


@router.get("/{order_id}/notes", response_model=list[SupportCaseNoteResponse])
def list_support_notes(
    order_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> list[SupportCaseNoteResponse]:
    _require_admin(db, user_id=user_id)
    case = get_relevant_support_case_for_order(db, order_id=order_id)
    if case is None:
        return []
    notes = db.execute(
        select(SupportCaseNote).where(SupportCaseNote.support_case_id == case.id).order_by(SupportCaseNote.created_at.asc())
    ).scalars().all()
    return [_to_note_response(note) for note in notes]


@router.post("/{order_id}/notes", response_model=SupportCaseNoteResponse, status_code=status.HTTP_201_CREATED)
def create_support_note(
    order_id: int,
    payload: SupportNoteCreateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> SupportCaseNoteResponse:
    _require_admin(db, user_id=user_id)
    try:
        note = add_support_case_note(db, order_id=order_id, author_user_id=user_id, body=payload.body)
    except SupportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _to_note_response(note)


@router.patch("/{order_id}/case", response_model=SupportCaseResponse)
def update_support_case(
    order_id: int,
    payload: SupportCasePatchRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
) -> SupportCaseResponse:
    _require_admin(db, user_id=user_id)
    try:
        parsed_status = SupportCaseStatus(payload.status) if payload.status is not None else None
        parsed_priority = SupportCasePriority(payload.priority) if payload.priority is not None else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid case enum value.") from exc

    try:
        case = patch_support_case(
            db,
            order_id=order_id,
            actor_user_id=user_id,
            status=parsed_status,
            priority=parsed_priority,
            assigned_to_user_id=payload.assigned_to_user_id,
            category=payload.category,
        )
    except SupportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return _to_case_response(case)


@router.post("/{order_id}/actions", response_model=SupportActionResponse)
def run_support_action(
    order_id: int,
    payload: SupportActionRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client_ip: str = Depends(request_client_ip),
) -> SupportActionResponse:
    _require_admin(db, user_id=user_id)
    apply_rate_limit(
        scope="admin_support_action",
        key=f"{user_id}:{order_id}:{payload.action_type}:{client_ip}",
        limit=settings.rate_limit_admin_action_count,
        window_seconds=settings.rate_limit_admin_action_window_seconds,
    )
    try:
        result = run_admin_support_action(
            db,
            order_id=order_id,
            actor_user_id=user_id,
            action_type=payload.action_type,
            reason=payload.reason,
            payload=payload.payload,
        )
    except SupportNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SupportConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SupportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return SupportActionResponse(action_type=result.action_type, success=result.success, message=result.message)
