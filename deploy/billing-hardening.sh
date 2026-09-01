#!/usr/bin/env bash
#
# billing-hardening.sh — run ONCE after the billing account is restored.
#
# The August 2026 outage was not caused by a bug: the billing account closed,
# Google switched the project off, and nobody found out for weeks because
# nothing was watching. This script fixes the "nobody found out" half and
# takes the secrets hostage-situation off the table.
#
#   1. refuses to run until billing is actually enabled
#   2. enables the budget + monitoring APIs
#   3. creates a monthly budget with 50/90/100% email alerts
#   4. creates an uptime check on the API + an alert that emails within minutes
#   5. backs up every Secret Manager value to an offline file (chmod 600)
#   6. proves the production database is reachable
#
# Usage:
#   deploy/billing-hardening.sh                          # uses defaults below
#   ALERT_EMAIL=you@x.com BUDGET_ILS=300 deploy/billing-hardening.sh
#
set -euo pipefail

PROJECT="classic-jerusalem-realty"
REGION="europe-west1"
BILLING_ACCOUNT="${BILLING_ACCOUNT:-}"           # auto-detected if empty
ALERT_EMAIL="${ALERT_EMAIL:-classicjerusaleminfo@gmail.com}"
BUDGET_ILS="${BUDGET_ILS:-250}"
API_HOST="api.classicjerusalem.com"
BACKUP_DIR="${BACKUP_DIR:-$HOME/.classic-jerusalem-secrets}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bold(){ printf '\n\033[1m%s\033[0m\n' "$*"; }
ok(){   printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn(){ printf '  \033[33m!\033[0m %s\n' "$*"; }
info(){ printf '  · %s\n' "$*"; }
die(){  printf '\n\033[31mSTOP:\033[0m %s\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------------ 1. gate
bold "1/6  Is billing actually on?"
BILLING="$(gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)' 2>/dev/null || echo ERROR)"
[[ "$BILLING" == "True" ]] || die "billing is still disabled on $PROJECT. Link an open billing account first, then re-run."
ok "billing enabled"

if [[ -z "$BILLING_ACCOUNT" ]]; then
  BILLING_ACCOUNT="$(gcloud billing projects describe "$PROJECT" --format='value(billingAccountName)' | sed 's|billingAccounts/||')"
fi
[[ -n "$BILLING_ACCOUNT" ]] || die "could not determine the billing account id."
ok "billing account $BILLING_ACCOUNT"

# ------------------------------------------------------------------ 2. apis
bold "2/6  Enable the APIs this needs"
gcloud services enable billingbudgets.googleapis.com monitoring.googleapis.com \
  --project "$PROJECT" >/dev/null 2>&1 && ok "billingbudgets + monitoring enabled" \
  || warn "could not enable APIs — enable them by hand if the steps below fail"

# ----------------------------------------------------------------- 3. budget
bold "3/6  Monthly budget with alerts"
BUDGET_NAME="classic-jerusalem monthly"
if gcloud billing budgets list --billing-account="$BILLING_ACCOUNT" \
     --format='value(displayName)' 2>/dev/null | grep -qx "$BUDGET_NAME"; then
  ok "budget \"$BUDGET_NAME\" already exists — leaving it alone"
else
  # Default IAM recipients = every Billing Account Admin gets the mail. That is
  # deliberate: the point is that a human hears about it.
  gcloud billing budgets create \
    --billing-account="$BILLING_ACCOUNT" \
    --display-name="$BUDGET_NAME" \
    --budget-amount="${BUDGET_ILS}ILS" \
    --filter-projects="projects/$PROJECT" \
    --calendar-period=month \
    --threshold-rule=percent=0.5 \
    --threshold-rule=percent=0.9 \
    --threshold-rule=percent=1.0 >/dev/null \
    && ok "budget created at ${BUDGET_ILS} ILS/month (alerts at 50/90/100%)" \
    || warn "budget creation failed — create it in the console, it is one form"
fi
info "a budget only WARNS. Never wire it to auto-disable billing."

# ------------------------------------------------------- 4. uptime + alerting
bold "4/6  Watch the API so an outage is noticed in minutes"

TOKEN="$(gcloud auth print-access-token)"
CHANNEL="$(curl -s -H "Authorization: Bearer $TOKEN" \
  "https://monitoring.googleapis.com/v3/projects/$PROJECT/notificationChannels" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin) or {}
for c in d.get('notificationChannels',[]):
    if c.get('type')=='email' and c.get('labels',{}).get('email_address')=='$ALERT_EMAIL':
        print(c['name']); break
" 2>/dev/null || true)"

if [[ -z "$CHANNEL" ]]; then
  CHANNEL="$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    "https://monitoring.googleapis.com/v3/projects/$PROJECT/notificationChannels" \
    -d "{\"type\":\"email\",\"displayName\":\"Classic Jerusalem alerts\",\"labels\":{\"email_address\":\"$ALERT_EMAIL\"}}" \
    | python3 -c "import json,sys; print((json.load(sys.stdin) or {}).get('name',''))" 2>/dev/null || true)"
fi
[[ -n "$CHANNEL" ]] && ok "email alerts go to $ALERT_EMAIL" || warn "could not create the email notification channel"

UPTIME_NAME="api-health"
if gcloud monitoring uptime list-configs --project "$PROJECT" \
     --format='value(displayName)' 2>/dev/null | grep -qx "$UPTIME_NAME"; then
  ok "uptime check \"$UPTIME_NAME\" already exists"
else
  gcloud monitoring uptime create "$UPTIME_NAME" \
    --project "$PROJECT" \
    --resource-type=uptime-url \
    --resource-labels="host=$API_HOST,project_id=$PROJECT" \
    --path="/health" --port=443 --protocol=https --period=5 >/dev/null \
    && ok "uptime check on https://$API_HOST/health every 5 min" \
    || warn "uptime check creation failed — add it in Monitoring > Uptime checks"
fi

if [[ -n "$CHANNEL" ]]; then
  POLICY_JSON="$(mktemp)"
  cat > "$POLICY_JSON" <<JSON
{
  "displayName": "API is down",
  "combiner": "OR",
  "conditions": [{
    "displayName": "uptime check failing",
    "conditionThreshold": {
      "filter": "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\"",
      "aggregations": [{
        "alignmentPeriod": "300s",
        "perSeriesAligner": "ALIGN_NEXT_OLDER",
        "crossSeriesReducer": "REDUCE_COUNT_FALSE",
        "groupByFields": ["resource.label.host"]
      }],
      "comparison": "COMPARISON_GT",
      "thresholdValue": 1,
      "duration": "300s",
      "trigger": {"count": 1}
    }
  }],
  "notificationChannels": ["$CHANNEL"],
  "alertStrategy": {"autoClose": "1800s"}
}
JSON
  if gcloud alpha monitoring policies list --project "$PROJECT" \
       --format='value(displayName)' 2>/dev/null | grep -qx "API is down"; then
    ok "alert policy \"API is down\" already exists"
  else
    curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      "https://monitoring.googleapis.com/v3/projects/$PROJECT/alertPolicies" \
      -d @"$POLICY_JSON" >/dev/null \
      && ok "alert policy created — you get an email when /health stops answering" \
      || warn "alert policy creation failed — wire the uptime check to the channel in the console"
  fi
  rm -f "$POLICY_JSON"
fi

# -------------------------------------------------------- 5. secrets backup
bold "5/6  Take the secrets off the critical path"
info "ENCRYPTION_KEY decrypts the stored Google Drive token. If Secret Manager"
info "is ever deleted with no copy, that token — and the photo integration — is gone."

mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"
STAMP="$(date +%Y%m%d)"
OUT="$BACKUP_DIR/secrets-$STAMP.env"
umask 077
: > "$OUT"
COUNT=0
while read -r NAME; do
  [[ -z "$NAME" ]] && continue
  VAL="$(gcloud secrets versions access latest --secret="$NAME" --project="$PROJECT" 2>/dev/null || true)"
  if [[ -n "$VAL" ]]; then
    printf '%s=%s\n' "$NAME" "$VAL" >> "$OUT"
    COUNT=$((COUNT+1))
  fi
done < <(gcloud secrets list --project="$PROJECT" --format='value(name)' 2>/dev/null)
chmod 600 "$OUT"
[[ $COUNT -gt 0 ]] && ok "$COUNT secrets backed up to $OUT (chmod 600)" || warn "no secrets read — check permissions"
info "keep a copy somewhere off this laptop (password manager, encrypted drive)."

# --------------------------------------------------------- 6. prove the DB
bold "6/6  Is the production database still there?"
DB_URL="$(gcloud secrets versions access latest --secret=database-url --project="$PROJECT" 2>/dev/null || true)"
if [[ -z "$DB_URL" ]]; then
  warn "could not read the database-url secret — skipping the check"
else
  DB_URL="$DB_URL" "$REPO_ROOT/backend/.venv/bin/python" - <<'PY' || warn "database check failed — see the error above"
import asyncio, os, asyncpg
url = os.environ["DB_URL"].replace("postgresql+asyncpg://", "postgresql://")
async def main():
    c = await asyncpg.connect(url, timeout=20, statement_cache_size=0)
    for q, label in [("select count(*) from properties", "properties"),
                     ("select count(*) from cloud_photos", "photos"),
                     ("select count(*) from contacts", "contacts")]:
        try:
            print(f"  \033[32m✓\033[0m {label}: {await c.fetchval(q)}")
        except Exception as e:
            print(f"  \033[33m!\033[0m {label}: {type(e).__name__}")
    await c.close()
asyncio.run(main())
PY
fi

bold "Hardening done."
cat <<MSG

  Still worth doing by hand, in the billing console — a script cannot add a card:
    · add a SECOND payment method as backup (an expiring card is the usual cause)
    · check the billing contact email is one somebody reads
    · add a second Billing Account Administrator, so warnings never go to one inbox

  Next: deploy/whatsapp-golive.sh
MSG
