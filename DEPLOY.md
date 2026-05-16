# Deploy runbook

Step-by-step for cutting over from `localhost` to production.

**Prereqs:**
- Shmuel has added a credit card to the Google Cloud billing account (one-time).
- You have `gcloud` installed locally and are authenticated as `classicjerusaleminfo@gmail.com` (the Google account that owns the GCP project).
- You have access to the Cloudflare account that manages `classicjerusalem.com` DNS (or Shmuel adds the records when prompted).

The Google Cloud project ID below comes from the existing OAuth setup. Replace `PROJECT_ID` with the actual one — find it at <https://console.cloud.google.com/home/dashboard>.

---

## Quick path: one script for §1.1 + §1.3 + §1.4 + §1.5 + §1.6

If you want to skip the step-by-step and just bootstrap the GCP side
in one shot, run:

```bash
# Provision Supabase first (web UI — see §1.2 below) and copy the
# pooler connection string. That's the only manual prereq.

export PROJECT_ID="classic-jerusalem-realty-XXXXX"
export DATABASE_URL="postgresql+asyncpg://...supabase.../postgres"
export GITHUB_REPO="MattDevOps/shmuelautomation"

bash deploy/bootstrap.sh
```

The script auto-loads `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
and `ENCRYPTION_KEY` from `backend/.env` if present (and generates a fresh
Fernet key if `ENCRYPTION_KEY` is empty). It's idempotent — safe to re-run
if a step fails partway through. At the end it prints the GitHub
secrets/variables to paste at <https://github.com/MattDevOps/shmuelautomation/settings/secrets/actions>.

The remaining browser-only steps (Cloudflare Pages, OAuth redirect URI,
Sentry, custom-domain DNS records) are still manual and documented below.

---

## 1. Backend → Cloud Run

### 1.1 Enable required APIs (one-time)

```bash
gcloud config set project PROJECT_ID
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com
```

### 1.2 Provision Supabase

1. Sign up / log in at <https://supabase.com>.
2. New project → name `classic-jerusalem-realty`, region `eu-central-1` (Frankfurt). Set + save the DB password.
3. Settings → Database → copy the **Connection string (URI)** in **Transaction pooler** mode (port 6543). Replace the `postgres://` scheme prefix with `postgresql+asyncpg://` — that's what SQLAlchemy needs.
4. Run migrations once from your laptop pointed at the prod DB:
   ```bash
   cd backend
   DATABASE_URL=postgresql+asyncpg://...  uv run alembic upgrade head
   ```

### 1.3 Store secrets in Secret Manager

Cloud Run reads secrets via env-var-style references at runtime — no plaintext in the service config.

```bash
# Replace VALUEs with the real strings — none should land in shell history.
echo -n "VALUE_FROM_LOCAL_DOTENV"  | gcloud secrets create encryption-key --data-file=-
echo -n "VALUE_FROM_GCP_OAUTH"     | gcloud secrets create google-oauth-client-id --data-file=-
echo -n "VALUE_FROM_GCP_OAUTH"     | gcloud secrets create google-oauth-client-secret --data-file=-
echo -n "VALUE_FROM_SUPABASE"      | gcloud secrets create database-url --data-file=-
echo -n "VALUE_FROM_RESEND"        | gcloud secrets create resend-api-key --data-file=-
echo -n "VALUE_FROM_OPENAI"        | gcloud secrets create openai-api-key --data-file=-
# WhatsApp daemon secrets are only needed once the Baileys daemon (in
# whatsapp-daemon/) is deployed. Until then, the backend no-ops gracefully
# on the WhatsApp path. Create empty placeholders OR omit from `--set-secrets`.
# Generate the token with `openssl rand -hex 32` and configure the same
# value on the daemon side so backend ↔ daemon can authenticate.
echo -n ""                         | gcloud secrets create whatsapp-daemon-url --data-file=-
echo -n ""                         | gcloud secrets create whatsapp-daemon-token --data-file=-
```

Each secret then needs `roles/secretmanager.secretAccessor` granted to the runtime SA (default compute SA, `<project-number>-compute@developer.gserviceaccount.com` — see §2.5 in DEPLOY.md history for the exact `gcloud secrets add-iam-policy-binding` invocation if not already done).

### 1.4 Deploy

