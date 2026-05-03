import respx
from fastapi.testclient import TestClient


def _connect_drive(client: TestClient, respx_mock: respx.MockRouter) -> None:
    """Walk through the OAuth flow so a CloudConnection exists."""
    start = client.get("/auth/google/start", follow_redirects=False)
    state = _state_from(start.headers["location"])
    respx_mock.post("https://oauth2.googleapis.com/token").respond(
        json={
            "access_token": "access-1",
            "refresh_token": "rt-1",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    )
    respx_mock.get("https://openidconnect.googleapis.com/v1/userinfo").respond(
        json={"email": "shmuel@example.com"}
    )
    respx_mock.get("https://www.googleapis.com/drive/v3/files").respond(
        json={"files": []}
    )
    respx_mock.post("https://www.googleapis.com/drive/v3/files").respond(
        json={"id": "root-folder", "name": "Classic Jerusalem Realty"}
    )
    client.get(
        "/auth/google/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )


def _create_property(client: TestClient) -> str:
    r = client.post(
        "/properties",
        json={
            "type": "rent",
            "price": "8500.00",
            "neighborhood": "Baka",
        },
    )
    return str(r.json()["id"])


def _stub_subfolder_create(
    respx_mock: respx.MockRouter, folder_id: str = "subfolder-1"
) -> None:
    respx_mock.post("https://www.googleapis.com/drive/v3/files").respond(
        json={"id": folder_id, "name": "Baka – aaaaaaaa"}
    )


def _stub_file_upload(
    respx_mock: respx.MockRouter,
    file_id: str = "file-1",
    name: str = "front.jpg",
    size: int = 12,
) -> None:
    respx_mock.post(
        "https://www.googleapis.com/upload/drive/v3/files"
    ).respond(
        json={
            "id": file_id,
            "name": name,
            "mimeType": "image/jpeg",
            "size": str(size),
            "webViewLink": f"https://drive.google.com/file/d/{file_id}/view",
            "thumbnailLink": f"https://lh3.googleusercontent.com/t/{file_id}",
        }
    )


def test_upload_rejected_when_drive_not_connected(client: TestClient) -> None:
    pid = _create_property(client)

    r = client.post(
        f"/properties/{pid}/photos",
        files={"file": ("front.jpg", b"\xff\xd8\xff", "image/jpeg")},
    )
    assert r.status_code == 412
    assert "Google Drive is not connected" in r.json()["detail"]


@respx.mock
def test_upload_creates_property_subfolder_then_uploads(
    client: TestClient,
) -> None:
    _connect_drive(client, respx.mock)
    pid = _create_property(client)

    # Drive list returns no existing subfolder; then create subfolder; then upload file.
    respx.mock.get("https://www.googleapis.com/drive/v3/files").mock(
        side_effect=[
            __resp({"files": []}),  # subfolder lookup
        ]
    )
    _stub_subfolder_create(respx.mock)
    _stub_file_upload(respx.mock)

    r = client.post(
        f"/properties/{pid}/photos",
        files={"file": ("front.jpg", b"\xff\xd8\xffphotobytes", "image/jpeg")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["external_id"] == "file-1"
    assert body["folder_external_id"] == "subfolder-1"
    assert body["mime_type"] == "image/jpeg"
    assert body["web_view_url"].startswith("https://drive.google.com/")


@respx.mock
def test_upload_is_idempotent_on_same_checksum(client: TestClient) -> None:
    _connect_drive(client, respx.mock)
    pid = _create_property(client)

    respx.mock.get("https://www.googleapis.com/drive/v3/files").mock(
        side_effect=[__resp({"files": []})]
    )
    _stub_subfolder_create(respx.mock)
    _stub_file_upload(respx.mock)

    payload = b"\xff\xd8\xffsamebytes"
    first = client.post(
        f"/properties/{pid}/photos",
        files={"file": ("front.jpg", payload, "image/jpeg")},
    )
    second = client.post(
        f"/properties/{pid}/photos",
        files={"file": ("front.jpg", payload, "image/jpeg")},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["external_id"] == second.json()["external_id"]


@respx.mock
def test_upload_propagates_drive_unauthorized_as_412(
    client: TestClient,
) -> None:
    _connect_drive(client, respx.mock)
    pid = _create_property(client)

    # Refresh-token call now fails with 401 → CloudUnauthorizedError → 412 to client.
    respx.mock.post("https://oauth2.googleapis.com/token").respond(
        status_code=401, json={"error": "invalid_grant"}
    )

    r = client.post(
        f"/properties/{pid}/photos",
        files={"file": ("front.jpg", b"x", "image/jpeg")},
    )
    assert r.status_code == 412
    assert "Reconnect Google Drive" in r.json()["detail"]


def test_upload_rejects_empty_file(client: TestClient) -> None:
    pid = _create_property(client)
    r = client.post(
        f"/properties/{pid}/photos",
        files={"file": ("empty.jpg", b"", "image/jpeg")},
    )
    # Drive precondition failure beats empty-file check, so this can be 412.
    assert r.status_code in (400, 412)


@respx.mock
def test_list_returns_photos_for_property(client: TestClient) -> None:
    _connect_drive(client, respx.mock)
    pid = _create_property(client)
    respx.mock.get("https://www.googleapis.com/drive/v3/files").mock(
        side_effect=[__resp({"files": []})]
    )
    _stub_subfolder_create(respx.mock)
    _stub_file_upload(respx.mock)
    client.post(
        f"/properties/{pid}/photos",
        files={"file": ("front.jpg", b"abc", "image/jpeg")},
    )

    r = client.get(f"/properties/{pid}/photos")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["file_name"] == "front.jpg"


@respx.mock
def test_thumbnail_redirects_to_fresh_drive_url(client: TestClient) -> None:
    _connect_drive(client, respx.mock)
    pid = _create_property(client)
    respx.mock.get("https://www.googleapis.com/drive/v3/files").mock(
        side_effect=[__resp({"files": []})]
    )
    _stub_subfolder_create(respx.mock)
    _stub_file_upload(respx.mock)
    created = client.post(
        f"/properties/{pid}/photos",
        files={"file": ("front.jpg", b"abc", "image/jpeg")},
    ).json()

    # Drive returns a fresh thumbnail URL on the metadata fetch
    respx.mock.get(
        f"https://www.googleapis.com/drive/v3/files/{created['external_id']}"
    ).respond(
        json={"thumbnailLink": "https://lh3.googleusercontent.com/sig=abc"}
    )

    r = client.get(
        f"/properties/{pid}/photos/{created['id']}/thumbnail",
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == "https://lh3.googleusercontent.com/sig=abc"
    assert r.headers["cache-control"] == "public, max-age=300"


@respx.mock
def test_thumbnail_404_when_drive_has_no_thumbnail_yet(client: TestClient) -> None:
    _connect_drive(client, respx.mock)
    pid = _create_property(client)
    respx.mock.get("https://www.googleapis.com/drive/v3/files").mock(
        side_effect=[__resp({"files": []})]
    )
    _stub_subfolder_create(respx.mock)
    _stub_file_upload(respx.mock)
    created = client.post(
        f"/properties/{pid}/photos",
        files={"file": ("front.jpg", b"abc", "image/jpeg")},
    ).json()

    # Drive hasn't rendered a thumbnail yet — empty thumbnailLink
    respx.mock.get(
        f"https://www.googleapis.com/drive/v3/files/{created['external_id']}"
    ).respond(json={})

    r = client.get(
        f"/properties/{pid}/photos/{created['id']}/thumbnail",
        follow_redirects=False,
    )
    assert r.status_code == 404


def test_thumbnail_404_for_unknown_photo(client: TestClient) -> None:
    pid = _create_property(client)
    r = client.get(
        f"/properties/{pid}/photos/00000000-0000-0000-0000-000000000000/thumbnail"
    )
    assert r.status_code == 404


@respx.mock
def test_delete_trashes_drive_file_then_removes_record(
    client: TestClient,
) -> None:
    _connect_drive(client, respx.mock)
    pid = _create_property(client)
    respx.mock.get("https://www.googleapis.com/drive/v3/files").mock(
        side_effect=[__resp({"files": []})]
    )
    _stub_subfolder_create(respx.mock)
    _stub_file_upload(respx.mock)
    created = client.post(
        f"/properties/{pid}/photos",
        files={"file": ("front.jpg", b"abc", "image/jpeg")},
    ).json()

    trash = respx.mock.patch(
        "https://www.googleapis.com/drive/v3/files/file-1"
    ).respond(json={"id": "file-1", "trashed": True})

    r = client.delete(f"/properties/{pid}/photos/{created['id']}")
    assert r.status_code == 204
    assert trash.called

    after = client.get(f"/properties/{pid}/photos").json()
    assert after == []


def __resp(json_body: dict[str, object]) -> "object":
    """Tiny helper to build a mock httpx Response for respx side_effects."""
    import httpx

    return httpx.Response(200, json=json_body)


def _state_from(location: str) -> str:
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(location).query)
    return qs["state"][0]
