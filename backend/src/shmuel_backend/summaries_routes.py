"""Admin routes for the Phase 3.2 conversation summarizer.

- `POST /whatsapp/summaries/run` — kick the summarization job manually
  (also the endpoint the Cloud Scheduler cron will hit).
- `GET /whatsapp/summaries` — paginated list; filter by contact, by
  recency.
- `GET /whatsapp/threads/{id}/summaries` — summaries scoped to one
  thread, oldest-first (chronological).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.db import get_session
from shmuel_backend.models import ConversationSummary, WhatsappThread
from shmuel_backend.summarizer import summarize_all_threads, summarize_thread

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


class SummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_jid: str
    phone_number: str | None = None
    contact_id: uuid.UUID | None = None
    period_start: datetime
    period_end: datetime
    message_count: int
    summary: str
    action_items: list[str]
    mentioned_amounts: list[str]
    mentioned_dates: list[str]
    created_at: datetime


class SummaryList(BaseModel):
    summaries: list[SummaryRead]
    total: int


class ThreadSummaryRunRow(BaseModel):
    thread_id: str
    chat_jid: str
    message_count: int
    period_start: datetime | None = None
    period_end: datetime | None = None
    summary_id: str | None = None
    skipped_reason: str | None = None


class SummarizeRunResult(BaseModel):
    attempted: int
    summarized: int
    skipped: int
    threads: list[ThreadSummaryRunRow]


def _result_to_run_row(r: Any) -> ThreadSummaryRunRow:
    return ThreadSummaryRunRow(
        thread_id=r.thread_id,
        chat_jid=r.chat_jid,
        message_count=r.message_count,
        period_start=r.period_start,
        period_end=r.period_end,
        summary_id=r.summary_id,
        skipped_reason=r.skipped_reason,
    )


@router.post("/summaries/run", response_model=SummarizeRunResult)
async def run_summarize_all(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SummarizeRunResult:
    """Summarize every recently-active thread with new messages."""
    run = await summarize_all_threads(session)
    return SummarizeRunResult(
        attempted=run.attempted,
        summarized=run.summarized,
        skipped=run.skipped,
        threads=[_result_to_run_row(t) for t in run.threads],
    )


@router.post(
    "/threads/{thread_id}/summarize",
    response_model=ThreadSummaryRunRow,
)
async def summarize_one_thread(
    thread_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ThreadSummaryRunRow:
    """Manually summarize one thread — useful for ad-hoc 'catch me up'
    moments before Shmuel reads a thread he hasn't seen yet."""
    thread = await session.get(WhatsappThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    result = await summarize_thread(session, thread)
    return _result_to_run_row(result)


@router.get("/summaries", response_model=SummaryList)
async def list_summaries(
    session: Annotated[AsyncSession, Depends(get_session)],
    contact_id: Annotated[uuid.UUID | None, Query()] = None,
    chat_jid: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SummaryList:
    base = select(ConversationSummary)
    count_q = select(func.count()).select_from(ConversationSummary)
    if contact_id is not None:
        base = base.where(ConversationSummary.contact_id == contact_id)
        count_q = count_q.where(ConversationSummary.contact_id == contact_id)
    if chat_jid is not None:
        base = base.where(ConversationSummary.chat_jid == chat_jid)
        count_q = count_q.where(ConversationSummary.chat_jid == chat_jid)

    rows = await session.execute(
        base.order_by(desc(ConversationSummary.period_end)).limit(limit).offset(offset)
    )
    total = (await session.execute(count_q)).scalar_one()
    return SummaryList(
        summaries=[SummaryRead.model_validate(s) for s in rows.scalars().all()],
        total=int(total),
    )


@router.get(
    "/threads/{thread_id}/summaries",
    response_model=list[SummaryRead],
)
async def list_thread_summaries(
    thread_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[SummaryRead]:
    """All summaries for one thread, oldest first."""
    thread = await session.get(WhatsappThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    rows = await session.execute(
        select(ConversationSummary)
        .where(ConversationSummary.chat_jid == thread.chat_jid)
        .order_by(ConversationSummary.period_end.asc())
    )
    return [SummaryRead.model_validate(s) for s in rows.scalars().all()]
