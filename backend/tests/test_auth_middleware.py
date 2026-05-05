"""Tests for the X-API-Key middleware on top of FastAPI.

Defense-in-depth check on top of the Cloudflare Worker. The Worker
handles SPA traffic; this middleware blocks anyone hitting the
underlying .run.app URL directly without the header.
"""
import pytest
from fastapi.testclient import TestClient

from shmuel_backend.config import settings
from shmuel_backend.main import app


@pytest.fixture
def with_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Enable the gate with a known key for the duration of the test."""
    key = "test-secret-key-do-not-use-in-prod"
    monkeypatch.setattr(settings, "backend_api_key", key)
    return key


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_no_key_configured_means_open_access(client: TestClient) -> None:
    """Empty BACKEND_API_KEY (the dev/CI default) skips the gate so
    local work and the existing test suite stay painless."""
    # backend_api_key is empty by default in the test settings fixture
    r = client.get("/properties")
    assert r.status_code == 200


def test_health_bypasses_gate_even_when_configured(
    client: TestClient, with_key: str
) -> None:
    """Cloud Run + uptime probes hit /health without ever knowing the key."""
    r = client.get("/health")
    # 200 from the readiness probe, or 503 if the in-memory DB happens
    # to be unhappy — but never 401, that's the contract.
    assert r.status_code != 401


def test_healthz_bypasses_gate(client: TestClient, with_key: str) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200


def test_public_path_bypasses_gate(
    client: TestClient, with_key: str
) -> None:
    """The WP plugin hits /public/properties without a key — it shouldn't
    need one for read-only public data."""
    r = client.get("/public/properties")
    assert r.status_code == 200


def test_oauth_path_bypasses_gate(
    client: TestClient, with_key: str
) -> None:
    """OAuth callbacks come from Google's IPs and don't carry our key.
    The /auth/google/* prefix has its own validation downstream."""
    # /auth/google/start should redirect to Google, not 401-out.
    r = client.get("/auth/google/start", follow_redirects=False)
    assert r.status_code != 401


def test_admin_route_blocked_without_key(
    client: TestClient, with_key: str
) -> None:
    r = client.get("/properties")
    assert r.status_code == 401
    assert r.json() == {"detail": "Unauthorized"}


def test_admin_route_blocked_with_wrong_key(
    client: TestClient, with_key: str
) -> None:
    r = client.get("/properties", headers={"x-api-key": "wrong"})
    assert r.status_code == 401


def test_admin_route_allowed_with_correct_key(
    client: TestClient, with_key: str
) -> None:
    r = client.get("/properties", headers={"x-api-key": with_key})
    assert r.status_code == 200


def test_options_preflight_bypasses_gate(
    client: TestClient, with_key: str
) -> None:
    """CORS preflights don't carry custom headers; the middleware must
    let them through so CORSMiddleware can answer them. Otherwise the
    SPA gets a generic NetworkError on every fetch."""
    r = client.options(
        "/properties",
        headers={
            "Origin": "https://admin.classicjerusalem.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key, content-type",
        },
    )
    assert r.status_code != 401
