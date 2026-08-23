#!/bin/sh
# setup.sh — bring a machine from nothing to a working ffbox in one command.
#
# ONE SERVICE, NOT A KIT OF PARTS. Whatever machine this runs on gets all of ffbox: the
# container harness, the Discord conversation pipeline, and the web page. The last stage
# installs the systemd units and starts ffbox.target; the --skip-* flags exist so a re-run can
# pass over a stage that is already satisfied, not so a machine can have half of it.
#
# Runs every stage in order, each of which is independently re-runnable and each of which
# no-ops when it is already satisfied:
#
#   01-dockerSetup.sh   Docker on its own ZFS dataset, overlay2 driver
#   02-zfsSetup.sh      ZFS datasets, the golden checkout, the runs mountpoint, sudoers
#   03-build.sh         the container image (Unity + Claude Code)
#   04-warmLibrary.sh   update golden from git, then build its Unity Library/ cache
#   05-discord-setup.sh state dir, schema, config block for the Discord lanes
#   06-services.sh      the systemd units, installed and started (needs root)
#
# The numbers are the running order, and they are in the filenames so that order is visible in
# an `ls` rather than only in here.
#
# Stage 4 is the slow one — a cold Unity import on Final Factory is plausibly 30-60 minutes — and
# it is the reason the whole layout exists: it happens once in golden, and every later ffbox run
# clones that warm Library/ for free.
#
# Safe to re-run. Stages 1 and 2 no-op when they are already satisfied; stage 3 re-imports, which
# is what you want after a git pull anyway.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"

SECRETS=${FFBOX_SECRETS:-$HOME/.config/ffbox/secrets.env}

DO_DOCKER=1
DO_ZFS=1
DO_BUILD=1
DO_LIBRARY=1
DO_DISCORD=1
DO_SERVICES=1
DO_TOKEN=1
ZFS_ARGS=""

usage() {
  cat <<EOF
Usage: sh setup.sh [options]

Bootstraps this machine for ffbox: Docker, ZFS layout, container image, a warm Unity Library,
and the Discord lanes — then installs and starts the services. Idempotent — re-run any time.

ffbox installs as ONE service. The --skip-* flags below are for re-runs (skip a stage that is
already satisfied, or one this machine manages elsewhere), NOT a way to choose which parts of
ffbox to have. A machine is either an ffbox machine or it is not.

Options (alphabetical):
  --help           Show this message.
  --owner USER     Passed through to zfsSetup.sh (default: the invoking user).
  --pool NAME      Passed through to zfsSetup.sh (default: the pool holding /).
  --skip-build     Do not rebuild the container image.
  --skip-discord   Do not provision the Discord lanes (state dir, config, systemd units).
  --skip-docker    Do not touch Docker; assume it is installed and configured.
  --skip-library   Do not update golden or run the Unity import. Use when you only want the
                   datasets and image in place.
  --skip-services  Do not install or start the systemd units.
  --skip-token     Do not offer to run 'claude setup-token'.
  --skip-zfs       Do not touch ZFS; assume the layout already exists.

For finer control over any single stage, run it directly:
  sh ffbox/01-dockerSetup.sh --help
  sh ffbox/02-zfsSetup.sh --help
  sh ffbox/03-build.sh
  sh ffbox/04-warmLibrary.sh --help
  sh ffbox/05-discord-setup.sh --help
  sh ffbox/06-services.sh --help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --help|-h)      usage; exit 0 ;;
    --owner)        ZFS_ARGS="$ZFS_ARGS --owner ${2:?--owner needs a user}"; shift 2 ;;
    --pool)         ZFS_ARGS="$ZFS_ARGS --pool ${2:?--pool needs a name}"; shift 2 ;;
    --skip-build)   DO_BUILD=0; shift ;;
    --skip-discord) DO_DISCORD=0; shift ;;
    --skip-docker)  DO_DOCKER=0; shift ;;
    --skip-library) DO_LIBRARY=0; shift ;;
    --skip-services) DO_SERVICES=0; shift ;;
    --skip-token)   DO_TOKEN=0; shift ;;
    --skip-zfs)     DO_ZFS=0; shift ;;
    *)              echo "setup.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
