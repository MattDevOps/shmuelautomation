#!/usr/bin/env bash
# Idempotent one-shot GCP-side bootstrap for the realty backend.
#
# Runs the technical pieces of DEPLOY.md §1.1, §1.3, §1.4, §1.5, §1.6
# in sequence: enable APIs, create the Artifact Registry repo, push
# secrets to Secret Manager, run migrations against prod, deploy the
# first Cloud Run revision, map the custom domain, and set up
# Workload Identity Federation so GitHub Actions can deploy on push.
#
# Skipped from automation (web UI only):
#   §1.2  Supabase project creation. Provision it manually first and
#         pass DATABASE_URL into this script.
#   §2    Cloudflare Pages for the admin SPA — Cloudflare's GitHub
#         integration is dashboard-driven; do that step in a browser.
#
# Re-run safe: every gcloud action checks existence first or uses
# add-iam-policy-binding (which is itself idempotent).
#
# Required env (set before running):
#   PROJECT_ID                e.g. classic-jerusalem-realty-12345
#   DATABASE_URL              Supabase pooler URL with postgresql+asyncpg:// scheme
#   GITHUB_REPO               e.g. MattDevOps/shmuelautomation
#
# Optional (auto-loaded from backend/.env if present):
#   GOOGLE_OAUTH_CLIENT_ID
#   GOOGLE_OAUTH_CLIENT_SECRET
#   ENCRYPTION_KEY            (auto-generated via Fernet if missing)
#
# Optional defaults:
#   REGION                    me-west1
#   ARTIFACT_REPO             cloud-run-deploy
#   SERVICE                   classic-jerusalem-realty-api
#   API_DOMAIN                api.classicjerusalem.com
#   ADMIN_DOMAIN              admin.classicjerusalem.com
set -euo pipefail

# ─── Defaults ────────────────────────────────────────────────────────
REGION="${REGION:-me-west1}"
ARTIFACT_REPO="${ARTIFACT_REPO:-cloud-run-deploy}"
SERVICE="${SERVICE:-classic-jerusalem-realty-api}"
API_DOMAIN="${API_DOMAIN:-api.classicjerusalem.com}"
ADMIN_DOMAIN="${ADMIN_DOMAIN:-admin.classicjerusalem.com}"
SA_NAME="${SA_NAME:-github-deploy}"
POOL="${POOL:-github-pool}"
PROVIDER="${PROVIDER:-github-provider}"

