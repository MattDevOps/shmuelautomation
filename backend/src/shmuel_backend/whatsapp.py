"""WhatsApp routes — three audiences in one module.

1. **Admin** (`/whatsapp/*` — admin UI): connection status, current pairing QR,
   list of groups the daemon can see, force-reset.
2. **Daemon** (`/whatsapp/session/blob`): the Node daemon PUTs its serialized
   Baileys auth blob here on every state change and GETs it on boot. Auth
   is the shared `X-Daemon-Token` header.
3. **Daemon webhook** (`/webhooks/whatsapp/inbound`): the daemon POSTs every
   inbound WhatsApp message here for storage. Same shared token.

The X-API-Key middleware in `main.py` still applies — the daemon sends both
its API key and its daemon token. The token dependency below is the
extra "this is the daemon, not just any authenticated client" check that
gatekeeps session-blob writes and inbound message ingestion.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend import whatsapp_client
from shmuel_backend.config import settings
from shmuel_backend.db import get_session
from shmuel_backend.models import WhatsappMessage, WhatsappSession

# --- Auth dependency -------------------------------------------------

def require_daemon_token(
    x_daemon_token: Annotated[str | None, Header(alias="X-Daemon-Token")] = None,
) -> None:
    """Require the daemon's shared secret on daemon-facing routes.

    Empty `whatsapp_daemon_token` in settings skips the check — keeps
    local dev painless for routes that don't yet have a real daemon.
    """
    expected = settings.whatsapp_daemon_token
    if not expected:
        return
    if x_daemon_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid daemon token",
        )


# --- Schemas ---------------------------------------------------------

class WhatsappStatus(BaseModel):
    configured: bool
    connection_state: str | None = None
    paired_phone: str | None = None
    last_connected_at: str | None = None
    last_disconnect_reason: str | None = None
    reachable: bool = False


class SessionBlob(BaseModel):
    blob: str


class InboundMessage(BaseModel):
    messageId: str | None = None
    fromJid: str
    fromPhone: str | None = None
    fromName: str | None = None
    chatJid: str
    isGroup: bool = False
    groupId: str | None = None
    groupName: str | None = None
    text: str | None = None
    mediaType: str | None = None
    timestamp: int


# --- Admin router (X-API-Key, no daemon token) -----------------------

admin_router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@admin_router.get("/status", response_model=WhatsappStatus)
async def get_status() -> WhatsappStatus:
    """Connection snapshot from the daemon.

    `configured=false` means the env vars aren't set yet — the admin UI
    should show a "deploy the daemon" hint instead of "Connected".
    """
    if not settings.whatsapp_daemon_url or not settings.whatsapp_daemon_token:
        return WhatsappStatus(configured=False)
    snap = await whatsapp_client.check_status()
    if snap is None:
        return WhatsappStatus(configured=True, reachable=False)
    return WhatsappStatus(
        configured=True,
        reachable=True,
        connection_state=snap.get("state"),
        paired_phone=snap.get("phone"),
        last_connected_at=snap.get("lastConnectedAt"),
        last_disconnect_reason=snap.get("lastDisconnectReason"),
    )


@admin_router.get("/qr")
async def get_qr() -> dict[str, Any]:
    """Current pairing QR as a PNG data URL.

    `{qrPng: null}` if already connected or no QR is ready yet — admin
    UI polls this until a QR appears, then shows it for scanning.
    """
    png = await whatsapp_client.get_qr_png()
    return {"qrPng": png}


@admin_router.get("/groups")
async def get_groups() -> dict[str, Any]:
    groups = await whatsapp_client.list_groups()
    return {"groups": groups or []}


@admin_router.post("/reset")
async def reset_session() -> dict[str, Any]:
    """Wipe the daemon's auth and force a re-pair. Use after a ban or
    when migrating to a different SIM. After this call, the QR endpoint
    will start returning a new QR within a few seconds.
    """
    ok = await whatsapp_client.reset()
    return {"ok": ok}


# --- Session blob endpoints (daemon-facing) --------------------------
# The daemon's identity is enforced by the X-Daemon-Token header.

SESSION_ID = "default"


@admin_router.get("/session/blob", dependencies=[Depends(require_daemon_token)])
async def get_session_blob(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    """Return the persisted Baileys auth blob, or 404 if none yet."""
    row = await session.get(WhatsappSession, SESSION_ID)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return {"blob": row.blob}


@admin_router.put("/session/blob", dependencies=[Depends(require_daemon_token)])
async def put_session_blob(
    body: SessionBlob,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, bool]:
    """Upsert the auth blob. Called by the daemon on every state change."""
    existing = await session.get(WhatsappSession, SESSION_ID)
    if existing is None:
        session.add(WhatsappSession(id=SESSION_ID, blob=body.blob))
    else:
        existing.blob = body.blob
    await session.commit()
    return {"ok": True}


# --- Webhook router (daemon-facing) ----------------------------------

webhook_router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp-webhooks"])


@webhook_router.post(
    "/inbound",
    dependencies=[Depends(require_daemon_token)],
)
async def inbound_message(
    msg: InboundMessage,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    """Store an inbound WhatsApp message.

    Idempotent on (chat_jid, message_id) — the daemon may retry, and
    WhatsApp itself occasionally redelivers. On Postgres we use ON
    CONFLICT DO NOTHING; on SQLite (tests) we fall back to a
    select-then-insert. Either way, duplicate pushes are a no-op.
    """
    if not msg.messageId:
        # Messages without a stable id come from system events — skip.
        return {"status": "skipped"}

    bind = session.get_bind() if session.bind is None else session.bind
    dialect = bind.dialect.name if bind is not None else "postgresql"

    if dialect == "postgresql":
        stmt = pg_insert(WhatsappMessage).values(
            message_id=msg.messageId,
            chat_jid=msg.chatJid,
            from_jid=msg.fromJid,
            from_phone=msg.fromPhone,
            from_name=msg.fromName,
            is_group=msg.isGroup,
            group_id=msg.groupId,
            group_name=msg.groupName,
            text=msg.text,
            media_type=msg.mediaType,
            wa_timestamp=msg.timestamp,
        ).on_conflict_do_nothing(
            constraint="uq_whatsapp_messages_chat_id",
        )
        await session.execute(stmt)
        await session.commit()
        return {"status": "stored"}

    # SQLite / other — manual dup check.
    existing = await session.execute(
        select(WhatsappMessage).where(
            WhatsappMessage.chat_jid == msg.chatJid,
            WhatsappMessage.message_id == msg.messageId,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return {"status": "duplicate"}

    session.add(
        WhatsappMessage(
            message_id=msg.messageId,
            chat_jid=msg.chatJid,
            from_jid=msg.fromJid,
            from_phone=msg.fromPhone,
            from_name=msg.fromName,
            is_group=msg.isGroup,
            group_id=msg.groupId,
            group_name=msg.groupName,
            text=msg.text,
            media_type=msg.mediaType,
            wa_timestamp=msg.timestamp,
        )
    )
    await session.commit()
    return {"status": "stored"}
