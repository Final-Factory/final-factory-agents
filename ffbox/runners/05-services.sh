#!/bin/sh
# 05-services.sh — install the systemd units and bring the target up.
#
#   sudo sh ffbox/runners/05-services.sh --install
#   sh ffbox/runners/05-services.sh --check      exit 1 if installing would change anything
#   sh ffbox/runners/05-services.sh              report what is installed and running
#
# THE TEMPLATES IN systemd/ ARE THE ONLY SOURCE. They are rendered into a throwaway directory and
# installed from there, so no second copy on disk can disagree with git. Every path in a unit comes
# from THIS checkout, which is why --install from a second clone silently repoints everything at
# that clone and why the checkout path is recorded and checked.
#
# ffbox-container-dockerd.service is NOT installed here. It is a USER unit in the container
# account's own systemd instance and belongs to 02-daemon.sh.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
UNIT_DIR=/etc/systemd/system
RECORD=/etc/ffgithubrunners-checkout

INSTALL=0
CHECK=0
FORCE=0
NO_ENABLE=0
OWNER=""

usage() {
  cat <<EOF
Usage: sudo sh ffbox/runners/05-services.sh --install [options]

Renders ffbox/runners/systemd/*.service into ${UNIT_DIR}: the target, the daemon gate, the egress
fence and the two timers. Idempotent — re-run any time.

There are no per-runner units. ffwatch keeps the CI pool, and how many jobs run at once is
\`githubrunner.pool.max\` in config.json, which it re-reads live — \`ffgithubrunners slots N\` sets
it with no root and nothing restarting. Re-run this only after moving the checkout or changing the
owner.

Options (alphabetical):
  --check       Exit 1 if installing would change anything. Needs no root.
  --force       Install even when the units were installed from a different checkout.
  --help        Show this message.
  --install     Write the units, enable the timers, start the target. Needs root.
  --no-enable   Install the units but do not enable or start anything.
  --owner USER  Account the units run as (default: FFGITHUBRUNNERS_RUN_USER, then SUDO_USER,
                then the checkout owner).
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --check)     CHECK=1; shift ;;
    --force)     FORCE=1; shift ;;
    --help|-h)   usage; exit 0 ;;
    --install)   INSTALL=1; shift ;;
    --no-enable) NO_ENABLE=1; shift ;;
    --owner)     OWNER=${2:?--owner needs a user}; shift 2 ;;
    *)           echo "05-services.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
done

say()  { printf '==> %s\n' "$*"; }
skip() { printf '    %s\n' "$*"; }
die()  { printf '05-services.sh: %s\n' "$*" >&2; exit 1; }

# WHOSE MACHINE THIS IS. SUDO_USER is only meaningful when we are actually root: it lingers in any
# shell started under sudo. It is also ABSENT under systemd, which is how an unattended re-install
# would arrive — that path used to render @USER@=root and @HOME@=/root in ffbox, giving units that
# pointed at a home with no config in it.
if [ -z "$OWNER" ]; then
  if [ "$(id -u)" -eq 0 ]; then
    OWNER=${FFGITHUBRUNNERS_RUN_USER:-}
    [ -z "$OWNER" ] && [ "${SUDO_USER:-root}" != root ] && OWNER=$SUDO_USER
    [ -z "$OWNER" ] && OWNER=$(stat -c %U "$HERE/../.git" 2>/dev/null || echo root)
  else
    OWNER=$(id -un)
  fi
fi
id "$OWNER" >/dev/null 2>&1 || die "no such user: $OWNER"
OWNER_HOME=$(getent passwd "$OWNER" | cut -d: -f6)
OWNER_HOME=${OWNER_HOME%/}
OWNER_GROUP=$(id -gn "$OWNER")

HOME=$OWNER_HOME . "$HERE/lib/config.sh"

# The user manager that hosts the container account's rootless daemon. The gate orders against it,
# and Wants= it so that ordering binds -- see ffgithubrunners-dockerd-wait.service. Resolved here
# rather than in the template because only this script knows the account's uid, and named rather
# than left to id's own error, which under set -eu would abort with no hint at which script makes
# the account.
_cuid=$(id -u "$CONTAINER_USER" 2>/dev/null) \
  || die "no account '$CONTAINER_USER' on this box -- run: sh ffbox/runners/01-hostSetup.sh"
CONTAINER_USER_UNIT="user@${_cuid}.service"

# NO ffgithubrunners@.service. The per-runner supervisor was retired on 2026-09-08 when ffwatch
# took the CI lane; there is no template and nothing to instantiate. What is left is the target,
# the daemon gate, the egress fence and the two timers -- and the reaper matters MORE under one
# daemon rather than less, because it is the cleanup for "the daemon is broken".
UNITS="ffgithubrunners.target ffgithubrunners-dockerd-wait.service ffghr-egress.service ffgithubrunners-reap.service ffgithubrunners-reap.timer ffgithubrunners-image.service ffgithubrunners-image.timer"
TIMERS="ffgithubrunners-reap.timer ffgithubrunners-image.timer"

# --- render ------------------------------------------------------------------------------------

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

for u in $UNITS; do
  sed -e "s|@USER@|$OWNER|g" \
      -e "s|@GROUP@|$OWNER_GROUP|g" \
      -e "s|@HOME@|$OWNER_HOME|g" \
      -e "s|@CUSER@|$CONTAINER_USER|g" \
      -e "s|@IMAGESH@|$HERE/03-image.sh|g" \
      -e "s|@WAITDOCKER@|$HERE/wait-for-docker.sh|g" \
      -e "s|@DOCKERUSERUNIT@|$CONTAINER_USER_UNIT|g" \
      -e "s|@REAPSH@|$HERE/reap.sh|g" \
      -e "s|@IMAGEUPDATESH@|$HERE/image-update.sh|g" \
      -e "s|@DOCKERSOCK@|$DOCKER_SOCK|g" \
      -e "s|@LOGDIR@|$LOG_DIR|g" \
      -e "s|@CONFIGDIR@|$FFGHR_CONFIG_DIR|g" \
      -e "s|@CACHEDIR@|${CACHE_DIR:-/nonexistent}|g" \
      "$HERE/systemd/$u" > "$TMP/$u"
  # An unsubstituted placeholder produces a unit that starts and does the wrong thing quietly.
  if grep -q '@[A-Z]*@' "$TMP/$u"; then
    die "$u still has an unsubstituted placeholder: $(grep -o '@[A-Z]*@' "$TMP/$u" | sort -u | tr '\n' ' ')"
  fi
done

changed=""
for u in $UNITS; do
  cmp -s "$TMP/$u" "$UNIT_DIR/$u" 2>/dev/null || changed="$changed $u"
done

recorded=$(cat "$RECORD" 2>/dev/null || echo "")

# --- --check and the bare report ------------------------------------------------------------------

if [ "$INSTALL" -eq 0 ]; then
  printf 'checkout:     %s\n' "$HERE"
  printf 'recorded:     %s\n' "${recorded:-<none>}"
  printf 'run user:     %s (%s), home %s\n' "$OWNER" "$OWNER_GROUP" "$OWNER_HOME"
  # pool.max IS NOT THIS SCRIPT'S BUSINESS and is shown only so the two are never confused: it is
  # the live ceiling on jobs, ffwatch re-reads it, and `ffgithubrunners slots N` sets it with no
  # root.
  printf 'CI lane:      ffwatch (no per-runner supervisors)\n'
  printf 'pool.max:     %s (live; `ffgithubrunners slots N`, no root, no restart)\n' "$SLOTS"
  printf 'units stale:  %s\n' "${changed:- none}"
  for u in $UNITS; do
    printf '  %-42s %s\n' "$u" "$([ -r "$UNIT_DIR/$u" ] && echo installed || echo MISSING)"
  done
  # `systemctl is-active` PRINTS its answer and ALSO exits non-zero when the answer is not
  # "active", so the obvious `|| echo inactive` prints it twice.
  for tm in $TIMERS; do
    printf '  %-42s %s\n' "$tm" "$(systemctl is-active "$tm" 2>/dev/null || true)"
  done
  printf 'target:       %s\n' "$(systemctl is-active ffgithubrunners.target 2>/dev/null || true)"
  if [ "$CHECK" -eq 1 ]; then
    [ -z "$changed" ] || { printf '\n--check: units differ from this checkout\n'; exit 1; }
    printf '\n--check: installed units match this checkout\n'
  elif [ -z "$changed" ]; then
    printf '\nInstalled units match this checkout. Nothing owed.\n'
  else
    printf '\nTo apply: sudo sh %s/05-services.sh --install\n' "$HERE"
  fi
  exit 0
fi

# --- --install -------------------------------------------------------------------------------------

[ "$(id -u)" -eq 0 ] || die "--install writes to $UNIT_DIR and needs root. Run:
       sudo sh $HERE/05-services.sh --install"

# Installing from a second clone silently repoints every unit at that clone, and nothing complains
# afterwards. Refuse rather than let two checkouts fight over one machine.
if [ -n "$recorded" ] && [ "$recorded" != "$HERE" ] && [ "$FORCE" -eq 0 ]; then
  die "the installed units came from $recorded, and this is $HERE.
       Re-run there, or pass --force to move this machine to this checkout."
fi

say "installing units into $UNIT_DIR"
for u in $UNITS; do
  install -m 0644 "$TMP/$u" "$UNIT_DIR/$u"
  skip "$u"
done
printf '%s\n' "$HERE" > "$RECORD"
systemctl daemon-reload

if [ "$NO_ENABLE" -eq 1 ]; then
  skip "not enabling anything (--no-enable)"
  exit 0
fi

systemctl enable ffgithubrunners-dockerd-wait.service ffghr-egress.service >/dev/null 2>&1 || true
systemctl start ffgithubrunners-dockerd-wait.service
systemctl start ffghr-egress.service

# The timers. The reaper recovers a reboot or a killed supervisor; the weekly image rebuild is the
# only thing keeping the runner new enough for GitHub to keep giving it jobs.
for tm in $TIMERS; do
  systemctl enable --now "$tm" >/dev/null 2>&1 && skip "$tm enabled" || skip "could not enable $tm"
done

# NOTHING TO ENABLE OR DISABLE PER SLOT any more. Any instance left over from before the
# 2026-09-08 cut-over was disabled by the run that performed it; the template is gone, so systemd
# has nothing to instantiate even if a stray symlink survived somewhere.
#
# THE TARGET STILL EXISTS AND STILL MATTERS with no slots under it: it carries the reaper and the
# image timer, and the reaper matters more under one daemon rather than less, because it is the
# cleanup for "the daemon is broken".
say "starting ffgithubrunners.target (the CI lane is ffwatch's; no slot units)"
systemctl enable ffgithubrunners.target >/dev/null 2>&1 || true
systemctl restart ffgithubrunners.target

printf '\n'
printf '\n'
for tm in $TIMERS; do
  skip "$tm next: $(systemctl show "$tm" -p NextElapseUSecRealtime --value 2>/dev/null || echo unknown)"
done
skip "watch:  journalctl -u ffwatch -f | grep ' ci:'"
skip "a job's own log: $LOG_DIR/slot-N.log"
