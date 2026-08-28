#!/bin/sh
# 02-daemon.sh — bring up ffbox-container's rootless Docker daemon on its stable socket.
#
# Installs systemd/ffbox-container-dockerd.service into that account's USER systemd instance,
# enables it, starts it, and does not return until the daemon answers. A no-op when it is already
# running, so this is safe to re-run after a config change or a reboot.
#
# THE TEMPLATE IN systemd/ IS THE ONLY SOURCE. It is rendered into a throwaway directory and
# installed from there, so no second copy on disk can disagree with git.
#
# Needs root only to write into another account's home and to drive its user manager. Everything
# it starts runs as ffbox-container, which owns nothing.
#
# Run 01-hostSetup.sh first: this script fails clearly rather than creating the account itself,
# because an account that appears as a side effect of the wrong script is how one ends up with two.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

CHECK_ONLY=0
DEADLINE=90
OWNER=""

usage() {
  cat <<EOF
Usage: sh ffgithubrunners/02-daemon.sh [options]

Installs and starts the rootless Docker daemon for the container account, on the stable socket
from lib/config.sh. Idempotent — re-run any time.

Options (alphabetical):
  --check         Report whether the daemon is installed and answering; change nothing.
  --help          Show this message.
  --owner USER    The account that runs the supervisor (default: as 01-hostSetup.sh resolves it).
  --timeout SECS  How long to wait for the daemon to answer (default: ${DEADLINE}).
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --check)   CHECK_ONLY=1; shift ;;
    --help|-h) usage; exit 0 ;;
    --owner)   OWNER=${2:?--owner needs a user}; shift 2 ;;
    --timeout) DEADLINE=${2:?--timeout needs seconds}; shift 2 ;;
    *)         echo "02-daemon.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
done

say()  { printf '==> %s\n' "$*"; }
skip() { printf '    %s\n' "$*"; }
die()  { printf '02-daemon.sh: %s\n' "$*" >&2; exit 1; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

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

HOME=${OWNER_HOME%/} . "$HERE/lib/config.sh"

CUSER=$CONTAINER_USER
id "$CUSER" >/dev/null 2>&1 || die "no such user: $CUSER. Run 01-hostSetup.sh first."
CUID=$(id -u "$CUSER")
CHOME=$(getent passwd "$CUSER" | cut -d: -f6)
UNIT_DIR="$CHOME/.config/systemd/user"
UNIT=docker.service
XDG="/run/user/$CUID"

# Drive the container account's user manager. runuser does not hand over a session, and
# systemctl --user needs both of these to find one; lingering is what makes them exist at all
# for an account nobody logs into.
as_cuser() {
  as_root runuser -u "$CUSER" -- env \
    HOME="$CHOME" \
    XDG_RUNTIME_DIR="$XDG" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG/bus" \
    "$@"
}

daemon_answers() {
  DOCKER_HOST="unix://$DOCKER_SOCK" docker version >/dev/null 2>&1
}

# "no" is three different problems with three different fixes, so never print just "no".
daemon_why() {
  _e=$(DOCKER_HOST="unix://$DOCKER_SOCK" docker version 2>&1 >/dev/null || true)
  case "$_e" in
    *"permission denied"*|*"Permission denied"*)
        echo "NO — the socket refuses this account (see 'socket group' above)" ;;
    *"Is the docker daemon running"*|*"No such file"*|*"connection refused"*)
        echo "NO — nothing is listening; the daemon is down" ;;
    *)  echo "NO — $(printf '%s' "$_e" | head -1)" ;;
  esac
}

# THE ONE THAT COST AN HOUR. dockerd sets the socket's group itself and defaults to --group
# docker, resolved against the host's /etc/group but applied inside the userns, so it lands on a
# subgid no host account is in. The directory's 0750 is then irrelevant. The socket's gid must be
# the container account's own group for the supervisor to reach it at all.
socket_group_state() {
  [ -S "$DOCKER_SOCK" ] || { echo "socket absent"; return; }
  _g=$(stat -c '%g' "$DOCKER_SOCK")
  _want=$(id -g "$CUSER")
  if [ "$_g" = "$_want" ]; then
    echo "gid $_g ($CUSER) — correct"
  else
    echo "gid $_g, want $_want ($CUSER). The unit is missing --group 0; re-run this script."
  fi
}

# --- --check --------------------------------------------------------------------------------------

if [ "$CHECK_ONLY" -eq 1 ]; then
  printf 'container user:  %s (uid %s)\n' "$CUSER" "$CUID"
  printf 'lingering:       %s\n' "$(loginctl show-user "$CUSER" -p Linger --value 2>/dev/null || echo unknown)"
  printf 'runtime dir:     %s %s\n' "$XDG" "$([ -d "$XDG" ] && echo present || echo "MISSING — lingering is off")"
  printf 'unit installed:  %s\n' "$([ -r "$UNIT_DIR/$UNIT" ] && echo "$UNIT_DIR/$UNIT" || echo MISSING)"
  printf 'socket:          %s %s\n' "$DOCKER_SOCK" \
    "$([ -S "$DOCKER_SOCK" ] && stat -c '(uid %u gid %g, mode %a)' "$DOCKER_SOCK" || echo MISSING)"
  printf 'socket group:    %s\n' "$(socket_group_state)"
  printf 'data root:       %s %s\n' "$DAEMON_ROOT" "$([ -d "$DAEMON_ROOT" ] && echo present || echo MISSING)"
  printf 'answers:         %s\n' "$(daemon_answers && echo yes || daemon_why)"
  printf 'reachable by %s: %s\n' "$OWNER" \
    "$(id -nG "$OWNER" | tr ' ' '\n' | grep -qx "$CUSER" && echo "in the group" || echo "NOT in the $CUSER group")"
  exit 0