```bash
cd backend
gcloud run deploy classic-jerusalem-realty-api \
  --source . \
  --region europe-west1 \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 4 \
  --memory 512Mi \
  --cpu 1 \
  --port 8000 \
  --set-env-vars "ENVIRONMENT=production,CORS_ORIGINS=[\"https://admin.classicjerusalem.com\"],GOOGLE_OAUTH_REDIRECT_URI=https://api.classicjerusalem.com/auth/google/callback,ADMIN_REDIRECT_URI=https://admin.classicjerusalem.com/settings" \
  --set-secrets "ENCRYPTION_KEY=encryption-key:latest,GOOGLE_OAUTH_CLIENT_ID=google-oauth-client-id:latest,GOOGLE_OAUTH_CLIENT_SECRET=google-oauth-client-secret:latest,DATABASE_URL=database-url:latest,BACKEND_API_KEY=backend-api-key:latest,RESEND_API_KEY=resend-api-key:latest,OPENAI_API_KEY=openai-api-key:latest,WHATSAPP_DAEMON_URL=whatsapp-daemon-url:latest,WHATSAPP_DAEMON_TOKEN=whatsapp-daemon-token:latest"
```

> If this is the very first deploy and you haven't yet created `backend-api-key` in Secret Manager (§1.6 covers it), drop that one entry from `--set-secrets` and re-run after creating it. The middleware no-ops when the env var is empty, so the service starts fine either way.

This builds the Dockerfile in Cloud Build, pushes to Artifact Registry, and deploys. First deploy takes ~3–4 minutes; subsequent ones are ~1 minute.

The command outputs a URL like `https://classic-jerusalem-realty-api-xxxx-mw.a.run.app`. Hit `/health` to confirm:

```bash
curl https://<that-url>/health
# {"status":"ok","environment":"production","db":"ok"}
```

### 1.5 Custom domain via a Cloudflare Worker proxy

We **don't** use `gcloud run domain-mappings` for `api.classicjerusalem.com`. Two reasons:

1. Cloud Run domain mapping isn't supported in `me-west1` (Tel Aviv) at all, and we hit a stuck "CertificatePending" state in `europe-west1` that didn't resolve even after recreating the mapping.
2. The Worker pattern lets us bolt on the `X-API-Key` gate (§1.7) at the edge without backend changes.

**The Worker (`api-proxy`):**

1. Cloudflare → **Workers & Pages** → **Create application** → **Create Worker** → name `api-proxy` → deploy with the default Hello World.
2. **Edit code** → replace with:

   ```javascript
   export default {
     async fetch(request, env) {
       const url = new URL(request.url);
       const publicPaths = ['/public/', '/auth/google/', '/health'];
       const isPublic = publicPaths.some(p => url.pathname.startsWith(p));
       const isPreflight = request.method === 'OPTIONS';

       if (!isPublic && !isPreflight) {
         const provided = request.headers.get('x-api-key');
         if (provided !== env.API_KEY) {
           return new Response('Unauthorized', { status: 401 });
         }
       }

       url.hostname = 'classic-jerusalem-realty-api-PROJECT_NUMBER.europe-west1.run.app';
       return fetch(new Request(url.toString(), request));
     }
   };
   ```

   Replace `PROJECT_NUMBER` with the actual one (find it via `gcloud projects describe PROJECT_ID --format='value(projectNumber)'`).

3. **Settings → Variables and Secrets → + Add → Secret**:
   - Name: `API_KEY`
   - Value: a fresh random key. Generate with:
     ```bash
     python3 -c "import secrets; print('cjr_' + secrets.token_urlsafe(32))"
     ```
   - Mirror this same value into §1.7 (Cloud Run secret) and §2 (Pages env var).
4. **Settings → Domains & Routes → + Add → Custom domain**:
   - `api.classicjerusalem.com`
   - Cloudflare auto-creates the DNS record and issues SSL within ~30 sec.

### 1.6 Backend X-API-Key check (defense in depth)

The Worker gates `api.classicjerusalem.com`, but the underlying `*.run.app` URL is publicly reachable. Mirror the same check in FastAPI so direct hits to the origin also require the key.

```bash
# Use the same value generated in §1.5.
echo -n "cjr_..." | gcloud secrets create backend-api-key --data-file=-

# Update the running service:
gcloud run services update classic-jerusalem-realty-api \
  --region europe-west1 \
  --update-secrets "BACKEND_API_KEY=backend-api-key:latest"
```

