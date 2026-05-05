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
# Keep pipefail off in check pipelines: `grep -q` exits early on a match,
# which gives upstream curl a SIGPIPE and pipefail flags it as failure.
# We rely on the rightmost command's exit code (the assertion itself).

API="${API:-https://api.classicjerusalem.com}"
ADMIN="${ADMIN:-https://admin.classicjerusalem.com}"
# The WP install that hosts the [classic_listings] shortcode is on the
# realestateadmin2025 subdomain (Namecheap shared hosting). The Vercel-
# rendered public site at classicjerusalem.com pulls its content from
# that WP install via REST, but doesn't itself execute shortcodes.
WP_SITE="${WP_SITE:-https://realestateadmin2025.classicjerusalem.com}"
LISTINGS_PATH="${LISTINGS_PATH:-/listings}"  # WP page hosting [classic_listings]

pass=0
fail=0
check() {
  local label="$1" cmd="$2"
  printf '  %-60s' "$label"
  if (set +o pipefail; eval "$cmd") >/dev/null 2>&1; then
    printf '\033[32mOK\033[0m\n'
    pass=$((pass+1))
  else
    printf '\033[31mFAIL\033[0m\n'
    fail=$((fail+1))
  fi
}

http_status() { curl -fsSL -o /dev/null -w '%{http_code}' "$1"; }

echo
echo "▶ Backend (Cloud Run)"
check "GET ${API}/health → 200" \
  "[ \"\$(http_status ${API}/health)\" = '200' ]"

check "GET ${API}/health body has db: ok" \
  "curl -fsS ${API}/health | grep -q '\"db\":\"ok\"'"

check "GET ${API}/public/properties → 200 with items[]" \
  "curl -fsS ${API}/public/properties | grep -q '\"items\"'"

check "GET ${API}/public/properties has Cache-Control: public" \
  "curl -sS -D - -o /dev/null ${API}/public/properties | grep -iq 'cache-control:.*public'"

# OAuth start should 30x to accounts.google.com — proves the client id
# is wired and the Drive scope is requested. FastAPI uses 307 by default.
check "GET ${API}/auth/google/start → 30x to google.com" \
  "curl -sS --max-redir 0 -D - -o /dev/null ${API}/auth/google/start | grep -iq 'location:.*accounts.google.com'"

echo
echo "▶ Admin SPA (Cloudflare Pages, behind Cloudflare Access)"
# Admin is gated by Cloudflare Access — unauthenticated requests get 302
# to the cloudflareaccess.com login page. That's the correct behavior.
check "GET ${ADMIN}/ → 302 to cloudflareaccess.com (gated)" \
  "curl -sS --max-redir 0 -D - -o /dev/null ${ADMIN}/ | grep -iq 'location:.*cloudflareaccess.com'"

check "GET ${ADMIN}/contacts → 302 to cloudflareaccess.com (gated)" \
  "curl -sS --max-redir 0 -D - -o /dev/null ${ADMIN}/contacts | grep -iq 'location:.*cloudflareaccess.com'"

echo
echo "▶ WordPress (shortcode renderer)"
check "GET ${WP_SITE}${LISTINGS_PATH} → 200" \
  "[ \"\$(http_status ${WP_SITE}${LISTINGS_PATH})\" = '200' ]"

# The plugin renders <article class='cjl-listing'> when properties exist,
# or <p class='cjl-empty'> when the catalog is empty. Either proves the
# shortcode is wired up and the WP→backend chain is reachable.
check "${LISTINGS_PATH} has cjl-* output (plugin live)" \
  "curl -fsSL ${WP_SITE}${LISTINGS_PATH} | grep -qE 'cjl-(listing|empty)'"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf "  %d passed, %d failed\n" "$pass" "$fail"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
exit $(( fail > 0 ? 1 : 0 ))
