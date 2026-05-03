#!/usr/bin/env bash
# Builds an install-ready WordPress plugin .zip in dist/.
# WP expects: zip extracts into a single directory named after the
# plugin slug, with the main PHP file at the top level of that dir.
set -euo pipefail

cd "$(dirname "$0")"

SLUG="classic-jerusalem-listings"
SRC="$SLUG"
DIST="dist"

if [[ ! -d "$SRC" ]]; then
  echo "error: $SRC/ does not exist" >&2
  exit 1
fi

VERSION=$(grep -E "^[[:space:]]*\*[[:space:]]*Version:" "$SRC/$SLUG.php" | head -1 | sed -E 's/.*Version:[[:space:]]*//; s/[[:space:]]*$//')
if [[ -z "$VERSION" ]]; then
  echo "error: could not extract Version from $SRC/$SLUG.php" >&2
  exit 1
fi

# php -l on every PHP file before bundling — catches syntax errors that
# would otherwise blow up on Shmuel's site at activation time.
if command -v php >/dev/null 2>&1; then
  while IFS= read -r f; do
    php -l "$f" >/dev/null
  done < <(find "$SRC" -name "*.php")
else
  echo "warning: php not installed, skipping syntax check" >&2
fi

mkdir -p "$DIST"
ZIP="$DIST/$SLUG-$VERSION.zip"
rm -f "$ZIP"

# Exclude editor/dev cruft so what ships is exactly what was reviewed.
zip -rq "$ZIP" "$SRC" \
  -x "*.DS_Store" \
     "*/.git/*" \
     "*.swp" \
     "*~" \
     "*/node_modules/*"

echo "built: $ZIP ($(du -h "$ZIP" | cut -f1))"
echo
echo "to install on WordPress:"
echo "  Plugins → Add New → Upload Plugin → choose $ZIP → Install Now → Activate"
