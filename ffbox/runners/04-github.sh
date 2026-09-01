#!/bin/sh
# 04-github.sh — the one credential this system holds, and proof that it works.
#
# Ephemeral runners register a new runner for every job, so something here has to call the API
# continuously. That is the only reason a credential exists; the workflows are unaffected.
#
# VERIFICATION MINTS A REAL JIT CONFIG AND THEN DELETES THE RUNNER IT CREATED. Checking that the
# token merely authenticates would pass with the wrong permission and fail eight hours later on
# the first job, at which point the failure looks like a runner problem rather than a token
# problem. Doing the actual call is the only check worth the name.
#
# Needs no root. Everything it writes is under the invoking account's ~/.config.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

CHECK_ONLY=0
PAT=""
ARG_APP_ID=""
ARG_APP_INSTALL=""
ARG_APP_KEY=""
NONINTERACTIVE=0
{ [ -t 0 ] && [ -t 1 ]; } || NONINTERACTIVE=1

usage() {
  cat <<EOF
Usage: sh ffbox/runners/04-github.sh [options]

Records the GitHub credential and proves it can mint a JIT config. Idempotent — re-run any time.

Either credential works, and lib/gh.sh handles both:

  a fine-grained PAT   --pat TOKEN
                       Organization permissions -> Self-hosted runners -> Read and write.
                       One setting to create, and the smallest thing to start with.

  a GitHub App         --app-id ID --installation-id ID --key PATH
                       Same permission. Better hygiene: installation tokens expire in an hour and
                       no personal account is in the loop, at the cost of more setup.

Options (alphabetical):
  --app-id ID           GitHub App id.
  --check               Verify whatever is already configured; write nothing.
  --help                Show this message.
  --installation-id ID  The App's installation id on the organization.
  --key PATH            The App's private key (.pem). Copied beside secrets.env at 0600.
  --non-interactive     Never prompt. Implied when stdin or stdout is not a terminal.
  --pat TOKEN           A fine-grained personal access token.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --app-id)          ARG_APP_ID=${2:?--app-id needs a value}; shift 2 ;;
    --check)           CHECK_ONLY=1; shift ;;
    --help|-h)         usage; exit 0 ;;
    --installation-id) ARG_APP_INSTALL=${2:?--installation-id needs a value}; shift 2 ;;
    --key)             ARG_APP_KEY=${2:?--key needs a path}; shift 2 ;;
    --non-interactive) NONINTERACTIVE=1; shift ;;
    --pat)             PAT=${2:?--pat needs a token}; shift 2 ;;
    *)                 echo "04-github.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
done

say()  { printf '==> %s\n' "$*"; }
skip() { printf '    %s\n' "$*"; }
die()  { printf '04-github.sh: %s\n' "$*" >&2; exit 1; }

. "$HERE/lib/config.sh"

mkdir -p "$FFGHR_CONFIG_DIR"
chmod 0700 "$FFGHR_CONFIG_DIR" 2>/dev/null || true

# MIGRATION from ~/.config/ffgithubrunners, which is where this lived before the config moved
# under ~/.config/ffbox with the rest of what ffbox owns on a machine. Moved rather than copied:
# two config directories, one of them stale, is worse than either.
OLD_DIR="$HOME/.config/ffgithubrunners"
if [ -d "$OLD_DIR" ] && [ "$OLD_DIR" != "$FFGHR_CONFIG_DIR" ]; then
  say "moving $OLD_DIR to $FFGHR_CONFIG_DIR"
  for f in config.json secrets.env github-app.pem .installation-token; do
    if [ -e "$OLD_DIR/$f" ] && [ ! -e "$FFGHR_CONFIG_DIR/$f" ]; then
      mv "$OLD_DIR/$f" "$FFGHR_CONFIG_DIR/$f"
      skip "moved $f"
    fi
  done
  rmdir "$OLD_DIR" 2>/dev/null && skip "removed $OLD_DIR" \
    || skip "$OLD_DIR still has files in it; look before deleting it"
fi

# Drop the template in place whatever else happens, so a machine that gets no further still has
# the instructions on disk rather than only in this script's help.
if [ ! -e "$FFGHR_SECRETS" ]; then
  install -m 0600 "$HERE/secrets.env.example" "$FFGHR_SECRETS"
  say "created $FFGHR_SECRETS (mode 600) from the template"