done

stage() { printf '\n######## %s\n\n' "$*"; }

# ------------------------------------------------------------------------------------------------
# Secrets: drop the template in place, then decide whether stage 3 can run.
#
# Stage 3 cannot work without a Unity license, and discovering that after a 20-minute git pull is
# a poor way to find out. Stages 1 and 2 still run either way, so the machine is left as far along
# as it can get and one edit plus one command finishes the job.
# ------------------------------------------------------------------------------------------------

# True only when every value stage 3 actually needs has been filled in. Sourced in a subshell so
# the secrets never enter this script's own environment, and so a malformed file cannot abort it.
secrets_ready() {
  ( set +u
    . "$SECRETS" 2>/dev/null || exit 1
    [ -n "$CLAUDE_CODE_OAUTH_TOKEN" ]                            || exit 1
    [ -n "$UNITY_EMAIL" ] && [ -n "$UNITY_PASSWORD" ]            || exit 1
    [ -n "$UNITY_SERIAL" ] || [ -n "$UNITY_LICENSE_FILE" ]       || exit 1
  ) 2>/dev/null
}

stage "0/6  secrets"

if [ -e "$SECRETS" ]; then
  skip_msg="$SECRETS already exists — leaving it alone"
  printf '    %s\n' "$skip_msg"
else
  # 0700 on the directory and 0600 on the file: this ends up holding a Unity account password and
  # a long-lived Claude token. Created from the checked-in template, which is all comments and
  # empty values, so there is nothing sensitive in the copy itself.
  mkdir -p "$(dirname "$SECRETS")"
  chmod 700 "$(dirname "$SECRETS")" 2>/dev/null || true
  install -m 600 "$ROOT/secrets.env.example" "$SECRETS"
  printf '==> created %s (mode 600) from the template\n' "$SECRETS"
fi

# Read one KEY=value out of the secrets file without importing the rest into this shell.
get_secret() {
  ( set +u; . "$SECRETS" 2>/dev/null || exit 0; eval "printf '%s' \"\${$1}\"" ) 2>/dev/null
}

# Rewrite one KEY=value in place. The temp file is created NEXT TO the target so the replacement
# is a same-filesystem rename (atomic), and starts at 0600 so the token is never briefly readable.
set_secret() {
  _k=$1; _v=$2; _tmp="${SECRETS}.tmp.$$"
  ( umask 077; : > "$_tmp" )
  awk -v k="$_k" -v v="$_v" '
    index($0, k "=") == 1 { print k "=" v; done = 1; next }
    { print }
    END { if (!done) print k "=" v }
  ' "$SECRETS" > "$_tmp" || { rm -f "$_tmp"; return 1; }
  mv "$_tmp" "$SECRETS"
}

