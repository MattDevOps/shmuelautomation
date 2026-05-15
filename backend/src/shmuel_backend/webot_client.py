"""Webot WhatsApp client — graceful no-op when unconfigured.

Mirrors the pattern of `translation_client.py` and `email_client.py`:
runs without `WEBOT_API_TOKEN` log the would-be call and return None.
Errors are logged but never raised — webot's WhatsApp service shouldn't
take down our scheduler or admin panel if the upstream is flaky.

Webot's API:
- BearerAuth-protected on some endpoints; `/sendMessage` etc take the
  token in the request body. Both are sent for safety.
- Hebrew text and emoji are fine — webot's payload is plain JSON.
- `fromPhoneNumber` is the WhatsApp number Shmuel has registered with
  webot; `toPhoneNumber` is either a contact's number or a group ID
  returned by `/getGroups`.

OpenAPI spec: https://api.webot.co.il/api-explorer/
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from shmuel_backend.config import settings

log = logging.getLogger(__name__)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.webot_api_token}",
        "Content-Type": "application/json",
    }


async def send_message(
    *,
    to_phone_number: str,
    message: str,
    media_link: str | None = None,
) -> dict[str, Any] | None:
    """Send a WhatsApp message via webot. Returns the parsed JSON response,
    or None on no-op / failure. Never raises.

    `to_phone_number` accepts both contact phone numbers (e.g. `972527485568`)
    and group IDs returned by `get_groups()`.
    """
    if not settings.webot_api_token or not settings.webot_from_phone:
        log.info(
            "webot not configured; would have sent %d chars to %s",
            len(message), to_phone_number,
        )
        return None

    payload: dict[str, Any] = {
        "token": settings.webot_api_token,
        "fromPhoneNumber": settings.webot_from_phone,
        "toPhoneNumber": to_phone_number,
        "message": message,
    }
    if media_link:
        payload["mediaLink"] = media_link

    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(
                f"{settings.webot_api_base_url}/sendMessage",
                json=payload,
                headers=_headers(),
            )
        if resp.status_code >= 400:
            log.warning("webot send_message %s: %s", resp.status_code, resp.text[:500])
            return None
        try:
            return resp.json()
        except ValueError:
            # 200 with empty body — webot's spec says `content: {}` for the
            # success response. Treat that as a successful send.
            return {"ok": True}
    except httpx.HTTPError as exc:
        log.warning("webot send_message failed: %s", exc)
        return None


async def get_groups() -> list[dict[str, Any]] | None:
    """List WhatsApp groups visible to the authenticated session. Returns
    the parsed list, or None on no-op / failure.
    """
    if not settings.webot_api_token:
        log.info("webot not configured; cannot list groups")
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(
                f"{settings.webot_api_base_url}/getGroups",
                json={"token": settings.webot_api_token},
                headers=_headers(),
            )
        if resp.status_code >= 400:
            log.warning("webot get_groups %s: %s", resp.status_code, resp.text[:500])
            return None
        body = resp.json()
        # The spec is loose on the response shape; tolerate both `{"groups":[...]}` and `[...]`
        if isinstance(body, dict) and "groups" in body:
            return body["groups"]
        if isinstance(body, list):
            return body
        log.warning("webot get_groups: unexpected response shape: %s", type(body).__name__)
        return None
    except httpx.HTTPError as exc:
        log.warning("webot get_groups failed: %s", exc)
        return None


async def check_status() -> dict[str, Any] | None:
    """Ping webot to verify the integration. Returns the raw response, or
    None on no-op / failure. Use this to surface a "Connected to webot"
    indicator in the admin UI.
    """
    if not settings.webot_api_token:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(
                f"{settings.webot_api_base_url}/checkStatus",
                json={"token": settings.webot_api_token},
                headers=_headers(),
            )
        if resp.status_code >= 400:
            log.warning("webot check_status %s: %s", resp.status_code, resp.text[:500])
            return None
        try:
            return resp.json()
        except ValueError:
            return {"ok": True}
    except httpx.HTTPError as exc:
        log.warning("webot check_status failed: %s", exc)
        return None
