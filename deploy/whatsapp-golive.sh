#!/usr/bin/env bash
#
# whatsapp-golive.sh — one command to take the WhatsApp daemon live on
# Shmuel's dedicated 2nd number.
#
# Everything here is idempotent: re-running it re-deploys the daemon and
# re-points the backend without touching the WhatsApp pairing (the auth
# blob lives in Postgres, not on the Fly machine).
#
# Usage:
#   deploy/whatsapp-golive.sh            # full go-live
#   deploy/whatsapp-golive.sh --check    # preflight only, changes nothing
#
set -euo pipefail

PROJECT="classic-jerusalem-realty"
REGION="europe-west1"
SERVICE="classic-jerusalem-realty-api"
FLY_APP="shmuel-whatsapp"
# Fly org to deploy into, by API SLUG (not the display name, and not the
# vanity path in the dashboard URL — for Shmuel's org those are "Classic
# Jerusalem", "/dashboard/classic-jerusalem/" and "personal" respectively).
# Find it with: flyctl orgs list --json
#
# "personal" is only correct here because FLY_ACCESS_TOKEN is scoped to
# Shmuel's own Fly account, so his personal org is the business org and his
# card is the one on it. Deploying to a personal org under anyone else's
# login would put this client's infra on the wrong card.
FLY_ORG="${FLY_ORG:-personal}"
API_BASE="https://api.classicjerusalem.com"
ADMIN_URL="https://admin.classicjerusalem.com"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; }
info() { printf '  · %s\n' "$*"; }
die()  { printf '\n\033[31mSTOP:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight
bold "1/6  Preflight"

command -v gcloud  >/dev/null || die "gcloud not installed."
command -v flyctl  >/dev/null || die "flyctl not installed (https://fly.io/docs/flyctl/install/)."
command -v openssl >/dev/null || die "openssl not installed."
ok "gcloud, flyctl, openssl present"

gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q . \
  || die "gcloud not logged in. Run: gcloud auth login"
ok "gcloud authenticated as $(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -1)"

# The whole stack is dead without billing — check it first, it is the most
# common reason everything below fails with confusing permission errors.
BILLING="$(gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)' 2>/dev/null || echo 'ERROR')"
if [[ "$BILLING" != "True" ]]; then
  bad "GCP billing is DISABLED on $PROJECT — the backend, admin and database are offline."
  cat <<'MSG'

     Fix this first (5 minutes, Shmuel's card):
       1. https://console.cloud.google.com/billing  → sign in as
          classicjerusaleminfo@gmail.com
       2. Reopen / re-add the billing account (add a valid card).
       3. https://console.cloud.google.com/billing/linkedaccount?project=classic-jerusalem-realty
          → link the account to the project.
       4. Re-run this script.

MSG
  die "Billing must be enabled before anything else can work."
fi
ok "GCP billing enabled"

flyctl auth whoami >/dev/null 2>&1 \
  || die "flyctl not logged in. Run: flyctl auth login   (use SHMUEL'S Fly account — infra goes on his card)"
ok "Fly authenticated as $(flyctl auth whoami 2>/dev/null)"

if [[ $CHECK_ONLY -eq 1 ]]; then
  bold "Preflight passed. Re-run without --check to go live."
  exit 0
fi

# ------------------------------------------------------------ shared token
bold "2/6  Shared daemon token"

# Reuse the existing token if one is already stored, so re-running the script
# never breaks a backend that is already talking to a live daemon.
EXISTING_TOKEN="$(gcloud secrets versions access latest --secret=whatsapp-daemon-token \
                    --project="$PROJECT" 2>/dev/null || true)"
if [[ -n "$EXISTING_TOKEN" && ${#EXISTING_TOKEN} -eq 64 ]]; then
  DAEMON_TOKEN="$EXISTING_TOKEN"
  ok "reusing existing 64-char token from Secret Manager"
else
  DAEMON_TOKEN="$(openssl rand -hex 32)"
  ok "generated a new 64-char token"
fi

BACKEND_API_KEY="$(gcloud secrets versions access latest --secret=backend-api-key \
                     --project="$PROJECT" 2>/dev/null || true)"
[[ -n "$BACKEND_API_KEY" ]] || die "Could not read the backend-api-key secret."
ok "read backend API key"

# ------------------------------------------------------------- deploy fly
bold "3/6  Deploy the daemon to Fly ($FLY_APP)"

cd "$REPO_ROOT/whatsapp-daemon"

# Match on the JSON keys: the table output can't be parsed positionally
# because display names contain spaces ("Classic Jerusalem" -> $2 = "Jerusalem").
FLY_ORG_NAME="$(flyctl orgs list --json 2>/dev/null \
  | python3 -c "import json,sys; print((json.load(sys.stdin) or {}).get('$FLY_ORG',''))" 2>/dev/null || true)"
[[ -n "$FLY_ORG_NAME" ]] \
  || die "Fly org slug '$FLY_ORG' not visible to this token. Run: flyctl orgs list --json"
ok "target org $FLY_ORG (\"$FLY_ORG_NAME\")"

# --org is required when creating non-interactively, and picking it explicitly
# is what keeps this off a personal account.
# Match on JSON, not the table: the table is box-drawn and every row is
# indented, so an anchored "^$FLY_APP" grep silently never matches and we
# try to create an app that already exists.
if flyctl apps list --json 2>/dev/null \
   | python3 -c "import json,sys; sys.exit(0 if any(a.get('Name')=='$FLY_APP' for a in (json.load(sys.stdin) or [])) else 1)" 2>/dev/null; then
  ok "app $FLY_APP already exists — deploying over it"
else
  info "creating Fly app $FLY_APP in org $FLY_ORG"
  flyctl apps create "$FLY_APP" --org "$FLY_ORG" --machines
fi

flyctl secrets set --app "$FLY_APP" --stage \
  DAEMON_AUTH_TOKEN="$DAEMON_TOKEN" \
  BACKEND_BASE_URL="$API_BASE" \
  BACKEND_API_KEY="$BACKEND_API_KEY" >/dev/null
ok "Fly secrets staged"

flyctl deploy --app "$FLY_APP" --now
ok "daemon deployed"

DAEMON_URL="https://${FLY_APP}.fly.dev"

# Wait for the health check rather than assuming the machine is up.
info "waiting for $DAEMON_URL/health"
for i in $(seq 1 30); do
  if curl -fsS --max-time 5 "$DAEMON_URL/health" >/dev/null 2>&1; then
    ok "daemon healthy"
    break
  fi
  [[ $i -eq 30 ]] && die "daemon never became healthy. Check: flyctl logs --app $FLY_APP"
  sleep 4
done

# --------------------------------------------------- point the backend at it
bold "4/6  Point the backend at the real daemon"

printf '%s' "$DAEMON_URL"    | gcloud secrets versions add whatsapp-daemon-url   --data-file=- --project="$PROJECT" >/dev/null
printf '%s' "$DAEMON_TOKEN"  | gcloud secrets versions add whatsapp-daemon-token --data-file=- --project="$PROJECT" >/dev/null
ok "secrets updated (url=$DAEMON_URL)"

gcloud run services update "$SERVICE" \
  --region "$REGION" --project "$PROJECT" \
  --update-secrets "WHATSAPP_DAEMON_URL=whatsapp-daemon-url:latest,WHATSAPP_DAEMON_TOKEN=whatsapp-daemon-token:latest" \
  --quiet >/dev/null
ok "Cloud Run rolled to a fresh revision"

# ------------------------------------------------------------------ verify
bold "5/6  Verify the backend can see the daemon"

sleep 5
STATUS="$(curl -fsS --max-time 20 -H "x-api-key: $BACKEND_API_KEY" "$API_BASE/whatsapp/status" || echo '')"
[[ -n "$STATUS" ]] || die "GET $API_BASE/whatsapp/status returned nothing. Check Cloud Run logs."
echo "     $STATUS"

echo "$STATUS" | grep -q '"configured":true' || die "backend reports configured=false"
echo "$STATUS" | grep -q '"reachable":true'  || die "backend cannot reach the daemon — check the token matches on both sides."
ok "backend ↔ daemon handshake works"

# -------------------------------------------------------------- pair the phone
bold "6/6  Pair the new number"
cat <<MSG

  The plumbing is live. The last step is physical and only Shmuel can do it:

    1. On the NEW business phone: install WhatsApp, register the new number,
       set the business name + logo as the profile.
    2. On a computer, open  $ADMIN_URL  → Settings.
       A QR code appears in the WhatsApp section.
    3. On the new phone: WhatsApp → Settings → Linked Devices → Link a device
       → scan that QR.
    4. The card turns green and shows the paired number. Done — the pairing
       survives restarts and redeploys.

  Then, still in the admin:
    · Groups page  — paste each WhatsApp group so posts have somewhere to go.
                     (A group with no target set is skipped at send time.)
    · Chatbot page — flip the bot ON once you are happy with the greeting.

  Re-check status any time:
    curl -sH "x-api-key: \$BACKEND_API_KEY" $API_BASE/whatsapp/status

MSG
bold "Go-live script finished."
