# Deploy runbook

Step-by-step for cutting over from `localhost` to production.

**Prereqs:**
- Shmuel has added a credit card to the Google Cloud billing account (one-time).
- You have `gcloud` installed locally and are authenticated as `classicjerusaleminfo@gmail.com` (the Google account that owns the GCP project).
- You have access to the Cloudflare account that manages `classicjerusalem.com` DNS (or Shmuel adds the records when prompted).

The Google Cloud project ID below comes from the existing OAuth setup. Replace `PROJECT_ID` with the actual one — find it at <https://console.cloud.google.com/home/dashboard>.

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
```

### 1.4 Deploy

```bash
cd backend
gcloud run deploy classic-jerusalem-realty-api \
  --source . \
  --region me-west1 \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 4 \
  --memory 512Mi \
  --cpu 1 \
  --port 8000 \
  --set-env-vars "ENVIRONMENT=production,CORS_ORIGINS=[\"https://admin.classicjerusalem.com\"],GOOGLE_OAUTH_REDIRECT_URI=https://api.classicjerusalem.com/auth/google/callback,ADMIN_REDIRECT_URI=https://admin.classicjerusalem.com/settings" \
  --set-secrets "ENCRYPTION_KEY=encryption-key:latest,GOOGLE_OAUTH_CLIENT_ID=google-oauth-client-id:latest,GOOGLE_OAUTH_CLIENT_SECRET=google-oauth-client-secret:latest,DATABASE_URL=database-url:latest"
```

This builds the Dockerfile in Cloud Build, pushes to Artifact Registry, and deploys. First deploy takes ~3–4 minutes; subsequent ones are ~1 minute.

The command outputs a URL like `https://classic-jerusalem-realty-api-xxxx-mw.a.run.app`. Hit `/health` to confirm:

```bash
curl https://<that-url>/health
# {"status":"ok","environment":"production","db":"ok"}
```

### 1.5 Map the custom domain

```bash
gcloud run domain-mappings create \
  --service classic-jerusalem-realty-api \
  --domain api.classicjerusalem.com \
  --region me-west1
```

It prints CNAME records to add. Add them in the Cloudflare DNS for `classicjerusalem.com`. SSL is provisioned automatically; takes ~10 minutes.

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
   - **Environment variables (production)**: `VITE_API_URL=https://api.classicjerusalem.com`
3. **Save and Deploy** — first build runs (~30 sec).
4. **Custom domain**: project → Custom domains → **Set up a custom domain** → `admin.classicjerusalem.com`. If the DNS zone is on Cloudflare, the CNAME is added automatically; otherwise it prints the record to add at the registrar.

Subsequent pushes to `main` auto-deploy; PRs get preview URLs.

---

## 3. Update the OAuth client

Google Cloud Console → APIs & Services → Credentials → click the OAuth client → add to **Authorized redirect URIs**:

- `https://api.classicjerusalem.com/auth/google/callback`

Keep `http://localhost:8000/auth/google/callback` for local dev.

---

## 4. Smoke test

1. Open `https://admin.classicjerusalem.com` — Properties page loads.
2. `https://api.classicjerusalem.com/health` returns `{"status": "ok"}`.
3. Settings → Connect Google Drive → consent → land back on `?cloud_connected=1`.
4. Create a property → upload a photo → photo appears.

---

## Rollback

```bash
gcloud run services list-revisions --service classic-jerusalem-realty-api --region me-west1
gcloud run services update-traffic classic-jerusalem-realty-api \
  --to-revisions PREVIOUS_REVISION_NAME=100 --region me-west1
```

DB migrations are forward-compatible by convention — if a migration breaks, run `alembic downgrade -1` against the prod DB and redeploy the previous revision.

---

## What this costs (monthly, expected)

| Service | Cost |
| --- | --- |
| Cloud Run | $0 (always-free covers single-user traffic) |
| Cloudflare Pages | $0 (free tier) |
| Supabase | $0 until ~500 MB of property+contact data; then $25/mo |
| Custom domain | $0 (already paid for `classicjerusalem.com`) |
| **Total expected** | **$0/mo** for at least the first year of single-user usage |
