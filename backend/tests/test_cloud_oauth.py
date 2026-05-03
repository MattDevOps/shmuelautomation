import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.cloud.crypto import decrypt
from shmuel_backend.config import settings
from shmuel_backend.models import CloudConnection


def _stub_token(respx_mock: respx.MockRouter, refresh_token: str = "rt-123") -> None:
    respx_mock.post("https://oauth2.googleapis.com/token").respond(
        json={
            "access_token": "access-abc",
            "refresh_token": refresh_token,
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    )


def _stub_userinfo(respx_mock: respx.MockRouter, email: str = "shmuel@example.com") -> None:
    respx_mock.get("https://openidconnect.googleapis.com/v1/userinfo").respond(
        json={"email": email}
    )


def _stub_root_folder(respx_mock: respx.MockRouter) -> None:
    """Drive sees no existing root folder, then creates one."""
    respx_mock.get("https://www.googleapis.com/drive/v3/files").respond(
        json={"files": []}
    )
    respx_mock.post("https://www.googleapis.com/drive/v3/files").respond(
        json={"id": "root-folder-1", "name": "Classic Jerusalem Realty"}
    )


def test_start_redirects_to_google_with_state(client: TestClient) -> None:
    r = client.get("/auth/google/start", follow_redirects=False)
    assert r.status_code == 307
    location = r.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "state=" in location
    assert "access_type=offline" in location
    assert f"client_id={settings.google_oauth_client_id}" in location


@respx.mock
def test_callback_persists_encrypted_refresh_token_and_root_folder(
    client: TestClient,
) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = _state_from(start.headers["location"])

    _stub_token(respx.mock, refresh_token="rt-secret")
    _stub_userinfo(respx.mock)
    _stub_root_folder(respx.mock)

    r = client.get(
        "/auth/google/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 307
    assert "cloud_connected=1" in r.headers["location"]

    status_r = client.get("/auth/google/status")
    assert status_r.status_code == 200
    body = status_r.json()
    assert body["connected"] is True
    assert body["account_email"] == "shmuel@example.com"
    assert body["root_folder_name"] == "Classic Jerusalem Realty"


@respx.mock
async def test_callback_stores_refresh_token_encrypted_at_rest(
    client: TestClient, session: AsyncSession
) -> None:
    """The DB row holds ciphertext, not the refresh token in plaintext."""
    start = client.get("/auth/google/start", follow_redirects=False)
    state = _state_from(start.headers["location"])

    _stub_token(respx.mock, refresh_token="plain-secret-xyz")
    _stub_userinfo(respx.mock)
    _stub_root_folder(respx.mock)

    client.get(
        "/auth/google/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )

    result = await session.execute(select(CloudConnection))
    conn = result.scalar_one_or_none()
    assert conn is not None
    assert conn.encrypted_refresh_token != "plain-secret-xyz"
    assert decrypt(conn.encrypted_refresh_token) == "plain-secret-xyz"


def test_callback_rejects_unknown_state(client: TestClient) -> None:
    r = client.get(
        "/auth/google/callback",
        params={"code": "x", "state": "never-issued"},
    )
    assert r.status_code == 400


def test_callback_redirects_with_error_when_user_denies(
    client: TestClient,
) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = _state_from(start.headers["location"])

    r = client.get(
        "/auth/google/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert r.status_code == 307
    assert "cloud_error=access_denied" in r.headers["location"]


def test_status_returns_disconnected_initially(client: TestClient) -> None:
    r = client.get("/auth/google/status")
    assert r.status_code == 200
    assert r.json() == {
        "provider": "google_drive",
        "connected": False,
        "account_email": None,
        "root_folder_name": None,
    }


@respx.mock
def test_disconnect_revokes_token_and_clears_connection(
    client: TestClient,
) -> None:
    start = client.get("/auth/google/start", follow_redirects=False)
    state = _state_from(start.headers["location"])
    _stub_token(respx.mock)
    _stub_userinfo(respx.mock)
    _stub_root_folder(respx.mock)
    client.get(
        "/auth/google/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )

    revoke = respx.mock.post("https://oauth2.googleapis.com/revoke").respond(
        status_code=200
    )

    r = client.post("/auth/google/disconnect")
    assert r.status_code == 204
    assert revoke.called

    after = client.get("/auth/google/status").json()
    assert after["connected"] is False


def _state_from(location: str) -> str:
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(location).query)
    return qs["state"][0]
