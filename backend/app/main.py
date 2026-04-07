from fastapi import FastAPI

from app.api.admin_support import router as admin_support_router
from app.api.admin_finance import router as admin_finance_router
from app.api.auth import router as auth_router
from app.api.account import router as account_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.messaging import router as messaging_router
from app.api.internal_finance import router as internal_finance_router
from app.api.integrations import router as integrations_router, public_router as public_integrations_router
from app.api.notifications import router as notifications_router
from app.api.organizer_reporting import router as organizer_reporting_router
from app.api.organizer_promos import router as organizer_promos_router
from app.api.orders import router as orders_router
from app.api.payments import router as payments_router
from app.api.refunds import router as refunds_router
from app.api.ticket_holds import router as ticket_holds_router
from app.api.tickets import router as tickets_router
from app.api.ticket_transfer_invites import router as ticket_transfer_invites_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(health_router)
app.include_router(events_router)
app.include_router(ticket_holds_router)
app.include_router(orders_router)
app.include_router(notifications_router)
app.include_router(messaging_router)
app.include_router(payments_router)
app.include_router(refunds_router)
app.include_router(tickets_router)
app.include_router(ticket_transfer_invites_router)
app.include_router(organizer_reporting_router)
app.include_router(organizer_promos_router)
app.include_router(internal_finance_router)
app.include_router(admin_support_router)
app.include_router(admin_finance_router)
app.include_router(auth_router)
app.include_router(account_router)


@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(integrations_router)
app.include_router(public_integrations_router)