fi
# NO TEMPLATE TO INSTALL ANY MORE. The runners' settings are a section of the box's one config
# file, seeded by 05-discord-setup.sh along with everything else in it, so there is nothing for
# this stage to create. set_config below writes into that section, creating it if the machine has
# somehow reached here without it.

# Set one key in config.json. python3 rather than sed, because a JSON file edited by line is a
# JSON file that eventually is not one. This reflows the file; the _comment keys survive, which is
# where the explanations live.
set_config() {
  _k=$1; _v=$2
  KEY="$_k" VAL="$_v" CFG="$FFGHR_CONFIG" SECTION="$FFGHR_CONFIG_SECTION" python3 - <<'PY'
import json, os
path, key, val = os.environ["CFG"], os.environ["KEY"], os.environ["VAL"]
section = os.environ["SECTION"]
try:
    with open(path) as fh:
        cfg = json.load(fh)
except FileNotFoundError:
    cfg = {}
if not isinstance(cfg.get(section), dict):
    cfg[section] = {}
cfg[section][key] = int(val) if val.isdigit() else val
tmp = path + ".tmp"
with open(tmp, "w") as fh:
    json.dump(cfg, fh, indent=2, sort_keys=True)
    fh.write("\n")
os.replace(tmp, path)
PY
}

# Rewrite one KEY=value in place. Temp file next to the target so the replacement is a
# same-filesystem rename, and created under umask 077 so the token is never briefly readable.
set_secret() {
  _k=$1; _v=$2; _tmp="${FFGHR_SECRETS}.tmp.$$"
  ( umask 077; : > "$_tmp" )
  awk -v k="$_k" -v v="$_v" '
    index($0, k "=") == 1 { print k "=" v; done = 1; next }
    { print }
    END { if (!done) print k "=" v }
  ' "$FFGHR_SECRETS" > "$_tmp" || { rm -f "$_tmp"; return 1; }
  mv "$_tmp" "$FFGHR_SECRETS"
  chmod 0600 "$FFGHR_SECRETS"
}

# --- take what was given, or ask -------------------------------------------------------------------

if [ "$CHECK_ONLY" -eq 0 ]; then
  if [ -n "$PAT" ]; then
    set_secret FFGHR_GITHUB_TOKEN "$PAT"
    say "recorded a PAT in $FFGHR_SECRETS"
  elif [ -n "$ARG_APP_ID" ] || [ -n "$ARG_APP_INSTALL" ] || [ -n "$ARG_APP_KEY" ]; then
    [ -n "$ARG_APP_ID" ]      || die "--app-id is required with the App options"
    [ -n "$ARG_APP_INSTALL" ] || die "--installation-id is required with the App options"
    [ -n "$ARG_APP_KEY" ]     || die "--key is required with the App options"
    [ -r "$ARG_APP_KEY" ]     || die "cannot read the key at $ARG_APP_KEY"

    # One place a key ever lives, so nothing has to record where it went. APP_KEY from
    # lib/config.sh is this same path.
    if [ "$(readlink -f "$ARG_APP_KEY")" != "$(readlink -f "$APP_KEY" 2>/dev/null || echo)" ]; then
      ( umask 077; cp "$ARG_APP_KEY" "$APP_KEY" )
      chmod 0600 "$APP_KEY"
      say "copied the App key to $APP_KEY (mode 600)"
    fi
    # A key that is not a key fails here rather than inside a JWT signature at 3am.
    openssl rsa -in "$APP_KEY" -noout -check >/dev/null 2>&1 \
      || openssl pkey -in "$APP_KEY" -noout >/dev/null 2>&1 \
      || die "$APP_KEY is not a readable private key"

    # The two ids go in config.json, not secrets.env: they identify an App, they do not
    # authenticate as one. The key is the secret, and it is a file.
    set_config app_id "$ARG_APP_ID"
    set_config app_installation_id "$ARG_APP_INSTALL"
    APP_ID=$ARG_APP_ID
    APP_INSTALLATION_ID=$ARG_APP_INSTALL
    say "recorded App $ARG_APP_ID, installation $ARG_APP_INSTALL in $FFGHR_CONFIG"
  fi

  # Anything left in secrets.env from before the ids moved into config.json. The lines are always
  # stripped, because gh.sh lets secrets.env win and a stale id shadowing the real one is a very
  # quiet way to fail. The VALUES are only carried across when this run was not given better ones.
  if grep -q '^FFGHR_APP_' "$FFGHR_SECRETS" 2>/dev/null; then
    if [ -z "$ARG_APP_ID" ]; then
      _sid=$(sed -n 's/^FFGHR_APP_ID=//p' "$FFGHR_SECRETS" | head -1)
      _sin=$(sed -n 's/^FFGHR_APP_INSTALLATION_ID=//p' "$FFGHR_SECRETS" | head -1)
      [ -z "$_sid" ] || { set_config app_id "$_sid"; APP_ID=$_sid; }
      [ -z "$_sin" ] || { set_config app_installation_id "$_sin"; APP_INSTALLATION_ID=$_sin; }
      say "moved the App ids out of secrets.env and into $FFGHR_CONFIG"
    else
      say "dropped the stale App ids in secrets.env; the arguments to this run win"
    fi
    _tmp="${FFGHR_SECRETS}.tmp.$$"
    ( umask 077; grep -v '^FFGHR_APP_' "$FFGHR_SECRETS" > "$_tmp" )
    mv "$_tmp" "$FFGHR_SECRETS"
    chmod 0600 "$FFGHR_SECRETS"
  fi
