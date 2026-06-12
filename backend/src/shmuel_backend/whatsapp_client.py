"""HTTP client for the whatsapp-daemon.

The daemon (a separate Node/Baileys service in `whatsapp-daemon/`)
holds the long-lived WhatsApp connection; this module just talks to its
small HTTP API. Every call is best-effort: if the daemon is down or
unconfigured, functions log and return None rather than raising — the
caller (auto_poster, admin routes) decides how to handle the absence.

The daemon is identified by `WHATSAPP_DAEMON_URL` and authenticated by
a shared `WHATSAPP_DAEMON_TOKEN` (generated via `openssl rand -hex 32`).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from shmuel_backend.config import settings

log = logging.getLogger(__name__)


def _headers() -> dict[str, str]:
    return {
        "X-Daemon-Token": settings.whatsapp_daemon_token,
        "Content-Type": "application/json",
    }


def _configured() -> bool:
    return bool(settings.whatsapp_daemon_url and settings.whatsapp_daemon_token)


async def _post(path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _configured():
        log.info("whatsapp daemon not configured; would have called %s", path)
        return None
    url = f"{settings.whatsapp_daemon_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(url, json=payload, headers=_headers())
        if resp.status_code >= 400:
            log.warning("daemon %s %s: %s", path, resp.status_code, resp.text[:300])
            return None
        try:
            return resp.json()
        except ValueError:
            return {"ok": True}
    except httpx.HTTPError as exc:
        log.warning("daemon %s failed: %s", path, exc)
        return None


async def _get(path: str) -> dict[str, Any] | None:
    if not _configured():
        return None
    url = f"{settings.whatsapp_daemon_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(url, headers=_headers())
        if resp.status_code >= 400:
            log.warning("daemon %s %s: %s", path, resp.status_code, resp.text[:300])
            return None
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("daemon %s failed: %s", path, exc)
        return None


async def send_to_phone(
    *, to_phone_number: str, message: str,
) -> dict[str, Any] | None:
    """DM a phone number directly. Used by the Phase 3 chatbot to answer leads."""
    return await _post("/send-dm", {"toPhone": to_phone_number, "message": message})


async def send_to_group(
    *, group_id: str, message: str,
) -> dict[str, Any] | None:
    """Post to a WhatsApp group. Used by auto_poster.

    `group_id` accepts both bare ids (e.g. `12345-67890`) and full JIDs
    (`12345-67890@g.us`); the daemon normalizes.
    """
    return await _post("/send-group", {"groupId": group_id, "message": message})


async def send_image_to_group(
    *, group_id: str, image_base64: str, caption: str,
) -> dict[str, Any] | None:
    """Post a single image with a caption to a WhatsApp group.

    Used by auto_poster to send the property collage + post text together.
    `image_base64` is the raw PNG/JPEG bytes, base64-encoded.
    """
    return await _post(
        "/send-group-image",
        {"groupId": group_id, "imageBase64": image_base64, "caption": caption},
    )


async def list_groups() -> list[dict[str, Any]] | None:
    """List groups the paired number is in. Used by admin to pick groups
    for the queue config UI without forcing Shmuel to paste raw ids.
    """
    body = await _get("/groups")
    if body is None:
        return None
    groups = body.get("groups") if isinstance(body, dict) else None
    return groups if isinstance(groups, list) else None


async def check_status() -> dict[str, Any] | None:
    """Ping the daemon. None if unconfigured / unreachable; otherwise the
    daemon's connection snapshot (state, paired phone, last connect time).
    """
    return await _get("/status")


async def get_qr_png() -> str | None:
    """Fetch the current pairing QR as a PNG data URL. Returns None when
    the daemon is already connected or when there's no QR available yet.
    """
    if not _configured():
        return None
    url = f"{settings.whatsapp_daemon_url.rstrip('/')}/qr?format=png"
    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(url, headers=_headers())
        if resp.status_code == 409:
            return None  # already connected
        if resp.status_code >= 400:
            log.warning("daemon /qr %s: %s", resp.status_code, resp.text[:200])
            return None
        body = resp.json()
        qr = body.get("qrPng") if isinstance(body, dict) else None
        return qr if isinstance(qr, str) else None
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("daemon /qr failed: %s", exc)
        return None


async def reset() -> bool:
    """Wipe the daemon's session and force a re-pair. Used after a ban
    or when migrating to a new SIM. Returns True on apparent success.
    """
    result = await _post("/reset", {})
    return bool(result and result.get("ok"))
