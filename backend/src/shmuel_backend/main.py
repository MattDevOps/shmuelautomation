from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shmuel_backend.cloud_routes import oauth_router, photos_router
from shmuel_backend.config import settings
from shmuel_backend.contacts import router as contacts_router
from shmuel_backend.properties import router as properties_router
from shmuel_backend.public import router as public_router

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