fi

# --- verify, by doing the real thing -------------------------------------------------------------------

# RE-READ THE CONFIG FIRST. lib/config.sh was sourced at the top, before this script had seeded
# config.json from the template and before the migration moved an existing one into place, so
# everything it resolved came from the defaults in code. That is not cosmetic: LABELS defaults to
# the set INCLUDING self-hosted, and the probe below would register a runner carrying it, which is
# the one thing section 13 step 1 of the design says must not happen while the old runners are
# still serving main.yml.
# shellcheck disable=SC1090
. "$HERE/lib/config.sh"

. "$HERE/lib/gh.sh"

if ! gh_token >/dev/null 2>&1; then
  cat >&2 <<EOF

04-github.sh: no usable credential yet.

  Fill in ONE block in $FFGHR_SECRETS, or pass it here:

    sh $HERE/04-github.sh --pat github_pat_...
    sh $HERE/04-github.sh --app-id 123456 --installation-id 98765432 --key ./app.pem

  Either needs the organization's "Self-hosted runners" permission at Read and write.

EOF
  exit 1
fi

PROBE="ffghr-$(hostname -s 2>/dev/null || echo host)-probe-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"

say "verifying against $ORG by minting a real JIT config"
skip "probe runner: $PROBE"

OUT=$(gh_mint_jitconfig "$PROBE") || die "could not mint a JIT config.
       The credential authenticates but cannot register runners on $ORG. Check the
       'Self-hosted runners' organization permission is Read and WRITE, not read."

RUNNER_ID=$(printf '%s' "$OUT" | cut -d' ' -f1)
JIT=$(printf '%s' "$OUT" | cut -d' ' -f2-)
[ -n "$RUNNER_ID" ] || die "no runner id came back"
skip "minted runner id $RUNNER_ID, ${#JIT} bytes of JIT config"

# Clean up unconditionally: a probe left registered shows up on the org's runner page as an
# offline runner nobody can explain, and the reaper would only remove it because its name has no
# matching container, which is a slower way to arrive at the same place.
if gh_delete_runner "$RUNNER_ID"; then
  skip "probe runner deleted"
else
  printf '    WARNING: could not delete probe runner %s. Remove it by hand from\n' "$RUNNER_ID" >&2
  printf '             https://github.com/organizations/%s/settings/actions/runners\n' "$ORG" >&2
fi

printf '\n'
say "GitHub is configured"
skip "org:    $ORG"
skip "labels: $LABELS"
skip "auth:   $([ -n "${FFGHR_GITHUB_TOKEN:-}" ] && echo "PAT" || echo "App $FFGHR_APP_ID, installation $FFGHR_APP_INSTALLATION_ID")"
printf '\n'
skip "next: sh $HERE/05-services.sh"
