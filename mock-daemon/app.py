"""Hosted mock WhatsApp daemon + live viewer.

Stands in for a paired 2nd number so the production backend can be
exercised end to end without a real WhatsApp connection. It speaks the
exact HTTP contract of whatsapp-daemon/src/server.ts (so the backend
treats it as a connected daemon), but instead of sending over WhatsApp it
CAPTURES every send and shows it on a live web page at `/`.

Captures are in-memory (deploy with max-instances=1 so every send and the
viewer hit the same instance). This is a demo aid, not production.

Env:
  DAEMON_TOKEN  shared secret the backend sends as X-Daemon-Token
  PORT          provided by Cloud Run (default 8080)
"""
from __future__ import annotations

import base64
import os
from collections import deque
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

TOKEN = os.environ.get("DAEMON_TOKEN", "")
MAX_CAPTURES = 50

app = FastAPI(title="mock-whatsapp-daemon")
_captures: deque[dict[str, Any]] = deque(maxlen=MAX_CAPTURES)
_counter = {"n": 0}


def _require_token(x_daemon_token: str | None) -> None:
    if TOKEN and x_daemon_token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/status")
def status(x_daemon_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_daemon_token)
    return {
        "state": "connected",
        "phone": "+972 50-000-0000 (MOCK 2nd number)",
        "qr": None,
        "captures": len(_captures),
    }


@app.get("/groups")
def groups(x_daemon_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_daemon_token)
    return {"groups": [
        {"id": "120363000000000001@g.us", "name": "Jerusalem Rentals WA"},
        {"id": "120363000000000002@g.us", "name": "Jerusalem Sales WA"},
    ]}


def _record(kind: str, group: str, caption: str, image_b64: str | None) -> str:
    _counter["n"] += 1
    n = _counter["n"]
    _captures.appendleft({
        "n": n,
        "kind": kind,
        "group": group,
        "caption": caption,
        "image_b64": image_b64,
        "ts": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
    })
    return f"mock-{kind}-{n}"


@app.post("/send-group-image")
async def send_group_image(
    request: Request, x_daemon_token: str | None = Header(default=None)
) -> JSONResponse:
    _require_token(x_daemon_token)
    body = await request.json()
    group = body.get("groupId", "?")
    image_b64 = body.get("imageBase64", "")
    caption = body.get("caption", "")
    if not group or not image_b64:
        return JSONResponse({"error": "groupId and imageBase64 are required"}, status_code=400)
    mid = _record("img", group, caption, image_b64)
    return JSONResponse({"ok": True, "messageId": mid})


@app.post("/send-group")
async def send_group(
    request: Request, x_daemon_token: str | None = Header(default=None)
) -> JSONResponse:
    _require_token(x_daemon_token)
    body = await request.json()
    group = body.get("groupId", "?")
    message = body.get("message", "")
    if not group:
        return JSONResponse({"error": "groupId required"}, status_code=400)
    mid = _record("txt", group, message, None)
    return JSONResponse({"ok": True, "messageId": mid})


@app.post("/send-dm")
async def send_dm(
    request: Request, x_daemon_token: str | None = Header(default=None)
) -> JSONResponse:
    _require_token(x_daemon_token)
    body = await request.json()
    mid = _record("dm", body.get("toPhone", "?"), body.get("message", ""), None)
    return JSONResponse({"ok": True, "messageId": mid})


@app.post("/reset")
def reset(x_daemon_token: str | None = Header(default=None)) -> dict[str, bool]:
    _require_token(x_daemon_token)
    _captures.clear()
    return {"ok": True}


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mock WhatsApp number — captured posts</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, sans-serif; margin: 0; background: #0b141a; color: #e9edef; }}
  header {{ background: #202c33; padding: 16px 20px; position: sticky; top: 0; }}
  header h1 {{ font-size: 17px; margin: 0; }}
  header p {{ margin: 4px 0 0; font-size: 13px; color: #8696a0; }}
  .wrap {{ max-width: 560px; margin: 0 auto; padding: 16px; }}
  .empty {{ text-align: center; color: #8696a0; padding: 60px 20px; }}
  .msg {{ background: #005c4b; border-radius: 8px 8px 0 8px; margin: 0 0 14px auto;
          padding: 8px; max-width: 90%; box-shadow: 0 1px 1px rgba(0,0,0,.3); }}
  .msg img {{ width: 100%; border-radius: 6px; display: block; }}
  .msg .cap {{ white-space: pre-wrap; font-size: 14px; padding: 6px 4px 2px; }}
  .msg .meta {{ font-size: 11px; color: #a7c8bd; text-align: right; padding: 2px 4px 0; }}
  .grp {{ font-size: 11px; color: #8696a0; text-align: right; margin: 0 2px 4px auto; max-width: 90%; }}
</style></head><body>
<header><h1>Mock WhatsApp number — live captured posts</h1>
<p>{phone} · {count} captured · auto-refreshes every 3s. Nothing is sent to real WhatsApp.</p></header>
<div class="wrap">{body}</div>
<script>setTimeout(function(){{location.reload()}}, 3000)</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def viewer() -> HTMLResponse:
    if not _captures:
        body = '<div class="empty">No posts captured yet.<br>Hit "Post now" in the admin Queue.</div>'
    else:
        chunks = []
        for c in _captures:
            grp = f'<div class="grp">to {c["group"]}</div>'
            img = (f'<img src="data:image/png;base64,{c["image_b64"]}" alt="collage">'
                   if c["image_b64"] else "")
            cap = c["caption"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            chunks.append(
                f'{grp}<div class="msg">{img}<div class="cap">{cap}</div>'
                f'<div class="meta">{c["ts"]} · {c["kind"]} #{c["n"]}</div></div>'
            )
        body = "".join(chunks)
    html = PAGE.format(
        phone="+972 50-000-0000 (MOCK 2nd number)",
        count=len(_captures),
        body=body,
    )
    return HTMLResponse(html)


# Render the raw PNG of the most recent image capture, for quick checks.
@app.get("/latest.png")
def latest_png() -> Response:
    for c in _captures:
        if c["image_b64"]:
            return Response(base64.b64decode(c["image_b64"]), media_type="image/png")
    raise HTTPException(status_code=404, detail="no image captured yet")
