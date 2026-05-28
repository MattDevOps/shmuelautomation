#!/usr/bin/env bash
# One-shot: import the website's available apartments into the PRODUCTION
# backend, pulling live secrets from GCP Secret Manager.
#
# Prereq: `gcloud` authenticated on the project (classic-jerusalem-realty)
# and — for photos — Google Drive connected in the admin Settings page.
#
# Usage (from backend/):
#   bash scripts/import_prod.sh --dry-run                 # preview, no writes
#   bash scripts/import_prod.sh --photos --max-photos 12  # real import + photos
#   bash scripts/import_prod.sh                           # data only, no photos
#
# It is idempotent — safe to re-run; it skips listings/photos already imported.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Pulling production secrets from Secret Manager..."
export DATABASE_URL="$(gcloud secrets versions access latest --secret=database-url)"
export ENCRYPTION_KEY="$(gcloud secrets versions access latest --secret=encryption-key)"
export GOOGLE_OAUTH_CLIENT_ID="$(gcloud secrets versions access latest --secret=google-oauth-client-id)"
export GOOGLE_OAUTH_CLIENT_SECRET="$(gcloud secrets versions access latest --secret=google-oauth-client-secret)"
export ENVIRONMENT="production"

echo "Running importer against production..."
uv run python scripts/import_wp_properties.py "$@"