The middleware lives in `backend/src/shmuel_backend/main.py` and bypasses `/public/`, `/auth/google/`, `/health`, `/healthz`, and OPTIONS preflights.

### 1.7 Continuous deployment via GitHub Actions (one-time setup)

Once the manual deploy in 1.4 is healthy, wire up `main → prod` so future
pushes deploy automatically. The workflow at
`.github/workflows/deploy-backend.yml` is already in the repo — what's
left is the one-time GCP-side plumbing.

**Auth: Workload Identity Federation, no JSON keys.** GitHub authenticates
to GCP via short-lived tokens minted from your repo identity. No secret
JSON sits in repo settings.

```bash
# Replace these with the real values:
PROJECT_ID="classic-jerusalem-realty-XXXXX"
REPO="MattDevOps/shmuelautomation"
SA_NAME="github-deploy"
POOL="github-pool"
PROVIDER="github-provider"

# 1. Service account that GitHub will impersonate.
gcloud iam service-accounts create "$SA_NAME" \
  --display-name="GitHub Actions deployer"

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# 2. Roles the deployer needs.
for ROLE in roles/run.developer \
            roles/iam.serviceAccountUser \
            roles/artifactregistry.writer \
            roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" --role="$ROLE"
done

# 3. WIF pool + provider (GitHub OIDC).
gcloud iam workload-identity-pools create "$POOL" \
  --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --location=global \
  --workload-identity-pool="$POOL" \
  --display-name="GitHub OIDC" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="attribute.repository=='${REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
POOL_ID="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}"

# 4. Allow the GitHub repo to impersonate the service account.
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${REPO}"

# 5. Print what you'll paste into GitHub.
echo "GCP_PROJECT_ID=${PROJECT_ID}"
echo "GCP_SERVICE_ACCOUNT=${SA_EMAIL}"
echo "GCP_WIF_PROVIDER=${POOL_ID}/providers/${PROVIDER}"

# 6. Artifact Registry repo for images (if you haven't yet).
gcloud artifacts repositories create cloud-run-deploy \
  --repository-format=docker \
  --location=europe-west1 \
  --description="Cloud Run images for the realty backend"
```

**Add these to GitHub** at <https://github.com/MattDevOps/shmuelautomation/settings/secrets/actions>:

| Type | Name | Value |
| --- | --- | --- |
| Secret | `GCP_PROJECT_ID` | output of step 5 |
| Secret | `GCP_SERVICE_ACCOUNT` | output of step 5 |
| Secret | `GCP_WIF_PROVIDER` | output of step 5 |
| Variable | `DEPLOY_ENABLED` | `true` |
| Variable (optional) | `GCP_REGION` | defaults to `europe-west1` |
| Variable (optional) | `GCP_ARTIFACT_REPO` | defaults to `cloud-run-deploy` |
| Variable (optional) | `GCP_RUN_SERVICE` | defaults to `classic-jerusalem-realty-api` |

The workflow is **gated on `DEPLOY_ENABLED == 'true'`** — until that
variable is set, every push to main is a no-op for deploy. That way you
can land the workflow file in main today without anything failing, and
flip the switch once GCP is fully provisioned.

After the variable is set, every push to `main` that touches `backend/`:
1. Builds the image and tags it `:<commit-sha>` + `:latest`.
2. Pushes to Artifact Registry.
3. Runs `alembic upgrade head` against prod (DATABASE_URL pulled from Secret Manager at job time, never written to disk).
4. Deploys the new revision to Cloud Run with the same env+secrets as the manual deploy in 1.4.
5. Hits `/health` to confirm the new revision answers.

Manual rollback is unchanged — Cloud Run keeps prior revisions; see Section 5 below.

---

## 2. Admin SPA → Cloudflare Pages

