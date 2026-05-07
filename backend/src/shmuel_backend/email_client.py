"""Resend transactional email — graceful no-op when unconfigured.

Local/CI runs without RESEND_API_KEY just log the would-be send and
return without raising. Mirrors how Sentry behaves in this codebase
so dev environments don't need real credentials.

`send_email` is the only public entry point. Errors during a real send
are logged but not re-raised: a digest failure should never roll back
the property write that triggered it.
"""
from __future__ import annotations

import logging

import httpx

from shmuel_backend.config import settings

log = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


async def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    text: str,
) -> bool:
    """Send a single transactional email via Resend.

    Returns True if Resend accepted the payload, False if no-op or failed.
    Never raises — callers can ignore the return when they don't need to
    branch on delivery state.
    """
    if not settings.resend_api_key:
        log.info("Resend not configured; would have sent to=%s subject=%r", to, subject)
        return False

    payload = {
        "from": settings.newsletter_from_email,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }
    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.post(RESEND_ENDPOINT, json=payload, headers=headers)
        if resp.status_code >= 400:
            log.warning(
                "Resend returned %s for to=%s: %s",
                resp.status_code,
                to,
                resp.text[:500],
            )
            return False
        return True
    except httpx.HTTPError as exc:
        log.warning("Resend send failed for to=%s: %s", to, exc)
        return False
