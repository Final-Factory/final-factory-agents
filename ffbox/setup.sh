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
#   ../registerAgents.sh  the skills/roles marketplace, and the ffdiscord launcher on PATH
#   05-discord-setup.sh state dir, schema, config block for the Discord lanes
#   06-services.sh      the systemd units, installed and started (needs root)
#
# registerAgents.sh runs BEFORE 05: it is what puts `ffdiscord` in ~/.local/bin, and 05 calls it
# to look channel ids up by name. It is also what the containers read their skills from, so a
# machine that skips it runs agents against whatever plugin version was cached last.
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

# ------------------------------------------------------------------------------------------------
# WHOSE MACHINE THIS IS
#
# Every stage divides into two kinds. Stages 1, 2 and 6 change the SYSTEM — packages, datasets,
# /etc/sudoers.d, /etc/systemd/system — and need root. Stages 0, 4 and 5 write under a person's
# HOME — secrets, the Unity Library in golden, the ffbox config — and must be that person's
# files, not root's.
#
# Run by hand as yourself, that distinction takes care of itself: the system stages sudo, the
# rest are already yours. Run unattended by ffbox-update.service it does not, because that is
# root with no SUDO_USER, and every $HOME below would be /root. A setup that "succeeded" would
# have seeded a config in root's home that no service can read and left the real one untouched.
#
# So resolve the owner once, here, most explicit source first, and hand it to the stages that
# need it — as an argument where they take one, as FFBOX_RUN_USER where they do not, and as a
# uid to drop to for the HOME-scoped ones.
# SUDO_USER IS ONLY MEANINGFUL WHEN WE ARE ACTUALLY ROOT. It lingers in the environment of any
# shell that was itself started under sudo, so an unprivileged run would otherwise adopt whoever
# last sudo'd in that terminal and try to write their home. Found by running it: this file
# reached for /home/lothsahn from a FinalFactoryTester shell. The sibling stages guard it the
# same way, and this is the third time that trap has been worth a comment.
OWNER=${FFBOX_RUN_USER:-}
if [ -z "$OWNER" ]; then
  if [ "$(id -u)" = 0 ]; then
    [ "${SUDO_USER:-root}" != root ] && OWNER=$SUDO_USER
    # The checkout's owner: the same answer update_ffbox.sh derives for its git calls.
    [ -z "$OWNER" ] && OWNER=$(stat -c %U "$ROOT/../.git" 2>/dev/null || echo "")
  else
    OWNER=$(id -un)
  fi
fi
[ -n "$OWNER" ] || OWNER=$(id -un)
id "$OWNER" >/dev/null 2>&1 || { echo "setup.sh: no such user: $OWNER" >&2; exit 1; }
OWNER_HOME=$(getent passwd "$OWNER" | cut -d: -f6)
OWNER_HOME=${OWNER_HOME%/}
export FFBOX_RUN_USER=$OWNER

# Every path below is derived from HOME, so point it at the owner rather than threading the home
# through a dozen expressions — but ONLY when we are not already them. Running as yourself, an
# overridden $HOME is a deliberate act (that is how the sandbox tests and FFBOX_SECRETS work),
# and replacing it with the passwd entry would quietly ignore it.
if [ "$(id -un)" != "$OWNER" ]; then
  HOME=$OWNER_HOME
  export HOME
fi

# Run a HOME-scoped stage as the owner. Already them: straight through, no runuser needed (and
# none available to an unprivileged user anyway). Root: drop, and carry HOME, because runuser
# does not reset it.
as_owner() {
  if [ "$(id -un)" = "$OWNER" ]; then
    "$@"
  else
    runuser -u "$OWNER" -- env HOME="$OWNER_HOME" FFBOX_RUN_USER="$OWNER" "$@"
  fi
}

SECRETS=${FFBOX_SECRETS:-$HOME/.config/ffbox/secrets.env}