# ─── Pretty-print helpers ────────────────────────────────────────────
step()  { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn()  { printf '  \033[33m!\033[0m %s\n' "$*"; }

# ─── Auto-load local .env so we can borrow OAuth client / encryption key
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$REPO_ROOT/backend/.env" ]]; then
  # shellcheck disable=SC1091
  set -a; source "$REPO_ROOT/backend/.env"; set +a
fi

# ─── Validation ──────────────────────────────────────────────────────
required=(PROJECT_ID DATABASE_URL GITHUB_REPO)
missing=()
for v in "${required[@]}"; do
  [[ -z "${!v:-}" ]] && missing+=("$v")
done
if (( ${#missing[@]} > 0 )); then
  echo "error: missing required env: ${missing[*]}" >&2
  echo "see 'head -50 deploy/bootstrap.sh' for the full env reference." >&2
  exit 1
fi

if [[ -z "${GOOGLE_OAUTH_CLIENT_ID:-}" || -z "${GOOGLE_OAUTH_CLIENT_SECRET:-}" ]]; then
  echo "error: GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET not in env or backend/.env." >&2
  exit 1
fi

if ! command -v gcloud >/dev/null; then
  echo "error: gcloud CLI not installed. https://cloud.google.com/sdk/docs/install" >&2
  exit 1
fi

if [[ -z "${ENCRYPTION_KEY:-}" ]]; then
  warn "no ENCRYPTION_KEY set; generating a fresh Fernet key"
  ENCRYPTION_KEY=$(python3 -c \
    "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  echo "  → save this for your records: $ENCRYPTION_KEY"
fi

gcloud config set project "$PROJECT_ID" >/dev/null

# ─── 1. APIs ─────────────────────────────────────────────────────────
step "1/8  Enable required APIs"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  >/dev/null
ok "APIs enabled"

# ─── 2. Artifact Registry ────────────────────────────────────────────
step "2/8  Artifact Registry repo"
if gcloud artifacts repositories describe "$ARTIFACT_REPO" \
    --location="$REGION" >/dev/null 2>&1; then
  ok "repo $ARTIFACT_REPO already exists"
else
  gcloud artifacts repositories create "$ARTIFACT_REPO" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Cloud Run images for the realty backend" >/dev/null
  ok "created $ARTIFACT_REPO"
fi

# ─── 3. Secret Manager ───────────────────────────────────────────────
step "3/8  Push secrets to Secret Manager"
push_secret() {
  local name="$1" value="$2"
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
    ok "$name (added new version)"
  else
    printf '%s' "$value" | gcloud secrets create "$name" --data-file=- >/dev/null
    ok "$name (created)"
  fi
}
push_secret encryption-key             "$ENCRYPTION_KEY"
push_secret database-url               "$DATABASE_URL"
push_secret google-oauth-client-id     "$GOOGLE_OAUTH_CLIENT_ID"
push_secret google-oauth-client-secret "$GOOGLE_OAUTH_CLIENT_SECRET"

# ─── 4. Migrations ───────────────────────────────────────────────────
step "4/8  Run alembic migrations against prod"
( cd "$REPO_ROOT/backend" && DATABASE_URL="$DATABASE_URL" uv run alembic upgrade head )
ok "schema up to date"

# ─── 5. First deploy ─────────────────────────────────────────────────
step "5/8  First Cloud Run deploy (≈3-4 min)"
( cd "$REPO_ROOT/backend" && gcloud run deploy "$SERVICE" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --min-instances 0 --max-instances 4 \
    --memory 512Mi --cpu 1 --port 8000 \
    --set-env-vars "ENVIRONMENT=production,CORS_ORIGINS=[\"https://${ADMIN_DOMAIN}\"],GOOGLE_OAUTH_REDIRECT_URI=https://${API_DOMAIN}/auth/google/callback,ADMIN_REDIRECT_URI=https://${ADMIN_DOMAIN}/settings" \
    --set-secrets "ENCRYPTION_KEY=encryption-key:latest,GOOGLE_OAUTH_CLIENT_ID=google-oauth-client-id:latest,GOOGLE_OAUTH_CLIENT_SECRET=google-oauth-client-secret:latest,DATABASE_URL=database-url:latest" \
    >/dev/null )
SERVICE_URL=$(gcloud run services describe "$SERVICE" \
  --region "$REGION" --format='value(status.url)')
ok "live at $SERVICE_URL"

# ─── 6. Domain mapping ───────────────────────────────────────────────
step "6/8  Map custom domain $API_DOMAIN"
if gcloud beta run domain-mappings describe \
    --domain "$API_DOMAIN" --region "$REGION" >/dev/null 2>&1; then
  ok "domain mapping already exists"
else
  gcloud beta run domain-mappings create \
    --service "$SERVICE" \
    --domain "$API_DOMAIN" \
    --region "$REGION" >/dev/null
  ok "domain mapping created — see DNS records below"
fi

# ─── 7. WIF — service account + roles ────────────────────────────────
step "7/8  Service account + IAM roles for GitHub Actions"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
if gcloud iam service-accounts describe "$SA_EMAIL" >/dev/null 2>&1; then
  ok "service account $SA_NAME exists"
else
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="GitHub Actions deployer" >/dev/null
  ok "created $SA_NAME"
fi

for ROLE in roles/run.developer \
            roles/iam.serviceAccountUser \
            roles/artifactregistry.writer \
            roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE" \
    --condition=None \
    --quiet >/dev/null
  ok "role $ROLE bound"
done

# Cloud Run runtime uses the project's default compute SA; the deployer
# needs to act as that SA on deploy. Bind the iam.serviceAccountUser
# role on the runtime SA itself, scoped to the deployer.
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.serviceAccountUser" \
  --quiet >/dev/null
ok "deployer can act as runtime SA"

# ─── 8. WIF — pool + provider + repo binding ─────────────────────────
step "8/8  Workload Identity Federation pool + provider"
if gcloud iam workload-identity-pools describe "$POOL" \
    --location=global >/dev/null 2>&1; then
  ok "pool $POOL exists"
else
  gcloud iam workload-identity-pools create "$POOL" \
    --location=global --display-name="GitHub Actions" >/dev/null
  ok "created pool $POOL"
fi

if gcloud iam workload-identity-pools providers describe "$PROVIDER" \
    --location=global --workload-identity-pool="$POOL" >/dev/null 2>&1; then
  ok "provider $PROVIDER exists"
else
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
    --location=global \
    --workload-identity-pool="$POOL" \
    --display-name="GitHub OIDC" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="attribute.repository=='${GITHUB_REPO}'" \
    --issuer-uri="https://token.actions.githubusercontent.com" >/dev/null
  ok "created provider $PROVIDER"
fi

POOL_ID="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}"
PROVIDER_ID="${POOL_ID}/providers/${PROVIDER}"

gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${GITHUB_REPO}" \
  --quiet >/dev/null
ok "github repo $GITHUB_REPO bound to deployer"

# ─── DONE ────────────────────────────────────────────────────────────
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓ Backend live: $SERVICE_URL"
echo "  ✓ Health:       ${SERVICE_URL}/health"
echo
echo "  Paste at github.com/${GITHUB_REPO}/settings/secrets/actions:"
echo
echo "    Repository secrets:"
echo "      GCP_PROJECT_ID       = ${PROJECT_ID}"
echo "      GCP_SERVICE_ACCOUNT  = ${SA_EMAIL}"
echo "      GCP_WIF_PROVIDER     = ${PROVIDER_ID}"
echo
echo "    Repository variables:"
echo "      DEPLOY_ENABLED       = true"
echo "      GCP_REGION           = ${REGION}             (optional, default)"
echo "      GCP_ARTIFACT_REPO    = ${ARTIFACT_REPO}      (optional, default)"
echo "      GCP_RUN_SERVICE      = ${SERVICE}            (optional, default)"
echo
echo "  Manual remaining (browser-only):"
echo "    1. Add CNAMEs printed by the domain mapping above to Cloudflare DNS:"
echo "         gcloud beta run domain-mappings describe \\"
echo "           --domain ${API_DOMAIN} --region ${REGION}"
echo "    2. Cloudflare Pages: connect the repo, set VITE_API_URL=https://${API_DOMAIN}"
echo "       (DEPLOY.md §2)."
echo "    3. Add https://${API_DOMAIN}/auth/google/callback to the OAuth client"
echo "       (DEPLOY.md §3)."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
