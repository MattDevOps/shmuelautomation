import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.cloud_routes import oauth_router, photos_router
from shmuel_backend.config import settings
from shmuel_backend.contacts import router as contacts_router
from shmuel_backend.db import get_session
from shmuel_backend.enums import PostSlotStatus, PropertyStatus
from shmuel_backend.groups import router as groups_router
from shmuel_backend.logging_config import configure_logging
from shmuel_backend.models import (
    CloudConnection,
    Contact,
    Group,
    PostSlot,
    Property,
)
from shmuel_backend.properties import router as properties_router
from shmuel_backend.property_notes import router as property_notes_router
from shmuel_backend.public import router as public_router
from shmuel_backend.queue_routes import compose_router
from shmuel_backend.queue_routes import router as queue_router
from shmuel_backend.schemas import SystemStatus
from shmuel_backend.sentry import configure_sentry

configure_logging(settings.environment)
configure_sentry()
log = logging.getLogger(__name__)

app = FastAPI(title="Shmuel Realty Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public-prefix paths that bypass the API key check. Match the
# api-proxy Worker's bypass list so the two layers stay aligned.
_AUTH_BYPASS_PREFIXES = ("/public/", "/auth/google/", "/health", "/healthz")


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """Defense-in-depth on top of the Cloudflare Worker gate. The Worker
    handles browser/SPA traffic, but the underlying .run.app URL is
    publicly reachable. This middleware blocks anyone hitting the origin
    directly without the X-API-Key header.

    Empty BACKEND_API_KEY skips the check — keeps local dev painless.
    OPTIONS preflights bypass so CORSMiddleware can answer them; preflight
    requests don't carry custom headers like X-API-Key.
    """
    if not settings.backend_api_key:
        return await call_next(request)
    if request.method == "OPTIONS":
        return await call_next(request)
    if any(request.url.path.startswith(p) for p in _AUTH_BYPASS_PREFIXES):
        return await call_next(request)
    if request.headers.get("x-api-key") != settings.backend_api_key:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)

app.include_router(properties_router)
app.include_router(property_notes_router)
app.include_router(photos_router)
app.include_router(oauth_router)
app.include_router(public_router)
app.include_router(contacts_router)
app.include_router(queue_router)
app.include_router(compose_router)
app.include_router(groups_router)


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@app.get("/healthz")
def liveness() -> dict[str, str]:
    """Plain liveness — returns immediately. For cheap uptime checks."""
    return {"status": "ok"}


@app.get("/health")
async def readiness(
    session: SessionDep, response: Response
) -> dict[str, str]:
    """Readiness — pings the DB. Cloud Run uses this to decide if a new
    container should receive traffic. Returns 503 if the DB is unreachable
    so the container is excluded from rotation."""
    try:
        result = await session.execute(text("SELECT 1"))
        result.scalar_one()
        return {
            "status": "ok",
            "environment": settings.environment,
            "db": "ok",
        }
    except Exception as exc:
        log.warning("health check failed: %s", exc, exc_info=True)
        response.status_code = 503
        return {
            "status": "degraded",
            "environment": settings.environment,
            "db": "unreachable",
        }


@app.get("/system", response_model=SystemStatus)
async def system_status(session: SessionDep) -> SystemStatus:
    """Aggregate dashboard data for the admin /system page.

    Cheap to compute. No secrets in the response."""
    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    drive_conn = (
        await session.execute(
            select(CloudConnection).where(
                CloudConnection.provider == "google_drive"
            )
        )
    ).scalar_one_or_none()

    pending_total = (
        await session.execute(
            select(func.count())
            .select_from(PostSlot)
            .where(PostSlot.status == PostSlotStatus.PENDING)
        )
    ).scalar_one()

    due_now = (
        await session.execute(
            select(func.count())
            .select_from(PostSlot)
            .where(
                PostSlot.status == PostSlotStatus.PENDING,
                PostSlot.scheduled_for <= datetime.now(UTC).replace(tzinfo=None),
            )
        )
    ).scalar_one()

    properties_available = (
        await session.execute(
            select(func.count())
            .select_from(Property)
            .where(Property.status == PropertyStatus.AVAILABLE)
        )
    ).scalar_one()
    properties_total = (
        await session.execute(select(func.count()).select_from(Property))
    ).scalar_one()
    contacts_count = (
        await session.execute(select(func.count()).select_from(Contact))
    ).scalar_one()
    groups_active = (
        await session.execute(
            select(func.count())
            .select_from(Group)
            .where(Group.active.is_(True))
        )
    ).scalar_one()

    return SystemStatus(
        environment=settings.environment,
        db_ok=db_ok,
        drive_connected=drive_conn is not None,
        drive_account_email=drive_conn.account_email if drive_conn else None,
        queue_pending_count=int(pending_total),
        queue_due_now_count=int(due_now),
        properties_available=int(properties_available),
        properties_total=int(properties_total),
        contacts_count=int(contacts_count),
        groups_active=int(groups_active),
    )