DO_DOCKER=1
DO_ZFS=1
DO_BUILD=1
DO_DISCORD=1
DO_SERVICES=1
DO_TOKEN=1
DO_AGENTS=1
ZFS_ARGS=""
# Auto-detected, and --non-interactive forces it. Nothing here may block on a prompt when there
# is no one to answer: the self-updater runs this from a systemd oneshot with an 8100s timeout.
NONINTERACTIVE=0
{ [ -t 0 ] && [ -t 1 ]; } || NONINTERACTIVE=1

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
  --skip-services  Do not install or start the systemd units.
  --skip-agents    Do not register or update the skills/roles plugin marketplace.
  --skip-token     Do not offer to run 'claude setup-token'.
  --non-interactive
                   Never prompt, and SKIP the stages that need root (Docker, ZFS, installing
                   the systemd units) rather than wait on a sudo password. What was skipped is
                   printed at the end. Implied when stdin or stdout is not a terminal. This is
                   how ffbox-update.service re-runs setup after an update.
  --skip-zfs       Do not touch ZFS; assume the layout already exists.

For finer control over any single stage, run it directly:
  sh ffbox/01-dockerSetup.sh --help
  sh ffbox/02-zfsSetup.sh --help
  sh ffbox/03-build.sh
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
    --skip-services) DO_SERVICES=0; shift ;;
    --skip-token)   DO_TOKEN=0; shift ;;
    --skip-agents)  DO_AGENTS=0; shift ;;
    --non-interactive) NONINTERACTIVE=1; shift ;;
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
#
# NO UNITY CREDENTIALS IN THIS TEST ANY MORE. As of 2026-09-01 the licence is a .ulf FILE that
# ffbox/unity-offline-license.sh mints and no container is handed a Unity password; the thing to be
# ready is therefore the file, not a pair of secrets. It is checked separately below rather than
# here, because the fix for a missing one is a command rather than an edit to this file.
secrets_ready() {
  ( set +u
    . "$SECRETS" 2>/dev/null || exit 1
    # ANY slot in the Claude pool, not slot 1 specifically. secrets.env numbers the tokens from
    # 1 (CLAUDE_CODE_OAUTH_TOKEN1, ...2, ...) and ffbox spends the first non-empty one, so a
    # file whose slot 1 was emptied after a revocation is still a ready file. The unnumbered
    # name is the older spelling and still counts.
    n=1
    while [ "$n" -le 16 ]; do
      eval "v=\${CLAUDE_CODE_OAUTH_TOKEN${n}}"
      if [ -n "$v" ]; then exit 0; fi
      n=$((n + 1))
    done
    [ -n "$CLAUDE_CODE_OAUTH_TOKEN" ]                            || exit 1
  ) 2>/dev/null
}

# The offline Unity licence. Absent is not a reason to refuse stage 3 -- everything else it does is
# still worth doing -- but it IS a reason to say so plainly, because the first run that starts an
# editor is where it would otherwise surface.
UNITY_ULF_PATH=${FFBOX_UNITY_ULF_HOST:-/opt/ffcache/unity/Unity_lic.ulf}
unity_licence_ready() { [ -r "$UNITY_ULF_PATH" ]; }

stage "0/7  secrets"

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
  # NOTHING IS MINTED WHEN THE POOL HOLDS ANYTHING AT ALL. A box with a second account already
  # written into CLAUDE_CODE_OAUTH_TOKEN2 is a box somebody has configured, and this stage
  # offering to run an OAuth flow at it would be setup.sh second-guessing that. Adding another
  # account is an edit to the file, deliberately — the numbering is the whole interface.
  if secrets_ready; then
    printf '    a Claude token is already set — leaving the pool alone\n'
    return 0
  fi
  command -v claude >/dev/null 2>&1     || { printf '    claude not on PATH — set CLAUDE_CODE_OAUTH_TOKEN1 by hand\n'; return 0; }
  if [ ! -t 0 ] || [ ! -t 1 ]; then
    printf '    no terminal — run "sh %s" interactively to mint the Claude token\n' "$0"
    return 0
  fi

  printf '\n==> the Claude token pool is empty. Run "claude setup-token" now? [Y/n] '
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
      printf '    no token entered — set CLAUDE_CODE_OAUTH_TOKEN1 by hand later\n'
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
    printf 'setup.sh: no valid token after %s attempts; set CLAUDE_CODE_OAUTH_TOKEN1 by hand.\n' \
           "$_attempt" >&2
    return 0
  fi

  printf '    accepted a %s-character token\n' "$(printf '%s' "$_tok" | wc -c | tr -d ' ')"
  # SLOT 1, not the unnumbered name. The pool is what ffbox and ffweb read, and a box seeded
  # under the old spelling would work but would show up on ffweb's /claude page as a legacy
  # entry rather than as key 1 of a pool somebody can add to.
  set_secret CLAUDE_CODE_OAUTH_TOKEN1 "$_tok" \
    && printf '==> wrote CLAUDE_CODE_OAUTH_TOKEN1 to %s\n' "$SECRETS"
  unset _tok _raw
}

