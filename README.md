# shmuelautomation

[![CI](https://github.com/MattDevOps/shmuelautomation/actions/workflows/ci.yml/badge.svg)](https://github.com/MattDevOps/shmuelautomation/actions/workflows/ci.yml)

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

## Public API (for the WordPress site)

The backend exposes a small public, unauthenticated read API under `/public/*`
that the WordPress site at **classicjerusalem.com** can pull from. Internal
fields (owner phone, broker fee terms, internal notes) never appear in this
payload, and rented/sold inventory is hidden by default.

| Endpoint | Returns |
| --- | --- |
| `GET /public/properties?type=rent&neighborhood=Baka&limit=20&offset=0` | `{ items: [...], total, limit, offset }` |
| `GET /public/properties/{id}` | A single available property |

Both responses include `Cache-Control: public, max-age=60`, so a WordPress page
caching layer (or a transient stored in `wp_options`) can safely keep results
for a minute.

Minimal PHP shortcode for `wp-content/themes/.../functions.php` — one per page,
no external libraries needed:

```php
add_shortcode('classic_listings', function ($atts) {
  $atts = shortcode_atts(['type' => 'rent', 'limit' => 12], $atts);
  $cache_key = 'classic_listings_' . md5(serialize($atts));
  $cached = get_transient($cache_key);
  if ($cached !== false) return $cached;

  $url = 'https://api.classicjerusalem.com/public/properties?'
       . http_build_query(['type' => $atts['type'], 'limit' => $atts['limit']]);
  $resp = wp_remote_get($url, ['timeout' => 5]);
  if (is_wp_error($resp)) return '';
  $body = json_decode(wp_remote_retrieve_body($resp), true);

  ob_start();
  foreach ($body['items'] as $p) {
    $price = number_format((float) $p['price'], 0);
    $hood = esc_html($p['neighborhood'] ?? '');
    echo "<article class='listing'>";
    echo "<h3>{$hood}</h3>";
    echo "<p>{$p['currency']} {$price}</p>";
    echo "</article>";
  }
  $html = ob_get_clean();
  set_transient($cache_key, $html, 60);
  return $html;
});
```

Then in any WordPress page or post: `[classic_listings type="rent" limit="12"]`.

## Deployment (later)

- Backend → `fly deploy` from `backend/` (we'll add `fly.toml` when Phase 1 has something to ship).
- Admin → static build, served by Fly or Cloudflare Pages (TBD).
- DB → already live on Supabase; migrations run via whatever we pick (likely Alembic) pointed at the same connection string.