# ------------------------------------------------------------------------------------------------
# Offer to mint the Claude token.
#
# `claude setup-token` is a purely interactive OAuth flow — it has no flags, no non-interactive
# mode, and no way to print the token without a human completing a browser login. So this runs it
# with the terminal fully inherited (piping its stdout to capture the token risks breaking the
# flow, since CLIs routinely change behaviour when stdout is not a terminal) and then asks for the
# result to be pasted back. Skipped entirely when there is no terminal to drive it.
# ------------------------------------------------------------------------------------------------
mint_claude_token() {
  [ "$DO_TOKEN" -eq 1 ]                 || { printf '    token setup skipped (--skip-token)\n'; return 0; }
  [ -z "$(get_secret CLAUDE_CODE_OAUTH_TOKEN)" ] || { printf '    CLAUDE_CODE_OAUTH_TOKEN already set — leaving it alone\n'; return 0; }
  command -v claude >/dev/null 2>&1     || { printf '    claude not on PATH — set CLAUDE_CODE_OAUTH_TOKEN by hand\n'; return 0; }
  if [ ! -t 0 ] || [ ! -t 1 ]; then
    printf '    no terminal — run "sh %s" interactively to mint the Claude token\n' "$0"
    return 0
  fi

  printf '\n==> CLAUDE_CODE_OAUTH_TOKEN is empty. Run "claude setup-token" now? [Y/n] '
  read -r _ans
  case "$_ans" in [Nn]*) printf '    skipped\n'; return 0 ;; esac

  printf '\n--- claude setup-token ------------------------------------------------------\n'
  claude setup-token || printf '\nsetup.sh: claude setup-token exited non-zero\n' >&2
  printf -- '-----------------------------------------------------------------------------\n\n'

  # Input is deliberately VISIBLE. Hiding it is the safer default for a credential, but a paste
  # that produces no feedback reads as "nothing happened" — the natural response is to paste
  # again, and a silently doubled token is a much worse failure than the value appearing in
  # scrollback on the machine that is about to store it in a file anyway.
  printf 'Paste the token below, then press Enter. (Enter on an empty line skips.)\n'

  _tok=""
  _attempt=0
  while [ "$_attempt" -lt 3 ]; do
    _attempt=$((_attempt + 1))
    printf '> '
    read -r _raw || { _raw=""; }

    # Strip all whitespace: a paste can carry a stray newline, a leading space, or wrap.
    _raw=$(printf '%s' "$_raw" | tr -d '[:space:]')

    if [ -z "$_raw" ]; then
      printf '    no token entered — set CLAUDE_CODE_OAUTH_TOKEN by hand later\n'
      return 0
    fi

    case "$_raw" in
      sk-ant-*) ;;
      *) printf '    that does not start with sk-ant- — try again\n' >&2; continue ;;
    esac

    # The doubled-paste guard. Two right-clicks concatenate the token with itself, which still
    # starts with sk-ant- and still looks plausible; counting the marker is what catches it.
    _n=$(printf '%s' "$_raw" | grep -o 'sk-ant-' | wc -l | tr -d ' ')
    if [ "$_n" -gt 1 ]; then
      printf '    that looks like the token pasted %s times (%s characters) — try again\n' \
             "$_n" "$(printf '%s' "$_raw" | wc -c | tr -d ' ')" >&2
      continue
    fi

    _tok=$_raw
    break
  done

  if [ -z "$_tok" ]; then
    printf 'setup.sh: no valid token after %s attempts; set CLAUDE_CODE_OAUTH_TOKEN by hand.\n' \
           "$_attempt" >&2
    return 0
  fi

  printf '    accepted a %s-character token\n' "$(printf '%s' "$_tok" | wc -c | tr -d ' ')"
  set_secret CLAUDE_CODE_OAUTH_TOKEN "$_tok" \
    && printf '==> wrote CLAUDE_CODE_OAUTH_TOKEN to %s\n' "$SECRETS"
  unset _tok _raw
}

mint_claude_token

if [ "$DO_LIBRARY" -eq 1 ] && ! secrets_ready; then
  cat >&2 <<EOF

setup.sh: $SECRETS is not filled in yet, so stage 3 (the Unity import) will be skipped.
          Stages 1 and 2 still run.

  1. \$EDITOR $SECRETS
     - UNITY_EMAIL / UNITY_PASSWORD    (required even for a Personal license)
     - UNITY_SERIAL, or UNITY_LICENSE_FILE pointing at a .ulf
     - CLAUDE_CODE_OAUTH_TOKEN         (setup.sh offers to mint this for you)
  2. sh $ROOT/04-warmLibrary.sh

EOF
  DO_LIBRARY=0
fi

# Docker first: stage 3 cannot build an image without it, and dockerSetup.sh is the one that
# keeps the layers OFF the boot environment — the zsys trap its own header documents at length.
if [ "$DO_DOCKER" -eq 1 ]; then
  stage "1/6  Docker on its own ZFS dataset"
  sh "$ROOT/01-dockerSetup.sh"
else
  stage "1/6  Docker — skipped (--skip-docker)"
fi

