"""OAuth + photo-management HTTP endpoints.

Two routers exported:
- `oauth_router` mounted at `/auth/google` — start, callback, status, disconnect
- `photos_router` mounted at `/properties` — nested photo CRUD per property

Both share the same `GoogleDriveStorage` singleton; the storage layer is stateless
across calls and just needs a refresh token, so reuse is safe.
"""
import contextlib
import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlparse

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.cloud import drive
from shmuel_backend.cloud.crypto import decrypt, encrypt
from shmuel_backend.cloud.drive import GoogleDriveStorage
from shmuel_backend.cloud.storage import (
    CloudStorageError,
    CloudUnauthorizedError,
)
from shmuel_backend.config import settings
from shmuel_backend.db import get_session
from shmuel_backend.models import (
    CloudConnection,
    CloudPhoto,
    OAuthState,
    Property,
)
from shmuel_backend.schemas import (
    CloudConnectionStatus,
    CloudPhotoRead,
    PhotoUrlImportRequest,
    PhotoUrlImportResult,
)

PROVIDER_GOOGLE = "google_drive"
ROOT_FOLDER_NAME = "Classic Jerusalem Realty"
OAUTH_STATE_TTL = timedelta(minutes=10)
# Cap a single downloaded image so a hostile/huge URL can't exhaust memory.
MAX_REMOTE_IMAGE_BYTES = 15 * 1024 * 1024
REMOTE_IMAGE_TIMEOUT = 20.0
# The only host the URL-import endpoint will fetch from (SSRF guard).
ALLOWED_IMAGE_HOST = "yad2.co.il"

storage = GoogleDriveStorage()