mint_claude_token

# THE UNITY IMPORT STAGE IS GONE, so nothing here depends on secrets being filled in yet. It used
# to warn and skip when they were not; setup now completes regardless and secrets are only needed
# when a run actually starts.

# Docker first: stage 3 cannot build an image without it, and dockerSetup.sh is the one that
# keeps the layers OFF the boot environment — the zsys trap its own header documents at length.
# WHY THE ROOT STAGES SKIP RATHER THAN TRY. 1, 2 and 6 change the system, so unprivileged they
# reach for sudo, and with no terminal sudo either fails or sits there. Both are worse than
# saying so: 1 and 2 are one-time provisioning that is already satisfied on any machine an
# update is running on, and 6 is the one thing a human still owes (see SKIPPED, at the end).
needs_root() {   # $1 = stage label, for the message
  [ "$(id -u)" = 0 ] && return 0
  if [ "$NONINTERACTIVE" = 1 ] && ! sudo -n true 2>/dev/null; then
    SKIPPED="$SKIPPED
  $1"
    return 1
  fi
  return 0
}
SKIPPED=""

if [ "$DO_DOCKER" -eq 1 ] && needs_root "sh $ROOT/01-dockerSetup.sh"; then
  stage "1/7  Docker on its own ZFS dataset"
  sh "$ROOT/01-dockerSetup.sh"
elif [ "$DO_DOCKER" -eq 1 ]; then
  stage "1/7  Docker — skipped (needs root, and nothing here can be prompted)"
else
  stage "1/7  Docker — skipped (--skip-docker)"
fi

if [ "$DO_ZFS" -eq 1 ] && needs_root "sh $ROOT/02-zfsSetup.sh"; then
  stage "2/7  ZFS layout and golden checkout"
  # shellcheck disable=SC2086  # ZFS_ARGS is a deliberately word-split option list
  sh "$ROOT/02-zfsSetup.sh" $ZFS_ARGS
elif [ "$DO_ZFS" -eq 1 ]; then
  stage "2/7  ZFS layout — skipped (needs root, and nothing here can be prompted)"
else
  stage "2/7  ZFS layout — skipped (--skip-zfs)"
fi

if [ "$DO_BUILD" -eq 1 ]; then
  stage "3/7  container image"
  sh "$ROOT/03-build.sh"
else
  stage "3/7  container image — skipped (--skip-build)"
fi

# STAGE GONE, NOT SKIPPED. This ran 04-warmLibrary.sh: bring golden to origin, then open the
# project in Unity so every later ZFS clone inherited a warm Library. Runs no longer clone golden
# -- they restore CI's workspace tar, which already contains that Library, and fetch the commits
# since from the local git mirror. There is nothing left to warm.
#
# What replaced it needs no stage: CI fills /opt/ffcache, and ffbox/runners/03-image.sh brings up
# the mirror.

