"""Admin-facing routes for webot WhatsApp integration.

Surfaces the connection status so Shmuel can verify his token is wired
correctly without leaving the admin UI. Future routes (post a queued
slot, list groups for the queue config UI) live here too.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from shmuel_backend.config import settings
from shmuel_backend import webot_client

admin_router = APIRouter(prefix="/webot", tags=["webot"])


class WebotStatus(BaseModel):
    configured: bool
    from_phone: str | None
    reachable: bool
    detail: dict[str, Any] | None = None


@admin_router.get("/status", response_model=WebotStatus)
async def get_status() -> WebotStatus:
    """Verify webot integration is reachable + auth works.

    `configured=false` means the user hasn't set WEBOT_API_TOKEN yet — the
    admin UI should show "Connect webot" instead of "Connected".
    `reachable=false` with `configured=true` means the token is set but
    webot rejected it; check token in Cloud Run secret manager.
    """
    if not settings.webot_api_token or not settings.webot_from_phone:
        return WebotStatus(
            configured=False,
            from_phone=settings.webot_from_phone or None,
            reachable=False,
        )
    detail = await webot_client.check_status()
    return WebotStatus(
        configured=True,
        from_phone=settings.webot_from_phone,
        reachable=detail is not None,
        detail=detail,
    )