oauth_router = APIRouter(prefix="/auth/google", tags=["auth"])
photos_router = APIRouter(prefix="/properties", tags=["photos"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _get_connection(session: AsyncSession) -> CloudConnection | None:
    result = await session.execute(
        select(CloudConnection).where(CloudConnection.provider == PROVIDER_GOOGLE)
    )
    return result.scalar_one_or_none()


async def _require_connection(session: AsyncSession) -> CloudConnection:
    conn = await _get_connection(session)
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=(
                "Google Drive is not connected. Connect it in Settings before "
                "uploading photos."
            ),
        )
    return conn


@oauth_router.get("/start")
async def start_oauth(session: SessionDep) -> RedirectResponse:
    state = drive.random_state()
    session.add(OAuthState(state=state, provider=PROVIDER_GOOGLE))
    await session.commit()
    return RedirectResponse(drive.authorize_url(state))


@oauth_router.get("/callback")
async def oauth_callback(
    session: SessionDep,
    state: str,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Receives the redirect from Google. State + code → refresh token in DB."""
    result = await session.execute(
        select(OAuthState).where(OAuthState.state == state)
    )
    pending = result.scalar_one_or_none()
    if pending is None or pending.provider != PROVIDER_GOOGLE:
        raise HTTPException(status_code=400, detail="Unknown OAuth state.")

    age = datetime.now(UTC) - pending.created_at.replace(tzinfo=UTC)
    await session.delete(pending)
    if age > OAUTH_STATE_TTL:
        await session.commit()
        raise HTTPException(status_code=400, detail="OAuth state expired; try again.")

    if error:
        await session.commit()
        return RedirectResponse(
            f"{settings.admin_redirect_uri}?cloud_error={error}"
        )
    if code is None:
        await session.commit()
        raise HTTPException(status_code=400, detail="Missing authorization code.")

    try:
        token_response = await drive.exchange_code(code)
    except CloudStorageError as exc:
        await session.commit()
        return RedirectResponse(
            f"{settings.admin_redirect_uri}?cloud_error={exc}"
        )

    refresh_token = token_response["refresh_token"]
    encrypted = encrypt(refresh_token)
    account_email: str | None = None
    with contextlib.suppress(CloudStorageError):
        account_email = await storage.get_account_email(refresh_token)

    root = await storage.ensure_root_folder(refresh_token, ROOT_FOLDER_NAME)

    existing = await _get_connection(session)
    if existing is None:
        session.add(
            CloudConnection(
                provider=PROVIDER_GOOGLE,
                account_email=account_email,
                encrypted_refresh_token=encrypted,
                root_folder_id=root.id,
                root_folder_name=root.name,
            )
        )
    else:
        existing.encrypted_refresh_token = encrypted
        existing.account_email = account_email
        existing.root_folder_id = root.id
        existing.root_folder_name = root.name

    await session.commit()
    return RedirectResponse(f"{settings.admin_redirect_uri}?cloud_connected=1")


@oauth_router.get("/status", response_model=CloudConnectionStatus)
async def oauth_status(session: SessionDep) -> CloudConnectionStatus:
    conn = await _get_connection(session)
    if conn is None:
        return CloudConnectionStatus(provider=PROVIDER_GOOGLE, connected=False)
    return CloudConnectionStatus(
        provider=PROVIDER_GOOGLE,
        connected=True,
        account_email=conn.account_email,
        root_folder_name=conn.root_folder_name,
    )


@oauth_router.post("/disconnect", status_code=204)
async def oauth_disconnect(session: SessionDep) -> Response:
    conn = await _get_connection(session)
    if conn is not None:
        with contextlib.suppress(CloudStorageError):
            await drive.revoke_refresh_token(decrypt(conn.encrypted_refresh_token))
        await session.delete(conn)
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _property_folder_name(p: Property) -> str:
    """Build the Drive folder name for a property.

    Format: "{Rent|Sale} — {neighborhood or address or 'Property'} ({short-id})"
    Example: "Rent — Baka (4893a584)" or "Sale — Old Katamon (09e51041)"

    The short UUID makes the folder unambiguous (two Bakas don't collide). The
    type + location prefix makes folders scannable in the Drive UI.
    """
    from shmuel_backend.enums import PropertyType

    short_id = str(p.id)[:8]
    type_label = "Rent" if p.type == PropertyType.RENT else "Sale"
    location = p.neighborhood or p.address or "Property"
    return f"{type_label} — {location} ({short_id})"


@photos_router.get("/{property_id}/photos", response_model=list[CloudPhotoRead])
async def list_photos(property_id: uuid.UUID, session: SessionDep) -> list[CloudPhoto]:
    result = await session.execute(
        select(CloudPhoto)
        .where(CloudPhoto.property_id == property_id)
        .order_by(CloudPhoto.created_at.desc())
    )
    return list(result.scalars().all())


@photos_router.post(
    "/{property_id}/photos",
    response_model=CloudPhotoRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_photo(
    property_id: uuid.UUID,
    session: SessionDep,
    file: UploadFile,
) -> CloudPhoto:
    prop = await session.get(Property, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="property not found")

    conn = await _require_connection(session)
    if conn.root_folder_id is None:
        raise HTTPException(
            status_code=500,
            detail="Cloud connection has no root folder; reconnect Drive.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file.")

    try:
        photo, _ = await _store_photo_bytes(
            session,
            prop,
            conn,
            file.filename or "photo.jpg",
            content,
            file.content_type or "application/octet-stream",
        )
    except CloudUnauthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=(
                "Drive credentials are no longer valid. Reconnect Google Drive "
                f"in Settings ({exc})."
            ),
        ) from exc
    except CloudStorageError as exc:
        raise HTTPException(status_code=502, detail=f"Drive upload failed: {exc}") from exc

    await session.commit()
    await session.refresh(photo)
    return photo


async def _store_photo_bytes(
    session: AsyncSession,
    prop: Property,
    conn: CloudConnection,
    filename: str,
    content: bytes,
    content_type: str,
) -> tuple[CloudPhoto, bool]:
    """Persist one image to Drive + DB, deduped by checksum.

    Does NOT commit — the caller decides the transaction boundary so a batch
    import can roll up many photos into one commit. Returns `(photo, created)`;
    `created` is False when the same bytes were already stored for this property
    (idempotent). Raises CloudStorageError / CloudUnauthorizedError on Drive
    failures.
    """
    checksum = hashlib.sha256(content).hexdigest()
    existing = await session.execute(
        select(CloudPhoto).where(
            CloudPhoto.property_id == prop.id, CloudPhoto.checksum == checksum
        )
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        return found, False

    refresh_token = decrypt(conn.encrypted_refresh_token)
    folder = await storage.ensure_subfolder(
        refresh_token, conn.root_folder_id, _property_folder_name(prop)
    )
    uploaded = await storage.upload_file(
        refresh_token,
        folder.id,
        filename,
        content,
        content_type or "application/octet-stream",
    )
    photo = CloudPhoto(
        property_id=prop.id,
        provider=PROVIDER_GOOGLE,
        external_id=uploaded.id,
        folder_external_id=folder.id,
        file_name=uploaded.name,
        mime_type=uploaded.mime_type,
        size_bytes=uploaded.size_bytes,
        checksum=checksum,
        web_view_url=uploaded.web_view_url,
        thumbnail_url=uploaded.thumbnail_url,
    )
    session.add(photo)
    return photo, True


def _filename_from_url(url: str, index: int) -> str:
    """Derive a sensible filename from an image URL, defaulting to a jpg."""
    name = os.path.basename(urlparse(url).path)
    if name and "." in name:
        return name
    return f"photo-{index + 1}.jpg"


def _validate_remote_image_url(url: str) -> None:
    """Reject anything but an https Yad2-CDN URL.

    This endpoint fetches its argument server-side, so an unrestricted URL is an
    SSRF hole — on Cloud Run it could reach the metadata server or internal
    services. The only legitimate caller imports the Yad2 gallery, whose images
    live under yad2.co.il, so we hard-limit to that host over https.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("only https image URLs are allowed")
    host = (parsed.hostname or "").lower()
    if host != ALLOWED_IMAGE_HOST and not host.endswith("." + ALLOWED_IMAGE_HOST):
        raise ValueError(f"host not allowed ({host or 'none'})")


async def _download_remote_image(
    http: httpx.AsyncClient, url: str
) -> tuple[bytes, str]:
    """Stream-download an image, aborting past the size cap instead of buffering.

    Reads in chunks so an oversized (or unbounded) body is rejected mid-flight
    rather than fully materialized in memory first.
    """
    async with http.stream("GET", url) as resp:
        resp.raise_for_status()
        declared = resp.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_REMOTE_IMAGE_BYTES:
            raise ValueError("image exceeds size limit")
        content_type = (
            resp.headers.get("content-type", "").split(";")[0].strip()
            or "image/jpeg"
        )
        if not content_type.startswith("image/"):
            raise ValueError(f"not an image ({content_type or 'unknown'})")
        buf = bytearray()
        async for chunk in resp.aiter_bytes():
            buf.extend(chunk)
            if len(buf) > MAX_REMOTE_IMAGE_BYTES:
                raise ValueError("image exceeds size limit")
    if not buf:
        raise ValueError("empty response")
    return bytes(buf), content_type


@photos_router.post(
    "/{property_id}/photos/import-urls",
    response_model=PhotoUrlImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def import_photos_from_urls(
    property_id: uuid.UUID,
    payload: PhotoUrlImportRequest,
    session: SessionDep,
) -> PhotoUrlImportResult:
    """Download remote images (e.g. a Yad2 gallery) and store them in Drive.

    Used by the Yad2 import flow: the listing's photo URLs live on
    img.yad2.co.il, which the browser can't fetch cross-origin, so the download
    happens here. Best-effort per image — one bad URL doesn't fail the batch.
    Deduped by checksum, so re-running is a no-op for already-stored photos.
    """
    prop = await session.get(Property, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="property not found")

    conn = await _require_connection(session)
    if conn.root_folder_id is None:
        raise HTTPException(
            status_code=500,
            detail="Cloud connection has no root folder; reconnect Drive.",
        )

    imported = 0
    skipped = 0
    # Snapshot each stored photo as a DTO in-loop: a later image's rollback
    # expires the ORM objects, so we can't safely read them after the loop.
    photos: list[CloudPhotoRead] = []
    errors: list[str] = []

    # follow_redirects=False: a redirect is a classic allowlist-bypass vector
    # (a yad2 URL 302-ing to an internal host), and the CDN serves images
    # directly, so we never need to follow one.
    async with httpx.AsyncClient(
        timeout=REMOTE_IMAGE_TIMEOUT, follow_redirects=False
    ) as http:
        for index, url in enumerate(payload.image_urls):
            try:
                _validate_remote_image_url(url)
                content, content_type = await _download_remote_image(http, url)
                photo, created = await _store_photo_bytes(
                    session,
                    prop,
                    conn,
                    _filename_from_url(url, index),
                    content,
                    content_type,
                )
                if created:
                    # Commit per image so a later failure can't roll back (and
                    # orphan the Drive files of) photos already stored.
                    await session.commit()
                    await session.refresh(photo)
                    photos.append(
                        CloudPhotoRead.model_validate(photo, from_attributes=True)
                    )
                    imported += 1
                else:
                    skipped += 1
            except CloudUnauthorizedError as exc:
                # Auth is broken for the whole batch — stop and surface it.
                # Already-committed photos survive; only this image is dropped.
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_412_PRECONDITION_FAILED,
                    detail=(
                        "Drive credentials are no longer valid. Reconnect Google "
                        f"Drive in Settings ({exc})."
                    ),
                ) from exc
            except (httpx.HTTPError, CloudStorageError, ValueError) as exc:
                await session.rollback()
                errors.append(f"{url}: {exc}")

    return PhotoUrlImportResult(
        imported=imported,
        skipped=skipped,
        failed=len(errors),
        photos=photos,
        errors=errors,
    )


@photos_router.get("/{property_id}/photos/{photo_id}/thumbnail")
async def photo_thumbnail(
    property_id: uuid.UUID, photo_id: uuid.UUID, session: SessionDep
) -> Response:
    """Resolve a fresh signed thumbnail URL for a photo, then 302 the browser
    there. Drive's thumbnailLink expires on the order of hours, so we fetch a
    fresh one on every request rather than caching it."""
    photo = await session.get(CloudPhoto, photo_id)
    if photo is None or photo.property_id != property_id:
        raise HTTPException(status_code=404, detail="photo not found")

    conn = await _require_connection(session)
    try:
        url = await storage.get_thumbnail_url(
            decrypt(conn.encrypted_refresh_token), photo.external_id
        )
    except CloudUnauthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=f"Drive credentials no longer valid ({exc}).",
        ) from exc
    except CloudStorageError:
        url = None

    if not url:
        # Drive hasn't generated a thumbnail yet — common just after upload.
        # 404 lets the frontend's onError fall back to the filename tile.
        raise HTTPException(status_code=404, detail="thumbnail not ready")

    return Response(
        status_code=302,
        headers={"location": url, "cache-control": "public, max-age=300"},
    )


@photos_router.delete(
    "/{property_id}/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_photo(
    property_id: uuid.UUID, photo_id: uuid.UUID, session: SessionDep
) -> Response:
    photo = await session.get(CloudPhoto, photo_id)
    if photo is None or photo.property_id != property_id:
        raise HTTPException(status_code=404, detail="photo not found")

    conn = await _get_connection(session)
    if conn is not None:
        with contextlib.suppress(CloudStorageError):
            await storage.trash_file(
                decrypt(conn.encrypted_refresh_token), photo.external_id
            )

    await session.delete(photo)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
