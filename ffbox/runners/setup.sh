#!/bin/sh
# setup.sh — bring a machine from nothing to working ffgithubrunners in one command.
#
# Runs every stage in order. Each is independently re-runnable and each no-ops when it is already
# satisfied, so this is also the right thing to run after a git pull.
#
#   1  01-hostSetup.sh   the ffbox-container account, its socket dir, the daemon's store,
#                        the log dir                                              (needs root)
#   2  02-daemon.sh      that account's rootless Docker on its stable socket      (needs root)
#   3  03-image.sh       the runner image, and the egress fence it runs behind
#   4  04-github.sh      the GitHub credential, verified by minting a real JIT config
#   5  05-services.sh    the systemd units, the slots, the timers                 (needs root)
#
# WHICH STAGES NEED ROOT AND WHY THEY SKIP RATHER THAN TRY. 1, 2 and 5 change the system:
# accounts, another user's systemd instance, /etc/systemd/system. Unprivileged they reach for
# sudo, and with no terminal sudo either fails or sits there waiting. Both are worse than saying
# what is owed and carrying on, so with no way to ask they are reported at the end instead.
#
# Stage 3 is the slow one: a cold pull of the Unity base image is several gigabytes.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

DO_HOST=1
DO_DAEMON=1
DO_IMAGE=1
IMAGE_ARGS=""
DO_GITHUB=1
DO_SERVICES=1
NONINTERACTIVE=0
{ [ -t 0 ] && [ -t 1 ]; } || NONINTERACTIVE=1
GITHUB_ARGS=""

usage() {
  cat <<EOF
Usage: sh ffbox/runners/setup.sh [options]

Bootstraps this machine for ffgithubrunners. Idempotent — re-run any time.

Options (alphabetical):
  --app-id ID           Passed to 04-github.sh.
  --help                Show this message.
  --installation-id ID  Passed to 04-github.sh.
  --key PATH            Passed to 04-github.sh.
  --non-interactive     Never prompt, and SKIP the stages that need root rather than wait on a
                        sudo password. What was skipped is printed at the end. Implied when
                        stdin or stdout is not a terminal.
  --pat TOKEN           Passed to 04-github.sh.
  --skip-daemon         Do not install or start the rootless daemon.
  --skip-github         Do not touch the GitHub credential.
  --skip-host           Do not touch the account, the socket dir or the store.
  --skip-image          Do not build the image or bring up the fence.
  --skip-image-build    Bring up the fence, the networks and the mirror, but do NOT rebuild the
                        image. For a caller that has just built it: ffbox/03-build.sh builds the
                        same tag from the same Dockerfile, so on this machine the second build is
                        a cached no-op that still costs a minute and a half.
  --skip-services       Do not install or start the systemd units.

For finer control over any single stage, run it directly — each takes --help.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --app-id)          GITHUB_ARGS="$GITHUB_ARGS --app-id ${2:?}"; shift 2 ;;
    --help|-h)         usage; exit 0 ;;
    --installation-id) GITHUB_ARGS="$GITHUB_ARGS --installation-id ${2:?}"; shift 2 ;;
    --key)             GITHUB_ARGS="$GITHUB_ARGS --key ${2:?}"; shift 2 ;;
    --non-interactive) NONINTERACTIVE=1; shift ;;
    --pat)             GITHUB_ARGS="$GITHUB_ARGS --pat ${2:?}"; shift 2 ;;
    --skip-daemon)     DO_DAEMON=0; shift ;;
    --skip-github)     DO_GITHUB=0; shift ;;
    --skip-host)       DO_HOST=0; shift ;;
    --skip-image)      DO_IMAGE=0; shift ;;
    --skip-image-build) IMAGE_ARGS="--egress-only"; shift ;;
    --skip-services)   DO_SERVICES=0; shift ;;
    *)                 echo "setup.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
done

stage() { printf '\n######## %s\n\n' "$*"; }
SKIPPED=""