# Last, and deliberately not fatal: a machine that only ever runs ffbox by hand still wants
# stages 1-4, and this stage is the only one that can fail purely because Discord is not
# configured yet. It writes only under $HOME and starts nothing; the services are stage 6.
# Unprivileged and idempotent by design — it is the same "run it on every machine" bootstrap a
# human runs by hand, and re-running it is how a plugin version bump reaches this box at all.
# Not fatal: a marketplace that will not update is a stale skill set, not a broken machine.
if [ "$DO_AGENTS" -eq 1 ]; then
  stage "5/7  skills and roles (plugin marketplace, ffdiscord launcher)"
  as_owner sh "$ROOT/../registerAgents.sh" \
    || printf 'setup.sh: registerAgents.sh exited non-zero; live sessions keep the cached plugin\n' >&2
else
  stage "5/7  skills and roles — skipped (--skip-agents)"
fi

if [ "$DO_DISCORD" -eq 1 ]; then
  stage "6/7  Discord lanes (state dir, schema, config)"
  as_owner sh "$ROOT/05-discord-setup.sh" || printf 'setup.sh: 05-discord-setup.sh exited non-zero; run it by hand\n' >&2
else
  stage "6/7  Discord lanes — skipped (--skip-discord)"
fi

# The services, last, because they are what runs everything the stages above put in place.
# Installing into /etc needs root: this re-invokes through sudo, which may prompt. With no
# terminal and no passwordless sudo it prints the one command instead of hanging on a prompt.
if [ "$DO_SERVICES" -eq 1 ]; then
  if [ "$(id -u)" = 0 ]; then
    stage "7/7  systemd services (ffbox.target: listener + ffwatch + ffweb)"
    sh "$ROOT/06-services.sh" --install || true
  elif [ "$NONINTERACTIVE" = 0 ]; then
    stage "7/7  systemd services (ffbox.target: listener + ffwatch + ffweb)"
    sudo sh "$ROOT/06-services.sh" --install \
      || printf 'setup.sh: run it yourself: sudo sh %s/06-services.sh --install\n' "$ROOT" >&2
  else
    # Reported, not attempted. Writing /etc/systemd/system is root-equivalent — a unit can run
    # anything as anyone — so it is deliberately the one thing the unattended updater cannot do,
    # and --check is how it says whether anything is actually owed.
    stage "7/7  systemd services — deferred (needs root)"
    if sh "$ROOT/06-services.sh" --check; then
      printf '    the installed units already match this checkout and config\n'
    else
      SKIPPED="$SKIPPED
  sudo sh $ROOT/06-services.sh --install"
    fi
  fi
else
  stage "7/7  services — skipped (--skip-services)"
fi

if [ -n "$SKIPPED" ]; then
  stage "SKIPPED — these need root, and this run had no way to ask for it"
  printf '%s\n\n' "$SKIPPED"
  printf '  Run them yourself when convenient. Everything else above is already applied.\n'
fi

# THE UNITY LICENCE, WHICH NOTHING ELSE IN THIS SCRIPT CAN SUPPLY. It needs a human with a browser
# once, and until it exists every run that starts an editor fails. Said here rather than at stage 0
# because it is a command to run, not a file to edit, and this is where the remaining manual steps
# are collected.
if ! unity_licence_ready; then
  stage "Unity licence — NOT INSTALLED"
  cat <<EOF
  No .ulf at $UNITY_ULF_PATH, so any run that starts the editor will fail.
  It is a one-time manual activation and needs no Unity password afterwards:

    sh $ROOT/unity-offline-license.sh mint      # asks for your Unity account, once
    sh $ROOT/unity-offline-license.sh verify 3

EOF
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
as_owner sh "$ROOT/05-discord-setup.sh" --check 2>/dev/null | sed 's/^/  /' || true
printf '\n'
# app_token is the current key and token the pre-2026-08-24 one; both count as configured,
# because the CLI reads both and this check exists only to decide whether to print the steps.
if ! python3 -c "
import json,sys
cfg=json.load(open(sys.argv[1])).get('discord') or {}
sys.exit(0 if any((cfg.get(k) or '').strip() for k in ('app_token','token')) else 1)" \
     "${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}/config.json" 2>/dev/null \
   && [ -z "${FFDISCORD_APP_TOKEN:-}" ] && [ -z "${FFDISCORD_TOKEN:-}" ]; then
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
