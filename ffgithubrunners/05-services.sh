#!/bin/sh
# 05-services.sh — install the systemd units and bring the slots up.
#
#   sudo sh ffgithubrunners/05-services.sh --install
#   sh ffgithubrunners/05-services.sh --check      exit 1 if installing would change anything
#   sh ffgithubrunners/05-services.sh              report what is installed and running
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
Usage: sudo sh ffgithubrunners/05-services.sh --install [options]

Renders ffgithubrunners/systemd/*.service into ${UNIT_DIR} and enables one slot per configured
slot. Idempotent — re-run any time.

Options (alphabetical):
  --check       Exit 1 if installing would change anything. Needs no root.
  --force       Install even when the units were installed from a different checkout.
  --help        Show this message.
  --install     Write the units, enable the slots, start the target. Needs root.
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

UNITS="ffgithubrunners@.service ffgithubrunners.target ffgithubrunners-dockerd-wait.service ffghr-egress.service ffgithubrunners-reap.service ffgithubrunners-reap.timer ffgithubrunners-image.service ffgithubrunners-image.timer"
TIMERS="ffgithubrunners-reap.timer ffgithubrunners-image.timer"

# --- render ------------------------------------------------------------------------------------

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

for u in $UNITS; do
  sed -e "s|@USER@|$OWNER|g" \
      -e "s|@GROUP@|$OWNER_GROUP|g" \
      -e "s|@HOME@|$OWNER_HOME|g" \
      -e "s|@CUSER@|$CONTAINER_USER|g" \
      -e "s|@SLOTSH@|$HERE/slot.sh|g" \
      -e "s|@IMAGESH@|$HERE/03-image.sh|g" \
      -e "s|@WAITDOCKER@|$HERE/wait-for-docker.sh|g" \
      -e "s|@REAPSH@|$HERE/reap.sh|g" \
      -e "s|@IMAGEUPDATESH@|$HERE/image-update.sh|g" \
      -e "s|@DOCKERSOCK@|$DOCKER_SOCK|g" \
      -e "s|@LOGDIR@|$LOG_DIR|g" \
      -e "s|@CONFIGDIR@|$FFGHR_CONFIG_DIR|g" \
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

# Slots that should be enabled, and slots that should not be any more.
want_slots=""
i=1
while [ "$i" -le "$SLOTS" ]; do want_slots="$want_slots $i"; i=$((i + 1)); done
# ENABLED TEMPLATE INSTANCES ARE SYMLINKS, NOT UNIT FILES. `systemctl list-unit-files
# 'ffgithubrunners@*.service'` lists the TEMPLATE and never the instances, so it reports nothing
# however many slots are enabled. Enabling ffgithubrunners@1 creates
# ffgithubrunners.target.wants/ffgithubrunners@1.service, and that directory is the record.
# Getting this wrong is not cosmetic: it is also what decides which slots to DISABLE when the
# slot count goes down, so a wrong answer here means `slots 1` never turns slot 2 off.
enabled_now=$(ls "$UNIT_DIR/ffgithubrunners.target.wants" 2>/dev/null \
              | sed -n 's/^ffgithubrunners@\([0-9]*\)\.service$/\1/p' | tr '\n' ' ')

recorded=$(cat "$RECORD" 2>/dev/null || echo "")

# --- --check and the bare report ------------------------------------------------------------------

if [ "$INSTALL" -eq 0 ]; then
  printf 'checkout:     %s\n' "$HERE"
  printf 'recorded:     %s\n' "${recorded:-<none>}"
  printf 'run user:     %s (%s), home %s\n' "$OWNER" "$OWNER_GROUP" "$OWNER_HOME"
  printf 'slots wanted: %s\n' "$SLOTS"
  printf 'slots enabled:%s\n' "${enabled_now:- none}"
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
  for s in $want_slots; do
    printf '  slot %-3s %s\n' "$s" "$(systemctl is-active "ffgithubrunners@$s.service" 2>/dev/null || true)"
  done
  if [ "$CHECK" -eq 1 ]; then
    [ -z "$changed" ] || { printf '\n--check: units differ from this checkout\n'; exit 1; }
    for s in $want_slots; do
      case " $enabled_now " in *" $s "*) ;; *) printf '\n--check: slot %s is not enabled\n' "$s"; exit 1 ;; esac
    done
    printf '\n--check: installed units match this checkout and config\n'
  elif [ -z "$changed" ] && [ -n "$enabled_now" ]; then
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

# Enable what should run and disable what should not, so lowering the slot count actually lowers it.
for s in $enabled_now; do
  case " $want_slots " in
    *" $s "*) ;;
    *) say "disabling slot $s (slots=$SLOTS)"
       systemctl disable --now "ffgithubrunners@$s.service" >/dev/null 2>&1 || true ;;
  esac
done
for s in $want_slots; do
  systemctl enable "ffgithubrunners@$s.service" >/dev/null 2>&1 || true
done

say "starting ffgithubrunners.target ($SLOTS slot(s))"
systemctl enable ffgithubrunners.target >/dev/null 2>&1 || true
systemctl restart ffgithubrunners.target

printf '\n'
for s in $want_slots; do
  skip "slot $s: $(systemctl is-active "ffgithubrunners@$s.service" 2>/dev/null || true)"
done
printf '\n'
for tm in $TIMERS; do
  skip "$tm next: $(systemctl show "$tm" -p NextElapseUSecRealtime --value 2>/dev/null || echo unknown)"
done
skip "watch:  journalctl -u 'ffgithubrunners@*' -f"
skip "a job's own log: $LOG_DIR/slot-N.log"