if [ "$DO_ZFS" -eq 1 ]; then
  stage "2/6  ZFS layout and golden checkout"
  # shellcheck disable=SC2086  # ZFS_ARGS is a deliberately word-split option list
  sh "$ROOT/02-zfsSetup.sh" $ZFS_ARGS
else
  stage "2/6  ZFS layout — skipped (--skip-zfs)"
fi

if [ "$DO_BUILD" -eq 1 ]; then
  stage "3/6  container image"
  sh "$ROOT/03-build.sh"
else
  stage "3/6  container image — skipped (--skip-build)"
fi

if [ "$DO_LIBRARY" -eq 1 ]; then
  stage "4/6  update golden and warm its Unity Library (slow)"
  sh "$ROOT/04-warmLibrary.sh"
else
  stage "4/6  Unity Library — skipped"
fi

# Last, and deliberately not fatal: a machine that only ever runs ffbox by hand still wants
# stages 1-4, and this stage is the only one that can fail purely because Discord is not
# configured yet. It writes only under $HOME and starts nothing; the services are stage 6.
if [ "$DO_DISCORD" -eq 1 ]; then
  stage "5/6  Discord lanes (state dir, schema, config)"
  sh "$ROOT/05-discord-setup.sh" || printf 'setup.sh: 05-discord-setup.sh exited non-zero; run it by hand\n' >&2
else
  stage "5/6  Discord lanes — skipped (--skip-discord)"
fi

# The services, last, because they are what runs everything the stages above put in place.
# Installing into /etc needs root: this re-invokes through sudo, which may prompt. With no
# terminal and no passwordless sudo it prints the one command instead of hanging on a prompt.
if [ "$DO_SERVICES" -eq 1 ]; then
  stage "6/6  systemd services (ffbox.target: listener + ffwatch + ffweb)"
  if [ "$(id -u)" = 0 ]; then
    sh "$ROOT/06-services.sh" --install || true
  elif sudo -n true 2>/dev/null || [ -t 0 ]; then
    sudo sh "$ROOT/06-services.sh" --install \
      || printf 'setup.sh: run it yourself: sudo sh %s/06-services.sh --install\n' "$ROOT" >&2
  else
    printf 'setup.sh: the units need root and there is no terminal to ask on. Run:\n' >&2
    printf '  sudo sh %s/06-services.sh --install\n' "$ROOT" >&2
  fi
else
  stage "6/6  services — skipped (--skip-services)"
fi

stage "setup complete"
cat <<EOF
Try it:
  $ROOT/ffbox 'summarise how the save migration system works'
EOF

# EVERY REMAINING MANUAL STEP, IN ONE PLACE. Stage 5 prints the same list in Discord terms;
# this is the whole-machine view, so somebody who ran one command and walked away can come back
# to exactly what is left rather than scrolling for it.
printf '\n'
sh "$ROOT/05-discord-setup.sh" --check 2>/dev/null | sed 's/^/  /' || true
printf '\n'
if ! python3 -c "
import json,sys
cfg=json.load(open(sys.argv[1]))
sys.exit(0 if (cfg.get('token') or '').strip() else 1)" \
     "${FFDISCORD_HOME:-$HOME/.config/ffdiscord}/config.json" 2>/dev/null \
   && [ -z "${FFDISCORD_TOKEN:-}" ]; then
  cat <<EOF
MANUAL STEPS REMAINING
  The Discord lanes need a bot before they can read anything:
    sh $ROOT/05-discord-setup.sh        prints the full step-by-step (bot, token, channels)
  Then, to pick the new watch list up:
    sudo sh $ROOT/06-services.sh --install
    ffdiscord doctor

  The shell and the web page work now, with or without Discord.
EOF
else
  cat <<EOF
MANUAL STEPS REMAINING
  None known. Verify with:
    ffdiscord doctor                    the bot can see its channels
    sh $ROOT/06-services.sh             units installed, enabled, running, not stale
    python3 $ROOT/ffwatch.py status     the pipeline's own view
EOF
fi
cat <<EOF

Full usage: $ROOT/README.md
EOF
