"""Admin routes for the WhatsApp chatbot — threads, messages, config.

Three pieces:

1. `GET /whatsapp/threads` — paginated list, filter by mode.
2. `GET /whatsapp/threads/{id}` — single thread plus its last N messages.
3. `PATCH /whatsapp/threads/{id}` — flip mode (takeover / release).
4. `GET /whatsapp/bot-config` / `PATCH /whatsapp/bot-config` — single-
   row runtime toggle for chatbot_enabled and greeting/takeover copy.

All under the existing X-API-Key gate so the admin SPA reaches them
the same way as every other admin route.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.chatbot import get_or_create_bot_config
from shmuel_backend.db import get_session
from shmuel_backend.enums import ThreadMode
from shmuel_backend.models import WhatsappMessage, WhatsappThread

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


# --- Schemas ---------------------------------------------------------


class ThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_jid: str
    phone_number: str | None = None
    display_name: str | None = None
    mode: ThreadMode
    takeover_reason: str | None = None
    contact_id: uuid.UUID | None = None
    last_bot_reply_at: datetime | None = None
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ThreadList(BaseModel):
    threads: list[ThreadRead]
    total: int


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: str
    chat_jid: str
    from_jid: str
    from_phone: str | None = None
    from_name: str | None = None
    text: str | None = None
    media_type: str | None = None
    is_group: bool
    wa_timestamp: int
    created_at: datetime


class ThreadDetail(BaseModel):
    thread: ThreadRead
    messages: list[MessageRead]


class ThreadUpdate(BaseModel):
    mode: ThreadMode
    takeover_reason: str | None = None


class BotConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chatbot_enabled: bool
    greeting_he: str | None = None
    greeting_en: str | None = None
    takeover_notice_he: str | None = None
    takeover_notice_en: str | None = None
    updated_at: datetime


class BotConfigUpdate(BaseModel):
    chatbot_enabled: bool | None = None
    greeting_he: str | None = Field(default=None, max_length=2000)
    greeting_en: str | None = Field(default=None, max_length=2000)
    takeover_notice_he: str | None = Field(default=None, max_length=2000)
    takeover_notice_en: str | None = Field(default=None, max_length=2000)


# --- Threads ---------------------------------------------------------


@router.get("/threads", response_model=ThreadList)
async def list_threads(
    session: Annotated[AsyncSession, Depends(get_session)],
    mode: Annotated[ThreadMode | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ThreadList:
    """Most-recently-active threads first.

    `last_message_at` falls back to `created_at` so brand-new threads
    with no recorded message yet still surface to the top."""
    base = select(WhatsappThread)
    count_q = select(func.count()).select_from(WhatsappThread)
    if mode is not None:
        base = base.where(WhatsappThread.mode == mode)
        count_q = count_q.where(WhatsappThread.mode == mode)

    sort_key = func.coalesce(WhatsappThread.last_message_at, WhatsappThread.created_at)
    rows = await session.execute(
        base.order_by(desc(sort_key)).limit(limit).offset(offset)
    )
    total = (await session.execute(count_q)).scalar_one()
    return ThreadList(
        threads=[ThreadRead.model_validate(t) for t in rows.scalars().all()],
        total=int(total),
    )


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    message_limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> ThreadDetail:
    """Thread + last N messages, oldest-first for chronological reading."""
    thread = await session.get(WhatsappThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    rows = await session.execute(
        select(WhatsappMessage)
        .where(WhatsappMessage.chat_jid == thread.chat_jid)
        .order_by(desc(WhatsappMessage.created_at))
        .limit(message_limit)
    )
    msgs = list(rows.scalars().all())
    msgs.reverse()
    return ThreadDetail(
        thread=ThreadRead.model_validate(thread),
        messages=[MessageRead.model_validate(m) for m in msgs],
    )


@router.patch("/threads/{thread_id}", response_model=ThreadRead)
async def update_thread(
    thread_id: uuid.UUID,
    body: ThreadUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ThreadRead:
    """Takeover (BOT→HUMAN) or release (HUMAN→BOT) a thread.

    Releasing clears `takeover_reason`. We don't unset the watermark on
    release — letting the bot answer the next new message but not
    re-process backlog is the safer behavior."""
    thread = await session.get(WhatsappThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    thread.mode = body.mode
    if body.mode == ThreadMode.BOT:
        thread.takeover_reason = None
    elif body.takeover_reason is not None:
        thread.takeover_reason = body.takeover_reason
    await session.commit()
    await session.refresh(thread)
    return ThreadRead.model_validate(thread)


# --- Bot config ------------------------------------------------------


@router.get("/bot-config", response_model=BotConfigRead)
async def get_bot_config(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BotConfigRead:
    cfg = await get_or_create_bot_config(session)
    await session.commit()  # persist the row if get_or_create just created it
    return BotConfigRead.model_validate(cfg)


@router.patch("/bot-config", response_model=BotConfigRead)
async def update_bot_config(
    body: BotConfigUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BotConfigRead:
    cfg = await get_or_create_bot_config(session)
    for field_name in (
        "chatbot_enabled",
        "greeting_he",
        "greeting_en",
        "takeover_notice_he",
        "takeover_notice_en",
    ):
        value = getattr(body, field_name)
        if value is not None:
            setattr(cfg, field_name, value)
    await session.commit()
    await session.refresh(cfg)
    return BotConfigRead.model_validate(cfg)


