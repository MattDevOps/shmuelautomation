"""OAuth + photo-management HTTP endpoints.

Two routers exported:
- `oauth_router` mounted at `/auth/google` — start, callback, status, disconnect
- `photos_router` mounted at `/properties` — nested photo CRUD per property

Both share the same `GoogleDriveStorage` singleton; the storage layer is stateless
across calls and just needs a refresh token, so reuse is safe.
"""
import contextlib
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

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
from shmuel_backend.schemas import CloudConnectionStatus, CloudPhotoRead

PROVIDER_GOOGLE = "google_drive"
ROOT_FOLDER_NAME = "Classic Jerusalem Realty"
OAUTH_STATE_TTL = timedelta(minutes=10)

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
    short_id = str(p.id)[:8]
    base = p.neighborhood or p.address or "Property"
    return f"{base} – {short_id}"


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
    checksum = hashlib.sha256(content).hexdigest()

    existing = await session.execute(
        select(CloudPhoto).where(
            CloudPhoto.property_id == property_id, CloudPhoto.checksum == checksum
        )
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        return found

    refresh_token = decrypt(conn.encrypted_refresh_token)
    try:
        folder = await storage.ensure_subfolder(
            refresh_token, conn.root_folder_id, _property_folder_name(prop)
        )
        uploaded = await storage.upload_file(
            refresh_token,
            folder.id,
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

    photo = CloudPhoto(
        property_id=property_id,
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
    await session.commit()
    await session.refresh(photo)
    return photo


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
