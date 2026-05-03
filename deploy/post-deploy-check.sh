#!/usr/bin/env bash
# Smoke test the full production chain after the manual browser steps.
#
# Run this after:
#   1. deploy/bootstrap.sh has succeeded
#   2. CNAME records are live for api.classicjerusalem.com
#   3. Cloudflare Pages is serving admin.classicjerusalem.com
#   4. The OAuth client has the prod redirect URI added
#   5. The WordPress plugin .zip is uploaded + activated + API URL set
#   6. There's at least one available property in the catalog
#
# Hits each layer that real users (Shmuel + WP visitors) will hit, in
# order, and reports a single OK/FAIL per check. Non-destructive — only
# GETs, no DB writes.
set -uo pipefail

API="${API:-https://api.classicjerusalem.com}"
ADMIN="${ADMIN:-https://admin.classicjerusalem.com}"
PUBLIC_SITE="${PUBLIC_SITE:-https://classicjerusalem.com}"
LISTINGS_PATH="${LISTINGS_PATH:-/listings}"  # the page that hosts [classic_listings]

pass=0
fail=0
check() {
  local label="$1" cmd="$2"
  printf '  %-60s' "$label"
  if eval "$cmd" >/dev/null 2>&1; then
    printf '\033[32mOK\033[0m\n'
    pass=$((pass+1))
  else
    printf '\033[31mFAIL\033[0m\n'
    fail=$((fail+1))
  fi
}

http_status() { curl -fsS -o /dev/null -w '%{http_code}' "$1"; }

echo
echo "▶ Backend (Cloud Run)"
check "GET ${API}/health → 200" \
  "[ \"\$(http_status ${API}/health)\" = '200' ]"

check "GET ${API}/health body has db: ok" \
  "curl -fsS ${API}/health | grep -q '\"db\":\"ok\"'"

check "GET ${API}/public/properties → 200 with items[]" \
  "curl -fsS ${API}/public/properties | grep -q '\"items\"'"

check "GET ${API}/public/properties has Cache-Control: public" \
  "curl -sSI ${API}/public/properties | grep -iq 'cache-control:.*public'"

# OAuth start should 30x to accounts.google.com — proves the client id
# is wired and the Drive scope is requested.
check "GET ${API}/auth/google/start → 30x to google.com" \
  "[ \"\$(http_status ${API}/auth/google/start)\" = '302' ] || \
   curl -sSI ${API}/auth/google/start | grep -iq 'location:.*accounts.google.com'"

echo
echo "▶ Admin SPA (Cloudflare Pages)"
check "GET ${ADMIN}/ → 200" \
  "[ \"\$(http_status ${ADMIN}/)\" = '200' ]"

# SPA fallback: deep links should also serve index.html, not 404.
check "GET ${ADMIN}/contacts → 200 (SPA fallback)" \
  "[ \"\$(http_status ${ADMIN}/contacts)\" = '200' ]"

check "${ADMIN} sets X-Frame-Options: DENY" \
  "curl -sSI ${ADMIN}/ | grep -iq 'x-frame-options: DENY'"

check "${ADMIN} hashed assets cached 1y immutable" \
  "curl -sSI ${ADMIN}/assets/ 2>/dev/null | grep -iq 'max-age=31536000' || \
   curl -fsS ${ADMIN}/ | grep -oE '/assets/[^\"]+' | head -1 | \
     xargs -I{} curl -sSI ${ADMIN}{} | grep -iq 'max-age=31536000'"

echo
echo "▶ WordPress public site"
check "GET ${PUBLIC_SITE}${LISTINGS_PATH} → 200" \
  "[ \"\$(http_status ${PUBLIC_SITE}${LISTINGS_PATH})\" = '200' ]"

# The plugin's shortcode renders <article class='cjl-listing'> rows.
# If we see at least one, the WP→backend chain is live.
check "${LISTINGS_PATH} has at least one cjl-listing rendered" \
  "curl -fsS ${PUBLIC_SITE}${LISTINGS_PATH} | grep -q 'cjl-listing'"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf "  %d passed, %d failed\n" "$pass" "$fail"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
exit $(( fail > 0 ? 1 : 0 ))
