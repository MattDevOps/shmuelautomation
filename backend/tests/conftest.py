from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shmuel_backend.config import settings
from shmuel_backend.db import Base, get_session
from shmuel_backend.main import app


@pytest.fixture(autouse=True)
def _cloud_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide test-only OAuth and encryption settings for every test.

    Also clears third-party API keys by default so tests don't accidentally
    inherit a developer's local .env (e.g. RESEND_API_KEY=re_...) and start
    making real HTTP calls or fail "no-op" assertions. Tests that need a
    specific key set opt in via a fixture (with_resend_key, etc.).
    """
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "google_oauth_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "test-secret")
    monkeypatch.setattr(
        settings,
        "google_oauth_redirect_uri",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setattr(
        settings, "admin_redirect_uri", "http://localhost:5173/settings"
    )
    # Third-party integrations default to unconfigured under tests.
    monkeypatch.setattr(settings, "resend_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "whatsapp_daemon_url", "")
    monkeypatch.setattr(settings, "whatsapp_daemon_token", "")


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as s:
        yield s

    await engine.dispose()


@pytest.fixture
def client(session: AsyncSession) -> Iterator[TestClient]:
    async def override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
