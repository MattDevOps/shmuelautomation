# shmuelautomation

[![CI](https://github.com/MattDevOps/shmuelautomation/actions/workflows/ci.yml/badge.svg)](https://github.com/MattDevOps/shmuelautomation/actions/workflows/ci.yml)

Monorepo for **Classic Jerusalem Realty**'s property CMS + automation platform. Single user (Shmuel, a Jerusalem real estate broker). The public site **classicjerusalem.com** is a Next.js 16 app (separate repo at `classic-jerusalem-frontend/`, cut over from Frontity on 2026-05-14) that consumes both the WordPress REST surface and this backend's public API. A WordPress installation at `realestateadmin2025.classicjerusalem.com` still hosts the CMS for property/blog/neighborhood content; the WP plugin ships if Shmuel ever wants to roll back to a WP-rendered public site.

```
client/             # client-facing scope/proposal/checklist docs + Shmuel synopsis
client/user-guide.md  # Shmuel's day-to-day how-to (plain-English)
backend/            # FastAPI service (source of truth for properties, CRM, automation)
admin/              # React admin SPA (Shmuel's daily-driver dashboard)
wordpress-plugin/   # installable plugin for classicjerusalem.com (build.sh → .zip)
notes.md            # internal project notes
```

## What's built

### Phase 1 — foundation (done)

- **Property CMS**: full CRUD, filters, status flip (available/rented/sold), Excel export of all fields including internal notes.
- **Yad2 link import**: paste a URL → fetch & parse OpenGraph + JSON-LD → form pre-filled → review → save. Graceful fallback when blocked by Cloudflare.
- **Photo storage in Google Drive**: per-property folder (`Rent — Baka (4893a584)` style), idempotent upload via SHA-256 checksum, OAuth refresh tokens encrypted at rest with Fernet.
- **Public read API**: `/public/properties` for WordPress consumption — strict subset of fields, never leaks owner phone / broker fee / notes, defaults to `status=available`, cache-headed.
- **Contacts CRM**: address book with free-form segment tags, CSV export ready for any WhatsApp bulk sender (UTF-8 BOM so Hebrew renders in Excel).

### Phase 2 — publishing & scheduling (done)

- **Scheduler engine**: pure Asia/Jerusalem time math — twice-daily slots (08:00 / 20:00), three posts per slot, Shabbat block from Friday 13:00 to Saturday 21:00. New listings get priority.
- **Post queue**: every available property is auto-enqueued; cancel-on-rented/sold; the admin sees what's due now and what's coming up.
- **Post composition**: Hebrew + English templates with tabular price, photo URL, Yad2 link.
- **One-tap share modal**: pre-composed text, language toggle, copy-to-clipboard, Open WhatsApp (`wa.me`), Share to Facebook, and per-group "copy & open ↗" jump links that copy the post text and open the destination in a new tab.
- **Configurable group lists**: WhatsApp / WhatsApp Status / Facebook / Janglo / other, tagged for rent / sale / both. Shmuel curates the destinations from the admin.
- **WhatsApp daemon integration** (no-op pending deploy): `whatsapp_client.py` talks to a self-hosted Baileys-based daemon (in `whatsapp-daemon/`) over its small HTTP API (`/send-group`, `/send-dm`, `/groups`, `/status`, `/qr`, `/reset`). Session auth (the Baileys creds/keys blob) round-trips through `/whatsapp/session/blob` so the backend's Postgres is the durable store and the daemon can redeploy without losing pairing. Every inbound message lands in `whatsapp_messages` via `/webhooks/whatsapp/inbound` — the data foundation for the Phase 3 chatbot + summarization. `auto_poster.dispatch_slot(slot)` is the Phase 2 trigger that posts a queued slot to every active matching WhatsApp group. Activates by setting `WHATSAPP_DAEMON_URL` + `WHATSAPP_DAEMON_TOKEN` in Cloud Run secrets and deploying the daemon (see `whatsapp-daemon/README.md`).

### Phase 3 — partial (newsletter + i18n done; chatbot pending)

- **Newsletter**: double opt-in subscribers, branded HTML digests in EN/HE via Resend, threshold-based digest triggers (default: 3 new matching properties), rent/sale/both filter, one-click unsubscribe. Signup form on the public Next.js site (`SubscribeFloater` → `/api/subscribe/` → backend) captures language + rent/sale preference at signup.
- **Multi-language public site**: Next.js rebuild serves 4 locales (EN default, ES, FR, HE) with hreflang alternates and a 664-URL sitemap. WP content (properties, blogs, neighborhoods) translated to ES/FR/HE via OpenAI gpt-4o-mini and served from `content_translations` in Supabase; chrome strings localized via `messages/{en,es,fr,he}.json` + a client-side `LocaleProvider`/`useT()` hook. Backfill produced ~3,000 translation rows.
- **Pending**: AI WhatsApp chatbot (blocked on Shmuel's Meta Business onboarding decision), call/WhatsApp → CRM summarization (not started).

## Infrastructure

- **Database**: [Supabase](https://supabase.com) (hosted Postgres). Used as plain Postgres — no Supabase-specific features.
- **Backend hosting**: [Google Cloud Run](https://cloud.google.com/run) — same GCP project as Drive OAuth, free tier covers single-user traffic.
- **Photo storage**: Google Drive (per-broker; OAuth on Shmuel's own account).
- **Redis** (Phase 2 hooks not used yet, queue is on-demand): [Upstash](https://upstash.com) when we eventually add background jobs.

No local Docker — all infra is hosted, including the dev DB during testing (SQLite via aiosqlite for local; Postgres in production).

## Prerequisites

- Python 3.12+ with [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node 20+
- A Supabase project (free tier) for production. SQLite covers local dev.
- A Google Cloud project with the Drive API enabled + OAuth client (Web application, redirect URI `http://localhost:8000/auth/google/callback`).

## First-time setup

```bash
# 1. Backend
cd backend
cp .env.example .env
# edit .env — see "Required env vars" below
uv sync
uv run alembic upgrade head
uv run uvicorn shmuel_backend.main:app --reload   # :8000

# 2. Admin (new terminal)
cd admin
cp .env.example .env
npm install
npx playwright install chromium   # one-time, for E2E tests
npm run dev                        # :5173
```

Open http://localhost:5173 → you should land on the Properties page.

### Required env vars (`backend/.env`)

```bash
DATABASE_URL=sqlite+aiosqlite:///./dev.sqlite
# Supabase prod: postgresql+asyncpg://...

# Generate once:
# python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=<fernet key — do not change after first use>

# Google Cloud Console → Credentials → OAuth 2.0 Client ID (Web application)
GOOGLE_OAUTH_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-...
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/auth/google/callback

ADMIN_REDIRECT_URI=http://localhost:5173/settings

# Resend for transactional email (newsletter confirmation + digests).
# Empty = no-op (subscribe still records the row, the email just doesn't
# go out — keeps local dev painless).
RESEND_API_KEY=

# OpenAI for property/blog/neighborhood translation backfill.
# Empty = sync logs would-be calls and no Postgres writes happen.
OPENAI_API_KEY=
OPENAI_TRANSLATE_MODEL=gpt-4o-mini

# WhatsApp daemon (Phase 2). Both must be set for /whatsapp/status to
# report reachable and auto_poster to dispatch. Empty = no-op.
# The daemon itself lives in whatsapp-daemon/ — deploy it separately
# (e.g. Fly.io) and point WHATSAPP_DAEMON_URL at its private hostname.
# Token is a shared secret — generate with `openssl rand -hex 32`.
WHATSAPP_DAEMON_URL=
WHATSAPP_DAEMON_TOKEN=
```

## Testing

| Layer | Command | Counts |
| --- | --- | --- |
| Backend unit | `cd backend && uv run pytest` | 249 tests |
| Admin unit | `cd admin && npm test` | 92 tests |
| Admin E2E | `cd admin && npm run test:e2e` | 3 flows (Properties / Yad2 import / Queue→share) |
| Frontend (Next.js) typecheck | `cd classic-jerusalem-frontend && npx tsc --noEmit` | |
| Backend lint | `cd backend && uv run ruff check .` | |
| Admin lint | `cd admin && npm run lint` | |

E2E mocks third-party services (WhatsApp, Yad2, Facebook, Google Drive, Dropbox) via `page.route` — never hits live APIs from tests. CI runs all of the above on every push and PR.

## Public API

The backend exposes a small public, unauthenticated read API under `/public/*` for both the Next.js rebuild and any other client. Internal fields (owner phone, broker fee terms, internal notes) never appear in this payload, and rented/sold inventory is hidden by default.

| Endpoint | Returns |
| --- | --- |
| `GET /public/properties?type=rent&neighborhood=Baka&limit=20&offset=0` | `{ items: [...], total, limit, offset }` |
| `GET /public/properties/{id}` | A single available property |
| `GET /public/translations?content_type=property&slugs=a,b,c&lang=he` | Per-slug field translations for ES/FR/HE |
| `POST /public/newsletter/subscribe` | Double-opt-in signup; emits confirmation email via Resend |
| `GET /public/newsletter/confirm/{token}` | Click-through from confirmation email |
| `GET /public/newsletter/unsubscribe/{token}` | One-click unsubscribe |

Property responses include `Cache-Control: public, max-age=60`. The WordPress plugin (kept for rollback) holds parsed results in a 60s transient. The Next.js rebuild relies on Next's built-in fetch cache.

### Admin API (X-API-Key gated, behind Cloudflare Access in production)

| Endpoint | Returns |
| --- | --- |
| `POST /translations/sync` | Idempotent full translation sync (WP → OpenAI → Supabase) |
| `GET /whatsapp/status` | WhatsApp daemon health: `{configured, reachable, connection_state, paired_phone, last_connected_at, last_disconnect_reason}` |
| `GET /whatsapp/qr` | Current pairing QR (PNG data URL) or `null` if already connected |
| `GET /whatsapp/groups` | Groups the paired phone is in — populates the group-picker UI |
| `POST /whatsapp/reset` | Wipe the daemon's auth and force re-pairing |
| `GET /newsletter/subscribers` | Subscriber list + stats for the admin newsletter page |

The repo ships an installable WordPress plugin in `wordpress-plugin/`:

```bash
bash wordpress-plugin/build.sh
# → wordpress-plugin/dist/classic-jerusalem-listings-1.0.0.zip
```

In WordPress: Plugins → Add New → Upload Plugin → choose the .zip → Activate.
Then Settings → Classic Listings → set the API base URL.

Use `[classic_listings type="rent" limit="12"]` in any page or post. Available shortcode options: `type` (`rent` or `sale`), `limit`, `neighborhood`.

## Deployment (later)

- Backend → `gcloud run deploy` from `backend/`. Container builds from a Dockerfile in `backend/` (added at deploy time).
- Admin → static build, served by Fly or Cloudflare Pages (TBD).
- DB → Supabase; `alembic upgrade head` against the prod connection string.

## Design system

`.impeccable.md` at repo root captures the design context (audience, tone, palette, type). `admin/DESIGN_BRIEF.md` is the page-by-page rationale. The aesthetic is editorial/documentary with a Jerusalem-stone palette — paper-cream backgrounds, warm ink text, terracotta clay accent. Hebrew + English render side-by-side via `dir="auto"` on free-text fields.
