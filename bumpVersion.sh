#!/bin/sh
# bumpVersion.sh — bump a plugin's version everywhere it is recorded, atomically-ish.
#
# A plugin's version lives in THREE files that must stay equal. If they drift, publishing
# silently no-ops: the update reports "already at the latest version" and keeps serving old
# content, with no error anywhere. This script is the only sanctioned way to change them.
#
#   sh bumpVersion.sh <plugin> [patch|minor|major]   bump (default: patch)
#   sh bumpVersion.sh --check                        verify all plugins agree; exit 1 if not
#   sh bumpVersion.sh --help
#
# Edits are done with sed, which rewrites only the matched bytes. Do NOT reimplement this by
# parsing and re-serializing the JSON — these manifests are UTF-8 with literal em-dashes and
# a naive round-trip mangles them (this has already happened once).

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"

MARKETPLACE=".claude-plugin/marketplace.json"

usage() {
  cat <<EOF
Usage: sh bumpVersion.sh <plugin> [patch|minor|major]
       sh bumpVersion.sh --check
       sh bumpVersion.sh --help

Bumps <plugin>'s version in all three places that record it:
  plugins/<plugin>/.claude-plugin/plugin.json
  plugins/<plugin>/.codex-plugin/plugin.json
  .claude-plugin/marketplace.json  (that plugin's entry)

(.agents/plugins/marketplace.json — the Codex marketplace — carries no versions.)

Plugins: $(ls -d plugins/*/ 2>/dev/null | sed 's|plugins/||;s|/||' | tr '\n' ' ')

--check verifies every plugin's three versions agree and exits 1 on any mismatch.
Run it before committing; a mismatch is invisible until someone gets stale skills.
EOF
}

# Read the first "version" value out of a plugin manifest.
manifest_version() {
  sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$1" 2>/dev/null | head -1
}

# Read the version recorded for a plugin inside the Claude marketplace manifest.
# The entry orders name -> description -> version, so take the first version after the name.
marketplace_version() {
  sed -n "/\"name\": \"$1\"/,/\"version\"/p" "$MARKETPLACE" 2>/dev/null \
    | sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' | head -1
}

plugin_names() {
  ls -d plugins/*/ 2>/dev/null | sed 's|plugins/||;s|/||'
}

check_all() {
  rc=0
  for p in $(plugin_names); do
    cj=$(manifest_version "plugins/$p/.claude-plugin/plugin.json")
    xj=$(manifest_version "plugins/$p/.codex-plugin/plugin.json")
    mk=$(marketplace_version "$p")
    if [ -n "$cj" ] && [ "$cj" = "$xj" ] && [ "$cj" = "$mk" ]; then
      printf '  %-12s %s  OK\n' "$p" "$cj"
    else
      printf '  %-12s claude=%s codex=%s marketplace=%s  MISMATCH\n' \
             "$p" "${cj:-MISSING}" "${xj:-MISSING}" "${mk:-MISSING}"
      rc=1
    fi
  done
  return $rc
}

# --- argument handling -------------------------------------------------------------------
case "${1:-}" in
  --help|-h) usage; exit 0 ;;
  --check)
    echo "version consistency:"
    if check_all; then
      echo "all plugins consistent"
      exit 0
    else
      echo "ERROR: fix the mismatch above before publishing — a drifted version publishes nothing." >&2
      exit 1
    fi
    ;;
  "") echo "ERROR: no plugin given" >&2; echo >&2; usage >&2; exit 1 ;;
esac

PLUGIN="$1"
PART="${2:-patch}"

CLAUDE_MANIFEST="plugins/$PLUGIN/.claude-plugin/plugin.json"
CODEX_MANIFEST="plugins/$PLUGIN/.codex-plugin/plugin.json"

[ -f "$CLAUDE_MANIFEST" ] || { echo "ERROR: no such plugin '$PLUGIN' ($CLAUDE_MANIFEST missing)" >&2; echo >&2; usage >&2; exit 1; }
[ -f "$CODEX_MANIFEST" ]  || { echo "ERROR: '$PLUGIN' has no Codex manifest ($CODEX_MANIFEST missing)" >&2; exit 1; }
grep -q "\"name\": \"$PLUGIN\"" "$MARKETPLACE" || { echo "ERROR: '$PLUGIN' has no entry in $MARKETPLACE" >&2; exit 1; }

case "$PART" in
  patch|minor|major) ;;
  *) echo "ERROR: bump part must be patch, minor, or major (got '$PART')" >&2; exit 1 ;;
esac

CUR=$(manifest_version "$CLAUDE_MANIFEST")
[ -n "$CUR" ] || { echo "ERROR: could not read a version from $CLAUDE_MANIFEST" >&2; exit 1; }

MAJOR=${CUR%%.*}
REST=${CUR#*.}
MINOR=${REST%%.*}
PATCH=${REST#*.}
case "$MAJOR$MINOR$PATCH" in
  *[!0-9]*) echo "ERROR: '$CUR' is not a numeric x.y.z version" >&2; exit 1 ;;
esac

case "$PART" in
  major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
  minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
  patch) PATCH=$((PATCH + 1)) ;;
esac
NEW="$MAJOR.$MINOR.$PATCH"

# --- apply ---------------------------------------------------------------------------------
sed -i "s/\"version\": \"$CUR\"/\"version\": \"$NEW\"/" "$CLAUDE_MANIFEST"
sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"$NEW\"/" "$CODEX_MANIFEST"
sed -i "/\"name\": \"$PLUGIN\"/,/\"version\"/ s/\"version\": \"[^\"]*\"/\"version\": \"$NEW\"/" "$MARKETPLACE"

echo "$PLUGIN: $CUR -> $NEW ($PART)"
echo "version consistency:"
if check_all; then
  echo
  echo "Next: commit + push, then 'sh registerClaude.sh' on each machine, then restart sessions."
else
  echo "ERROR: files are inconsistent AFTER the bump — inspect them before committing." >&2
  exit 1
fi
