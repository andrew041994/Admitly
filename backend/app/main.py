from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.orders import router as orders_router
from app.api.ticket_holds import router as ticket_holds_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(health_router)
app.include_router(ticket_holds_router)
app.include_router(orders_router)


@app.get("/health")
def health():
    return {"status": "ok"}
