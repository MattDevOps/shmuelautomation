# shmuelautomation

[![CI](https://github.com/MattDevOps/shmuelautomation/actions/workflows/ci.yml/badge.svg)](https://github.com/MattDevOps/shmuelautomation/actions/workflows/ci.yml)

Monorepo for **Classic Jerusalem Realty**'s property CMS + automation platform. Single user (Shmuel, a Jerusalem real estate broker); WordPress public site at **classicjerusalem.com** consumes the backend's public read API.

```
client/      # client-facing scope/proposal/checklist docs + Shmuel synopsis
backend/     # FastAPI service (source of truth for properties, CRM, automation)
admin/       # React admin SPA (Shmuel's daily-driver dashboard)
notes.md     # internal project notes
```

## What's built

### Phase 1 — foundation (done)

- **Property CMS**: full CRUD, filters, status flip (available/rented/sold), Excel export of all fields including internal notes.
- **Yad2 link import**: paste a URL → fetch & parse OpenGraph + JSON-LD → form pre-filled → review → save. Graceful fallback when blocked by Cloudflare.
- **Photo storage in Google Drive**: per-property folder (`Rent — Baka (4893a584)` style), idempotent upload via SHA-256 checksum, OAuth refresh tokens encrypted at rest with Fernet.
- **Public read API**: `/public/properties` for WordPress consumption — strict subset of fields, never leaks owner phone / broker fee / notes, defaults to `status=available`, cache-headed.
- **Contacts CRM**: address book with free-form segment tags, CSV export ready for webot or any WhatsApp bulk sender (UTF-8 BOM so Hebrew renders in Excel).

### Phase 2 — publishing & scheduling (done)

- **Scheduler engine**: pure Asia/Jerusalem time math — twice-daily slots (08:00 / 20:00), three posts per slot, Shabbat block from Friday 13:00 to Saturday 21:00. New listings get priority.
- **Post queue**: every available property is auto-enqueued; cancel-on-rented/sold; the admin sees what's due now and what's coming up.
- **Post composition**: Hebrew + English templates with tabular price, photo URL, Yad2 link.
- **One-tap share modal**: pre-composed text, language toggle, copy-to-clipboard, Open WhatsApp (`wa.me`), Share to Facebook, and per-group "copy & open ↗" jump links that copy the post text and open the destination in a new tab.
- **Configurable group lists**: WhatsApp / WhatsApp Status / Facebook / Janglo / other, tagged for rent / sale / both. Shmuel curates the destinations from the admin.

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
```

## Testing

| Layer | Command | Counts |
| --- | --- | --- |
| Backend unit | `cd backend && uv run pytest` | 107 tests |
| Admin unit | `cd admin && npm test` | 92 tests |
| Admin E2E | `cd admin && npm run test:e2e` | 3 flows (Properties / Yad2 import / Queue→share) |
| Backend lint | `cd backend && uv run ruff check .` | |
| Admin lint | `cd admin && npm run lint` | |

E2E mocks third-party services (WhatsApp, Yad2, Facebook, Google Drive, Dropbox) via `page.route` — never hits live APIs from tests. CI runs all of the above on every push and PR.

## Public API (for the WordPress site)

The backend exposes a small public, unauthenticated read API under `/public/*` that **classicjerusalem.com** can pull from. Internal fields (owner phone, broker fee terms, internal notes) never appear in this payload, and rented/sold inventory is hidden by default.

| Endpoint | Returns |
| --- | --- |
| `GET /public/properties?type=rent&neighborhood=Baka&limit=20&offset=0` | `{ items: [...], total, limit, offset }` |
| `GET /public/properties/{id}` | A single available property |

Both responses include `Cache-Control: public, max-age=60`, and the WordPress plugin holds the parsed result in a 60s transient on top, so the backend gets at most one request per minute per shortcode variant.

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
