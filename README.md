# shmuelautomation

Monorepo for Classic Jerusalem Realty's property CMS + automation platform.

```
client/      # client-facing scope/proposal/checklist docs
backend/     # FastAPI service (source of truth for properties, CRM, automation)
admin/       # React admin dashboard
notes.md     # internal project notes
```

## Infrastructure

- **Database**: [Supabase](https://supabase.com) (hosted Postgres). Phase 1 fits comfortably in the free tier; ~$25/mo once real data flows. Used as plain Postgres — no lock-in beyond a `pg_dump` away.
- **Backend hosting**: [Fly.io](https://fly.io) for the FastAPI service. Dockerfile managed by `fly launch`; no local Docker needed for dev.
- **Redis** (Phase 2 only, for the scheduled-posting queue): [Upstash](https://upstash.com) hosted. Not needed yet.
- **Photo storage**: Google Drive / Dropbox (Shmuel's choice) — per his requirement to see folders directly.

We do not use Docker for local development. If a future piece of infra genuinely needs it, we'll add it then — not preemptively.

## Prerequisites

- Python 3.12+ with [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node 20+
- A Supabase project (free tier) — get the connection string from Project Settings → Database

## First-time setup

```bash
# 1. Backend
cd backend
cp .env.example .env
# edit .env: paste Supabase connection string into DATABASE_URL (when we add DB code)
uv sync
uv run uvicorn shmuel_backend.main:app --reload   # :8000

# 2. Admin (new terminal)
cd admin
cp .env.example .env
npm install
npx playwright install chromium   # one-time, for E2E tests
npm run dev                        # :5173
```

Open http://localhost:5173 — the admin page should show backend status `ok`.

## Testing

| Layer | Command | What it covers |
| --- | --- | --- |
| Backend unit | `cd backend && uv run pytest` | FastAPI routes, business logic |
| Admin unit | `cd admin && npm test` | React components, hooks (Vitest + Testing Library) |
| Admin E2E | `cd admin && npm run test:e2e` | Full browser flows (Playwright, Chromium) |

E2E tests mock third-party services (WhatsApp, Yad2, Facebook) via `page.route` — never hit live APIs from tests.

## Deployment (later)

- Backend → `fly deploy` from `backend/` (we'll add `fly.toml` when Phase 1 has something to ship).
- Admin → static build, served by Fly or Cloudflare Pages (TBD).
- DB → already live on Supabase; migrations run via whatever we pick (likely Alembic) pointed at the same connection string.
