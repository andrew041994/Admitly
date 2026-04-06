from fastapi import FastAPI

from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.notifications import router as notifications_router
from app.api.organizer_reporting import router as organizer_reporting_router
from app.api.orders import router as orders_router
from app.api.payments import router as payments_router
from app.api.ticket_holds import router as ticket_holds_router
from app.api.tickets import router as tickets_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(health_router)
app.include_router(events_router)
app.include_router(ticket_holds_router)
app.include_router(orders_router)
app.include_router(notifications_router)
app.include_router(payments_router)
app.include_router(tickets_router)
app.include_router(organizer_reporting_router)


@app.get("/health")
def health():
    return {"status": "ok"}
