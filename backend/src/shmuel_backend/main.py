import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.cloud_routes import oauth_router, photos_router
from shmuel_backend.config import settings
from shmuel_backend.contacts import router as contacts_router
from shmuel_backend.db import get_session
from shmuel_backend.groups import router as groups_router
from shmuel_backend.logging_config import configure_logging
from shmuel_backend.properties import router as properties_router
from shmuel_backend.public import router as public_router
from shmuel_backend.queue_routes import compose_router
from shmuel_backend.queue_routes import router as queue_router

configure_logging(settings.environment)
log = logging.getLogger(__name__)

app = FastAPI(title="Shmuel Realty Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(properties_router)
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