fi

# --- preflight -------------------------------------------------------------------------------------

command -v dockerd-rootless.sh >/dev/null 2>&1 \
  || die "dockerd-rootless.sh not found. Install docker-ce-rootless-extras (01-hostSetup.sh does)."
command -v newuidmap >/dev/null 2>&1 \
  || die "newuidmap not found. Install uidmap (01-hostSetup.sh does)."
[ -n "$(awk -F: -v u="$CUSER" '$1 == u { print $2 }' /etc/subuid 2>/dev/null)" ] \
  || die "$CUSER has no /etc/subuid range; the daemon cannot start. Run 01-hostSetup.sh."
[ -d "$(dirname "$DOCKER_SOCK")" ] \
  || die "$(dirname "$DOCKER_SOCK") does not exist. Run 01-hostSetup.sh."
[ -d "$DAEMON_ROOT" ] \
  || die "$DAEMON_ROOT does not exist. Run 01-hostSetup.sh."
[ -d "$XDG" ] \
  || die "$XDG does not exist, so $CUSER has no user manager. Enable lingering:
       sudo loginctl enable-linger $CUSER"

# --- render and install ------------------------------------------------------------------------------

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

CGID=$(id -g "$CUSER")
sed -e "s|@SOCK@|$DOCKER_SOCK|g" \
    -e "s|@DATAROOT@|$DAEMON_ROOT|g" \
    -e "s|@CUSER@|$CUSER|g" \
    -e "s|@CGID@|$CGID|g" \
    "$HERE/systemd/ffbox-container-dockerd.service" > "$TMP/$UNIT"

if [ -r "$UNIT_DIR/$UNIT" ] && cmp -s "$TMP/$UNIT" "$UNIT_DIR/$UNIT"; then
  skip "$UNIT_DIR/$UNIT is already current"
  CHANGED=0
else
  say "installing $UNIT_DIR/$UNIT"
  as_root install -d -o "$CUSER" -g "$CUSER" -m 0755 "$UNIT_DIR"
  as_root install -o "$CUSER" -g "$CUSER" -m 0644 "$TMP/$UNIT" "$UNIT_DIR/$UNIT"
  CHANGED=1
fi

as_cuser systemctl --user daemon-reload

if as_cuser systemctl --user is-enabled --quiet "$UNIT" 2>/dev/null; then
  skip "$UNIT is enabled for $CUSER"
else
  say "enabling $UNIT for $CUSER"
  as_cuser systemctl --user enable "$UNIT" >/dev/null
fi

if [ "$CHANGED" -eq 1 ]; then
  # Restart rather than start: the unit changed, and a running daemon on the old socket is
  # exactly the state that makes the next hour confusing.
  say "restarting $UNIT (unit changed)"
  as_cuser systemctl --user restart "$UNIT"
elif as_cuser systemctl --user is-active --quiet "$UNIT"; then
  skip "$UNIT is already running"
else
  say "starting $UNIT"
  as_cuser systemctl --user start "$UNIT"
fi

# --- wait, and say what is wrong if it never comes ---------------------------------------------------

say "waiting for the daemon on $DOCKER_SOCK"
if ! sh "$HERE/wait-for-docker.sh" "$DOCKER_SOCK" "$DEADLINE" "$CUSER"; then
  printf '\n' >&2
  as_cuser systemctl --user status "$UNIT" --no-pager -n 30 >&2 || true
  die "the daemon did not come up (status above)"
fi

# The socket has to carry the container account's own group or the supervisor cannot use it, and
# only --group 0 produces that through the userns map. The 0750 directory keeps everyone else out.
if [ "$(stat -c '%g' "$DOCKER_SOCK")" != "$(id -g "$CUSER")" ]; then
  die "the socket is gid $(stat -c '%g' "$DOCKER_SOCK"), not $CUSER's $(id -g "$CUSER").
       dockerd was started without --group 0, so its socket landed on a mapped subgid that no
       account on this host is in. $OWNER cannot reach it. The rendered unit should carry
       --group 0; check $UNIT_DIR/$UNIT and re-run."
fi
skip "socket is gid $(id -g "$CUSER") ($CUSER), mode $(stat -c '%a' "$DOCKER_SOCK")"

VER=$(DOCKER_HOST="unix://$DOCKER_SOCK" docker version --format '{{.Server.Version}}' 2>/dev/null || echo unknown)
ROOT=$(DOCKER_HOST="unix://$DOCKER_SOCK" docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo unknown)
say "docker $VER is up, data root $ROOT"

# Delegation is what makes --memory and --pids-limit mean anything. Without it dockerd accepts
# both and enforces neither, and the ceiling in section 12 of the design would be decoration.
WARNINGS=$(DOCKER_HOST="unix://$DOCKER_SOCK" docker info --format '{{range .Warnings}}{{println .}}{{end}}' 2>/dev/null || true)
case "$WARNINGS" in
  *"No memory limit support"*|*"No cpu"*|*"No swap limit"*|*"pids"*)
    printf '\n'
    printf '    WARNING: this daemon reports missing cgroup support:\n' >&2
    printf '%s' "$WARNINGS" | sed 's/^/      /' >&2
    printf '    --memory and --pids-limit will be accepted and NOT enforced. Check Delegate=yes on\n' >&2
    printf '    user@%s.service before trusting the ceilings in section 12.\n' "$CUID" >&2
    ;;
  *) skip "cgroup delegation looks right (no memory/pids warnings from docker info)" ;;
esac

printf '\n'
skip "next: sh $HERE/03-image.sh"
