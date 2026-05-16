# whatsapp-daemon

Long-running Baileys-based WhatsApp daemon for Classic Jerusalem Realty. Pairs to a dedicated 2nd WhatsApp number, exposes a small HTTP API to the FastAPI backend, and pushes inbound messages to the backend webhook.

## What it replaces

Webot. Before: backend's `webot_client.py` called `api.webot.co.il` over HTTPS, Shmuel paid webot a monthly fee, conversations and groups lived in webot's closed system. After: backend's `whatsapp_client.py` calls this daemon over HTTPS on a private network, no monthly fee, every inbound message lands in our Postgres so the Phase 3 chatbot and summarization features have a clean data foundation.

## Architecture

```
FastAPI backend (Cloud Run)
        │  HTTP (X-Daemon-Token)
        ▼
whatsapp-daemon (Fly.io shared-cpu-1x, always-on)
        │  Baileys WebSocket
        ▼
WhatsApp servers (paired as a linked device of the 2nd-number account)
```

Auth state (the pairing) is persisted to the backend via `PUT /whatsapp/session/blob` so the daemon's machine is replaceable — kill the VM, redeploy, the new instance loads the blob from Supabase and reconnects without re-scanning the QR.

## Endpoints

All require `X-Daemon-Token` header except `/health`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Unauthenticated. For Fly's healthcheck. |
| `GET` | `/status` | Connection snapshot: state, paired phone, last connect time. |
| `GET` | `/qr?format=png` | Current QR string. `format=png` returns a data URL. 409 if already connected. |
| `POST` | `/send-dm` | Body: `{toPhone, message}`. Returns `{ok, messageId}` or 503 if not connected. |
| `POST` | `/send-group` | Body: `{groupId, message}`. Same response shape. |
| `GET` | `/groups` | List of groups the paired number is in. |
| `POST` | `/reset` | Wipe the auth blob and re-pair. Use when the number is banned or to migrate. |

## Local dev

```bash
cp .env.example .env
# Fill in DAEMON_AUTH_TOKEN, BACKEND_BASE_URL, BACKEND_API_KEY.
npm install
npm run dev
```

The first run prints a QR string. Render it (e.g. `qrencode -t ANSI` or paste into a QR-encoder). Scan from the 2nd-number's WhatsApp app under *Linked Devices*. Once paired, the auth blob is saved to the backend; subsequent restarts skip the QR.

## Deploy

See `fly.toml` and `Dockerfile`. The daemon needs to stay running 24/7 — Cloud Run's scale-to-zero doesn't work here because Baileys holds a long-lived WebSocket. Fly's `shared-cpu-1x` ($0-2/mo) is the cheapest fit.