# True when we are root already, or can become root without blocking on a prompt nobody will
# answer. Same shape as ffbox/setup.sh, and for the same reason.
needs_root() {
  [ "$(id -u)" -eq 0 ] && return 0
  [ "$NONINTERACTIVE" = 1 ] && ! sudo -n true 2>/dev/null && return 1
  return 0
}
owe() { SKIPPED="$SKIPPED
  $*"; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then sh "$@"; else sudo sh "$@"; fi
}

if [ "$DO_HOST" -eq 1 ] && needs_root; then
  stage "1/5  host: the ffbox-container account, its socket, its store, the log dir"
  as_root "$ROOT/01-hostSetup.sh"
elif [ "$DO_HOST" -eq 1 ]; then
  stage "1/5  host — deferred (needs root, and nothing here can be prompted)"
  if sh "$ROOT/01-hostSetup.sh" --check >/dev/null 2>&1; then
    printf '    the host is already provisioned; nothing owed\n'
  else
    owe "sudo sh $ROOT/01-hostSetup.sh"
  fi
else
  stage "1/5  host — skipped (--skip-host)"
fi

if [ "$DO_DAEMON" -eq 1 ] && needs_root; then
  stage "2/5  the rootless daemon on its stable socket"
  as_root "$ROOT/02-daemon.sh"
elif [ "$DO_DAEMON" -eq 1 ]; then
  stage "2/5  daemon — deferred (needs root, and nothing here can be prompted)"
  # Nothing is owed if the daemon is already answering, which on a re-run is the normal case.
  if sh "$ROOT/02-daemon.sh" --check 2>/dev/null | grep -q '^answers: *yes'; then
    printf '    the daemon is already up; nothing owed\n'
  else
    owe "sudo sh $ROOT/02-daemon.sh"
  fi
else
  stage "2/5  daemon — skipped (--skip-daemon)"
fi

# Unprivileged from here. If the daemon stage was deferred these will fail to reach the socket and
# say so, which is the right outcome: they cannot do anything useful without it.
if [ "$DO_IMAGE" -eq 1 ]; then
  stage "3/5  the runner image and its egress fence (slow on a cold pull)"
  # shellcheck disable=SC2086  # IMAGE_ARGS is empty or one option, deliberately unquoted
  sh "$ROOT/03-image.sh" $IMAGE_ARGS || printf 'setup.sh: 03-image.sh exited non-zero\n' >&2
else
  stage "3/5  image — skipped (--skip-image)"
fi

if [ "$DO_GITHUB" -eq 1 ]; then
  stage "4/5  the GitHub credential"
  # Not fatal. A machine with everything else in place and no credential yet is a machine one
  # command away from working, and saying so beats aborting the run.
  # shellcheck disable=SC2086
  sh "$ROOT/04-github.sh" $GITHUB_ARGS || owe "sh $ROOT/04-github.sh   (see its output above)"
else
  stage "4/5  GitHub — skipped (--skip-github)"
fi

if [ "$DO_SERVICES" -eq 1 ] && needs_root; then
  stage "5/5  systemd units, slots and timers"
  as_root "$ROOT/05-services.sh" --install
elif [ "$DO_SERVICES" -eq 1 ]; then
  stage "5/5  services — deferred (needs root)"
  if sh "$ROOT/05-services.sh" --check >/dev/null 2>&1; then
    printf '    the installed units already match this checkout and config\n'
  else
    owe "sudo sh $ROOT/05-services.sh --install"
  fi
else
  stage "5/5  services — skipped (--skip-services)"
fi

if [ -n "$SKIPPED" ]; then
  stage "STILL OWED"
  printf '%s\n\n' "$SKIPPED"
fi

stage "setup complete"
cat <<EOF
  $ROOT/ffgithubrunners status

The slots come up WITHOUT the self-hosted label, so nothing routes to them and the existing
runners keep serving main.yml. That is section 13 step 1 of the design and it is the correct
resting state until the new path has been proven side by side.
EOF