The repo already ships `admin/public/_redirects` (SPA fallback so client-side routes don't 404) and `admin/public/_headers` (security headers + static-asset caching). Both end up in `dist/` on every build automatically.

1. <https://dash.cloudflare.com/?to=/:account/pages> → **Create application → Pages → Connect to Git** → select `MattDevOps/shmuelautomation`.
2. **Set up builds and deployments**:
   - **Production branch**: `main`
   - **Framework preset**: `Vite`
   - **Build command**: `npm run build`
   - **Build output directory**: `dist`
   - **Root directory (advanced)**: `admin`
   - **Environment variables (production)**:
     - `VITE_API_URL=https://api.classicjerusalem.com`
     - `VITE_API_KEY=<the same key generated in §1.5>` — set this as a **Secret** type so it's encrypted at rest in the dashboard. Note: it still gets baked into the JS bundle at build time; the actual confidentiality comes from the Cloudflare Access gate (§2.5) blocking the bundle from anyone outside the allow-list.
3. **Save and Deploy** — first build runs (~30 sec).
4. **Custom domain**: project → Custom domains → **Set up a custom domain** → `admin.classicjerusalem.com`. If the DNS zone is on Cloudflare, the CNAME is added automatically; otherwise it prints the record to add at the registrar.

Subsequent pushes to `main` auto-deploy; PRs get preview URLs.

---

## 2.5 Gate the admin SPA behind Cloudflare Access

The admin tool has no built-in login. We rely on Cloudflare Access (Zero Trust) to gate the URL behind an email-PIN check.

1. Cloudflare → **Zero Trust** dashboard. First-time setup picks a team name (e.g. `classicjerusalem`); pick the **Free** plan (covers up to 50 users).
2. **Access → Applications → Add an application → Self-hosted**:
   - Application name: `Classic Jerusalem Admin`
   - Subdomain: `admin`, Domain: `classicjerusalem.com`, Path: blank
   - Identity providers: **One-time PIN** (default) — sends a 6-digit code to the email address the user enters
3. **Access policies → Add a policy**:
   - Name: `Allowed users`
   - Action: `Allow`
   - Include → Selector: `Emails`, Values: each allowed email on its own row (e.g. `mattstermh@hotmail.com`, `classicjerusaleminfo@gmail.com`)
4. **Save / Add application**.

Verify with `curl -sI https://admin.classicjerusalem.com` — should return `302` to `classicjerusalem.cloudflareaccess.com/cdn-cgi/access/login/...`. That's the gate working.

> **Don't gate the API (`api.classicjerusalem.com`) the same way.** We tried; the SPA's cross-subdomain XHR can't follow Access's redirect chain (CORS-blocked). The Worker `X-API-Key` check (§1.5/§1.6) is what protects the API.

---

## 3. Update the OAuth client

Google Cloud Console → APIs & Services → Credentials → click the OAuth client → add to **Authorized redirect URIs**:

- `https://api.classicjerusalem.com/auth/google/callback`

Keep `http://localhost:8000/auth/google/callback` for local dev.

---

## 4. Sentry — error tracking (optional but recommended)

Both the backend and admin ship the Sentry SDK; they no-op when the DSN env var is empty so dev / CI keep working unchanged. Setup is one-time:

1. Sign up at <https://sentry.io> using Shmuel's email. Free tier covers us comfortably (5k errors/month).
2. **New project → Python → FastAPI** → name it `shmuel-backend` → copy the DSN.
3. **New project → React** → name it `shmuel-admin` → copy that DSN.
4. Add to Cloud Run:
   ```bash
   echo -n "SENTRY_BACKEND_DSN" | gcloud secrets create sentry-dsn --data-file=-
   gcloud run services update classic-jerusalem-realty-api \
     --region europe-west1 \
     --update-secrets "SENTRY_DSN=sentry-dsn:latest"
   ```
5. Add to Cloudflare Pages → project → Settings → **Environment variables**:
   - `VITE_SENTRY_DSN=<the React project DSN>` (Production scope)
   - Trigger a redeploy so the new env is baked in.

After that, any uncaught exception in production fires an alert to Sentry. Configure email/Slack notifications from the Sentry project settings.

## 5. Resend — newsletter delivery (optional)

The newsletter (`/newsletter` admin page, `[classic_newsletter]` WordPress
shortcode) only emails confirmation + digest messages when `RESEND_API_KEY`
is set. With the var unset, signups still record into the DB but no email
goes out — same graceful no-op pattern Sentry uses.

1. Sign up at <https://resend.com>. Verify the `classicjerusalem.com`
   sender domain (DNS TXT/CNAME records — Resend walks you through it).
2. Issue an API key (Server / Production scope).
3. Create the secret in Secret Manager and grant the Cloud Run runtime SA
   read access. The deploy workflow already references the secret +
   env vars, so a redeploy is all it takes after that.
   ```bash
   echo -n "re_xxxxxxxx" | gcloud secrets create resend-api-key --data-file=-
   # Grant the runtime SA (default compute SA) read access:
   PROJECT_NUMBER=$(gcloud projects describe "$(gcloud config get-value project)" --format='value(projectNumber)')
   gcloud secrets add-iam-policy-binding resend-api-key \
     --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
     --role="roles/secretmanager.secretAccessor"
   ```
   Then push (or trigger a redeploy of `deploy-backend.yml`) — Cloud Run
   will pick up the new secret on the next revision.
4. The Next.js rebuild's `SubscribeFloater` is the primary signup
   surface (visible on every page of classicjerusalem.com); it captures
   language + rent/sale preference at signup. The legacy
   `[classic_newsletter]` WP shortcode is kept for rollback but isn't
   placed on the public site since the rebuild went live.

Tweak `NEWSLETTER_DIGEST_THRESHOLD` later if 3 turns out to be too
chatty or too quiet — it's a single env var change, no code redeploy.

## 5.1 OpenAI — content translation (optional)

The public site serves 4 locales (EN/ES/FR/HE). Property descriptions, blog
posts, and neighborhood content are translated via OpenAI gpt-4o-mini and
cached in Supabase's `content_translations` table. Without `OPENAI_API_KEY`,
`/translations/sync` logs would-be calls but writes nothing; non-English
pages render English fallbacks.

- One-time: `echo -n "sk-proj-..." | gcloud secrets create openai-api-key --data-file=-` (already in §1.3 if you ran the full setup) + grant runtime SA `secretAccessor`.
- Run a backfill from your laptop: `cd backend && uv run python scripts/translate_backfill.py` (uses the same `sync_translations()` the admin endpoint uses). Idempotent.
- Or hit `POST /translations/sync` against the live backend after deploy.

## 5.2 WhatsApp daemon — WhatsApp delivery (optional, Phase 2)

The Baileys-based daemon (in `whatsapp-daemon/`) holds the long-lived
WhatsApp connection and exposes a small HTTP API the backend talks to.
Deploy the daemon (Fly.io recommended — see `whatsapp-daemon/README.md`),
then point Cloud Run at it:

```bash
# WHATSAPP_DAEMON_URL — the daemon's private hostname (e.g. its Fly internal
# URL over WireGuard) or its public URL guarded by the shared token.
echo -n "https://shmuel-whatsapp.internal:8787" | \
  gcloud secrets versions add whatsapp-daemon-url --data-file=-

# Shared secret — same value on both sides. Generate with `openssl rand -hex 32`.
echo -n "$(openssl rand -hex 32)" | \
  gcloud secrets versions add whatsapp-daemon-token --data-file=-

gcloud run services update classic-jerusalem-realty-api --region europe-west1   # forces fresh revision
curl -sH "x-api-key: $BACKEND_API_KEY" https://api.classicjerusalem.com/whatsapp/status
# {"configured":true,"reachable":true,"connection_state":"connected",
#  "paired_phone":"972559662779","last_connected_at":"...","last_disconnect_reason":null}
```

First-time pairing: open the admin's WhatsApp panel (or `GET /whatsapp/qr`),
scan the QR with Shmuel's phone, and the daemon will PUT its serialized auth
blob back to `/whatsapp/session/blob` so subsequent restarts skip the QR.

## 6. Smoke test

Run `bash deploy/post-deploy-check.sh` for the full network-level chain (9 checks: backend, admin gating, WP shortcode renderer). Should print `9 passed, 0 failed`.

For a manual user-facing test:

1. Open `https://admin.classicjerusalem.com` — Cloudflare Access prompts for email + PIN. After PIN entry the Properties page loads (no NetworkError in the console).
2. `https://api.classicjerusalem.com/health` returns `{"status": "ok"}` (no key needed; `/health` is in the bypass list).
3. `https://api.classicjerusalem.com/properties` without `X-API-Key` returns `401 Unauthorized` from the Worker.
4. `https://classic-jerusalem-realty-api-PROJECT_NUMBER.europe-west1.run.app/properties` direct without `X-API-Key` also returns `401` (defense-in-depth from the FastAPI middleware).
5. Settings → Connect Google Drive → consent → land back on `?cloud_connected=1`.
6. Create a property → upload a photo → photo appears in admin and on `realestateadmin2025.classicjerusalem.com/listings/`.

---

## Keep-warm during business hours (optional)

Cloud Run scales to zero when idle. The first request after idle takes
~2 sec for the container to warm up — fine, but Shmuel might notice.

The cleanest fix is a **Cloud Scheduler** job that pings `/healthz`
every 10 minutes during business hours. Free tier covers up to 3 jobs.

```bash
# One-time setup:
gcloud services enable cloudscheduler.googleapis.com

gcloud scheduler jobs create http keep-warm \
  --location europe-west1 \
  --schedule "*/10 7-22 * * 0-4,6" \
  --time-zone Asia/Jerusalem \
  --uri "https://api.classicjerusalem.com/healthz" \
  --http-method GET \
  --description "Keep the API container warm during business hours, Sun-Thu + Sat eve"
```

The cron expression `*/10 7-22 * * 0-4,6` means: every 10 minutes,
between 07:00 and 22:00 Jerusalem time, on Sunday through Thursday
plus Saturday (giving the Saturday-night posting slot a warm container).
Friday is intentionally skipped — Shabbat starts at sundown and we don't
post anyway.

Cost stays $0 (Cloud Scheduler free tier covers 3 jobs; Cloud Run free
tier covers the requests). If we ever want to disable it:

```bash
gcloud scheduler jobs delete keep-warm --location europe-west1
```

## Rollback

### Bad code deploy

Cloud Run keeps prior revisions; instant traffic shift, no rebuild needed:

```bash
gcloud run services list-revisions --service classic-jerusalem-realty-api --region europe-west1
gcloud run services update-traffic classic-jerusalem-realty-api \
  --to-revisions PREVIOUS_REVISION_NAME=100 --region europe-west1
```

### Bad migration

Migrations are forward-compatible by convention. If one breaks, downgrade the live DB and redeploy the previous revision:

```bash
# Point at prod DB. Replace VALUE with the Supabase URI.
DATABASE_URL=postgresql+asyncpg://VALUE  uv run alembic downgrade -1
# Then traffic-shift Cloud Run as above.
```

### Accidental data wipe / corruption

Supabase keeps **automatic daily backups** on every project (free tier: 7 days of daily snapshots; Pro tier: 7 days of point-in-time recovery in addition).

To restore:

1. <https://supabase.com/dashboard/project/PROJECT/database/backups> → pick the snapshot before the bad event → **Restore**.
2. The restore creates a *new* database. You either:
   - **(safe)** restore into a new Supabase project, point the backend at it via `gcloud run services update --update-secrets DATABASE_URL=…` to swap connection strings,
   - **(faster but destructive)** overwrite the existing DB. Supabase prompts a typed confirmation.
3. Run `alembic upgrade head` against the restored DB to apply any migrations newer than the backup.

**Hard delete via the admin UI** is `DELETE FROM` for properties / contacts / groups. There's no soft-delete column. Photos are sent to Drive trash (recoverable for 30 days from Drive's UI). If a destructive admin action gets through, the snapshot is the canonical recovery path.

### Disaster preparedness — what to test before launch

Once a quarter, run a **real recovery drill**: pick yesterday's backup, restore into a throwaway Supabase project, point a local dev backend at it, verify the data + photos are intact. If the drill ever fails, our backup story is broken and we find out *before* we need it.

Also worth: download a `pg_dump` from Supabase manually before any major migration push or code change with destructive potential. Backups don't fail you when you have multiple of them.

---

## What this costs (monthly, expected)

| Service | Cost |
| --- | --- |
| Cloud Run | $0 (always-free covers single-user traffic) |
| Cloudflare Pages | $0 (free tier) |
| Cloudflare Workers (api-proxy) | $0 (free tier covers 100k requests/day) |
| Cloudflare Access (Zero Trust) | $0 (free tier covers up to 50 users) |
| Supabase | $0 until ~500 MB of property+contact data; then $25/mo |
| Custom domain | $0 (already paid for `classicjerusalem.com`) |
| **Total expected** | **$0/mo** for at least the first year of single-user usage |
