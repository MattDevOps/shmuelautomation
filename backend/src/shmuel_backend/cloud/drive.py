"""Google Drive REST client (v3).

Talks to Drive over plain HTTP — no google-api-python-client dependency, async-native
via httpx. Each call exchanges the long-lived refresh token for a short-lived access
token, then uses that token for the request. Access tokens are not cached on disk.
"""
import json
import secrets
from urllib.parse import urlencode

import httpx

from shmuel_backend.cloud.storage import (
    CloudFile,
    CloudFolder,
    CloudStorage,
    CloudStorageError,
    CloudUnauthorizedError,
)
from shmuel_backend.config import settings

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

FOLDER_MIME = "application/vnd.google-apps.folder"
FILE_FIELDS = "id, name, mimeType, size, webViewLink, thumbnailLink"
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "openid",
    "email",
]


def authorize_url(state: str) -> str:
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


def random_state() -> str:
    return secrets.token_urlsafe(32)


async def exchange_code(code: str) -> dict[str, str]:
    """Exchange an OAuth authorization code for a refresh token + access token."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            OAUTH_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if r.status_code >= 400:
        raise CloudStorageError(f"OAuth code exchange failed: {r.status_code} {r.text}")
    body = r.json()
    if "refresh_token" not in body:
        raise CloudStorageError(
            "Google did not return a refresh_token. "
            "Revoke the app's access in your Google account and try again."
        )
    return body


async def refresh_access_token(refresh_token: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            OAUTH_TOKEN_URL,
            data={
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if r.status_code in (400, 401):
        raise CloudUnauthorizedError(
            f"Refresh token rejected: {r.status_code} {r.text}"
        )
    if r.status_code >= 400:
        raise CloudStorageError(f"Token refresh failed: {r.status_code} {r.text}")
    return str(r.json()["access_token"])


async def revoke_refresh_token(refresh_token: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(OAUTH_REVOKE_URL, data={"token": refresh_token})


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {access_token}"}


def _raise_if_unauthorized(r: httpx.Response) -> None:
    if r.status_code in (401, 403):
        raise CloudUnauthorizedError(f"Drive rejected request: {r.status_code} {r.text}")
    if r.status_code >= 400:
        raise CloudStorageError(f"Drive request failed: {r.status_code} {r.text}")


def _to_folder(payload: dict[str, object]) -> CloudFolder:
    return CloudFolder(
        id=str(payload["id"]),
        name=str(payload.get("name") or ""),
        web_view_url=payload.get("webViewLink") if payload.get("webViewLink") else None,  # type: ignore[arg-type]
    )


def _to_file(payload: dict[str, object]) -> CloudFile:
    size_raw = payload.get("size") or "0"
    return CloudFile(
        id=str(payload["id"]),
        name=str(payload.get("name") or ""),
        mime_type=str(payload.get("mimeType") or "application/octet-stream"),
        size_bytes=int(size_raw),
        web_view_url=payload.get("webViewLink") if payload.get("webViewLink") else None,  # type: ignore[arg-type]
        thumbnail_url=payload.get("thumbnailLink") if payload.get("thumbnailLink") else None,  # type: ignore[arg-type]
    )


class GoogleDriveStorage(CloudStorage):
    provider_name = "google_drive"

    async def get_account_email(self, refresh_token: str) -> str | None:
        access = await refresh_access_token(refresh_token)
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(USERINFO_URL, headers=_auth_headers(access))
        _raise_if_unauthorized(r)
        return str(r.json().get("email")) if r.json().get("email") else None

    async def ensure_root_folder(
        self, refresh_token: str, name: str
    ) -> CloudFolder:
        return await self._find_or_create_folder(refresh_token, parent_id=None, name=name)

    async def ensure_subfolder(
        self, refresh_token: str, parent_id: str, name: str
    ) -> CloudFolder:
        return await self._find_or_create_folder(
            refresh_token, parent_id=parent_id, name=name
        )

    async def _find_or_create_folder(
        self, refresh_token: str, parent_id: str | None, name: str
    ) -> CloudFolder:
        access = await refresh_access_token(refresh_token)
        existing = await self._find_folder(access, parent_id, name)
        if existing is not None:
            return existing
        return await self._create_folder(access, parent_id, name)

    async def _find_folder(
        self, access_token: str, parent_id: str | None, name: str
    ) -> CloudFolder | None:
        escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        q_parts = [
            f"mimeType = '{FOLDER_MIME}'",
            f"name = '{escaped}'",
            "trashed = false",
        ]
        if parent_id is not None:
            q_parts.append(f"'{parent_id}' in parents")
        params = {
            "q": " and ".join(q_parts),
            "fields": f"files({FILE_FIELDS})",
            "spaces": "drive",
            "pageSize": "1",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{DRIVE_API}/files",
                headers=_auth_headers(access_token),
                params=params,
            )
        _raise_if_unauthorized(r)
        files = r.json().get("files") or []
        return _to_folder(files[0]) if files else None

    async def _create_folder(
        self, access_token: str, parent_id: str | None, name: str
    ) -> CloudFolder:
        body: dict[str, object] = {"name": name, "mimeType": FOLDER_MIME}
        if parent_id is not None:
            body["parents"] = [parent_id]
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{DRIVE_API}/files",
                headers={**_auth_headers(access_token), "content-type": "application/json"},
                params={"fields": FILE_FIELDS},
                content=json.dumps(body),
            )
        _raise_if_unauthorized(r)
        return _to_folder(r.json())

    async def upload_file(
        self,
        refresh_token: str,
        folder_id: str,
        file_name: str,
        content: bytes,
        mime_type: str,
    ) -> CloudFile:
        """Multipart upload — fine for property photos (typically < 10 MB).

        For files larger than ~50 MB, switch to resumable upload via the
        `uploadType=resumable` Drive endpoint. Out of scope for Phase 1.
        """
        access = await refresh_access_token(refresh_token)
        boundary = secrets.token_hex(16)
        metadata = json.dumps(
            {"name": file_name, "parents": [folder_id], "mimeType": mime_type}
        )
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{metadata}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--".encode()

        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{DRIVE_UPLOAD_API}/files",
                headers={
                    **_auth_headers(access),
                    "content-type": f"multipart/related; boundary={boundary}",
                },
                params={"uploadType": "multipart", "fields": FILE_FIELDS},
                content=body,
            )
        _raise_if_unauthorized(r)
        return _to_file(r.json())

    async def get_thumbnail_url(
        self, refresh_token: str, file_id: str
    ) -> str | None:
        access = await refresh_access_token(refresh_token)
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{DRIVE_API}/files/{file_id}",
                headers=_auth_headers(access),
                params={"fields": "thumbnailLink"},
            )
        _raise_if_unauthorized(r)
        link = r.json().get("thumbnailLink")
        return str(link) if link else None

    async def download_file(self, refresh_token: str, file_id: str) -> bytes:
        access = await refresh_access_token(refresh_token)
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(
                f"{DRIVE_API}/files/{file_id}",
                headers=_auth_headers(access),
                params={"alt": "media"},
            )
        _raise_if_unauthorized(r)
        if r.status_code >= 400:
            raise CloudStorageError(
                f"drive download failed ({r.status_code}) for {file_id}"
            )
        return r.content

    async def trash_file(self, refresh_token: str, file_id: str) -> None:
        access = await refresh_access_token(refresh_token)
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.patch(
                f"{DRIVE_API}/files/{file_id}",
                headers={**_auth_headers(access), "content-type": "application/json"},
                content=json.dumps({"trashed": True}),
            )
        _raise_if_unauthorized(r)
