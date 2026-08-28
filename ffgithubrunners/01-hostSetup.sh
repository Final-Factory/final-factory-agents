#!/bin/sh
# 01-hostSetup.sh — everything on this machine that has to exist before a runner can start, and
# nothing that a job ever touches.
#
# WHAT THIS BUILDS
#
#   ffbox-container      the account every job's container runs under. No login shell, no sudo,
#                        no docker group, nothing in its home. A container escape lands here and
#                        finds nothing worth having. This is finding F1's account split, for this
#                        system.
#   /run/ffbox-container the daemon's socket directory, 0750, group-readable by the account that
#                        runs the supervisor. NOT /run/user/<uid>, which logind owns at 0700 on a
#                        tmpfs it recreates per session and which does not exist at all for an
#                        account that never logs in.
#   the daemon's store   its own ZFS dataset, outside the boot environment, sync=disabled, with a
#                        quota.
#   /var/log/ffgithubrunners  where slot.sh tees container output, with a logrotate rule. `docker
#                        run --rm` would otherwise take the log with the container.
#
# NO SUDOERS FILE AND NO FIREWALL RULE. Nothing in this system needs privilege at run time: the
# supervisor talks to a socket it can already reach, and the CLI's state-changing verbs are flag
# files. Under the rootless daemon the egress bridge lives in rootlesskit's network namespace, so
# the host is not on the other side of it and there is nothing for an iptables rule to drop.
#
# Safe to re-run. Every step is skipped when it is already satisfied. The account, its subuid
# range and its group membership can equally be created by hand — see phase 0 of
# design/ffgithubrunners_tasks.md — and this script then finds them and moves on.
#
# Needs root for the account, the packages, the dataset and the files under /etc. It re-invokes
# itself through sudo where needed, so run it as the human who will operate this.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

POOL=""
DAEMON_DS=""
DO_INSTALL=1
CHECK_ONLY=0
OWNER=""

usage() {
  cat <<EOF
Usage: sh ffgithubrunners/01-hostSetup.sh [options]

Provisions the host for ffgithubrunners: the ffbox-container account, its socket directory, the
rootless daemon's store, and the log directory. Idempotent — re-run any time.

Options (alphabetical):
  --check          Report what is and is not in place; change nothing. Needs no root.
  --dataset NAME   Dataset for the daemon's store (default: <pool>/ff/container-docker).
  --help           Show this message.
  --no-install     Do not install packages; only do the account and storage work.
  --owner USER     The account that runs the supervisor and joins the container group
                   (default: FFGITHUBRUNNERS_RUN_USER, then SUDO_USER, then the checkout owner).
  --pool NAME      ZFS pool to build in (default: the pool holding /).
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --check)      CHECK_ONLY=1; shift ;;
    --dataset)    DAEMON_DS=${2:?--dataset needs a name}; shift 2 ;;
    --help|-h)    usage; exit 0 ;;
    --no-install) DO_INSTALL=0; shift ;;
    --owner)      OWNER=${2:?--owner needs a user}; shift 2 ;;
    --pool)       POOL=${2:?--pool needs a name}; shift 2 ;;
    *)            echo "01-hostSetup.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
done

say()  { printf '==> %s\n' "$*"; }
skip() { printf '    %s\n' "$*"; }
warn() { printf '    WARNING: %s\n' "$*" >&2; }
die()  { printf '01-hostSetup.sh: %s\n' "$*" >&2; exit 1; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

# WHOSE MACHINE THIS IS, most explicit source first. SUDO_USER is only meaningful when we are
# actually root: it lingers in the environment of any shell that was itself started under sudo,
# and trusting it elsewhere would add the wrong account to the group that reaches the daemon.
# It is also absent under systemd, which is how an unattended re-run would arrive.
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

# Read the config as the OWNER, not as root. ffbox has been bitten twice by a root-run stage
# reading /root/.config and provisioning a machine for an account that never uses it.
HOME=${OWNER_HOME%/} . "$HERE/lib/config.sh"

CUSER=$CONTAINER_USER
SOCK_DIR=$(dirname "$DOCKER_SOCK")
TMPFILES=/etc/tmpfiles.d/ffbox-container.conf
LOGROTATE=/etc/logrotate.d/ffgithubrunners

# --- inspection helpers ------------------------------------------------------------------------

have_user()  { id "$1" >/dev/null 2>&1; }
have_ds()    { zfs list -H -o name "$1" >/dev/null 2>&1; }
in_group()   { id -nG "$1" 2>/dev/null | tr ' ' '\n' | grep -qx "$2"; }
linger_on()  { [ "$(loginctl show-user "$1" -p Linger --value 2>/dev/null)" = yes ]; }

# One line per user in /etc/subuid is what shadow writes and what rootless docker reads. More
# than one is legal and rootlesskit uses only the first, so report the count rather than assuming.
subid_range() {  # $1 = file, $2 = user -> "start count", empty if absent
  awk -F: -v u="$2" '$1 == u { print $2, $3; exit }' "$1" 2>/dev/null
}

# Overlapping ranges are the failure that looks like nothing until two daemons map the same host
# uids and one of them writes files the other owns.
ranges_overlap() {  # $1 start $2 count $3 start $4 count
  _a=$1; _an=$2; _b=$3; _bn=$4
  [ -n "$_a" ] && [ -n "$_b" ] || return 1
  [ "$_a" -lt "$((_b + _bn))" ] && [ "$_b" -lt "$((_a + _an))" ]
}

# --- pool and dataset --------------------------------------------------------------------------

if command -v zfs >/dev/null 2>&1; then
  if [ -z "$POOL" ]; then
    root_ds=$(df --output=source / 2>/dev/null | tail -1)
    case "$root_ds" in */*) POOL=${root_ds%%/*} ;; *) POOL="" ;; esac
  fi
  # Under ff/ with ffbox's own store, because it is this pair of systems' and not the machine's.
  [ -n "$DAEMON_DS" ] || [ -z "$POOL" ] || DAEMON_DS="${POOL}/ff/container-docker"
fi

# --- --check ------------------------------------------------------------------------------------

if [ "$CHECK_ONLY" -eq 1 ]; then
  printf 'owner:            %s\n' "$OWNER"
  printf 'container user:   %s %s\n' "$CUSER" \
    "$(have_user "$CUSER" && echo "(uid $(id -u "$CUSER"))" || echo "(MISSING)")"
  if have_user "$CUSER"; then
    printf '  login shell:    %s\n' "$(getent passwd "$CUSER" | cut -d: -f7)"
    printf '  sudo group:     %s\n' "$(in_group "$CUSER" sudo && echo "MEMBER — must not be" || echo "no (correct)")"
    printf '  docker group:   %s\n' "$(in_group "$CUSER" docker && echo "MEMBER — must not be" || echo "no (correct)")"
    printf '  subuid:         %s\n' "$(subid_range /etc/subuid "$CUSER" || true)"
    printf '  subgid:         %s\n' "$(subid_range /etc/subgid "$CUSER" || true)"
    printf '  lingering:      %s\n' "$(linger_on "$CUSER" && echo yes || echo "no — the daemon will not start at boot")"
  fi
  printf 'owner in group:   %s\n' "$(in_group "$OWNER" "$CUSER" \
      && echo "yes" || echo "NO — $OWNER cannot reach the socket")"
  printf 'socket dir:       %s %s\n' "$SOCK_DIR" \
    "$([ -d "$SOCK_DIR" ] && stat -c '(%U:%G %a)' "$SOCK_DIR" || echo "(absent until boot or systemd-tmpfiles)")"
  printf 'tmpfiles rule:    %s\n' "$([ -r "$TMPFILES" ] && echo present || echo MISSING)"
  printf 'daemon store:     %s %s\n' "$DAEMON_ROOT" \
    "$(have_ds "${DAEMON_DS:-none}" && echo "($DAEMON_DS, sync=$(zfs get -H -o value sync "$DAEMON_DS"), quota=$(zfs get -H -o value quota "$DAEMON_DS"))" || echo "(MISSING)")"
  printf 'log dir:          %s %s\n' "$LOG_DIR" \
    "$([ -d "$LOG_DIR" ] && stat -c '(%U:%G %a)' "$LOG_DIR" || echo MISSING)"
  printf 'logrotate rule:   %s\n' "$([ -r "$LOGROTATE" ] && echo present || echo MISSING)"
  printf 'uidmap:           %s\n' "$(command -v newuidmap >/dev/null 2>&1 && echo present || echo MISSING)"
  printf 'rootless extras:  %s\n' "$(command -v dockerd-rootless.sh >/dev/null 2>&1 && echo present || echo MISSING)"

  # Exit non-zero if anything above is not in place, so --check is a gate and not just a report.
  _ok=0
  have_user "$CUSER"                             || _ok=1
  in_group "$OWNER" "$CUSER"                     || _ok=1
  [ -n "$(subid_range /etc/subuid "$CUSER")" ]   || _ok=1
  [ -n "$(subid_range /etc/subgid "$CUSER")" ]   || _ok=1
  linger_on "$CUSER"                             || _ok=1
  [ -r "$TMPFILES" ]                             || _ok=1
  [ -d "$DAEMON_ROOT" ]                          || _ok=1
  [ -d "$LOG_DIR" ]                              || _ok=1
  [ -r "$LOGROTATE" ]                            || _ok=1
  command -v newuidmap >/dev/null 2>&1           || _ok=1
  command -v dockerd-rootless.sh >/dev/null 2>&1 || _ok=1
  if [ "$_ok" -eq 0 ]; then
    printf '\n--check: the host is provisioned\n'
  else
    printf '\n--check: something above is missing\n'
  fi
  exit "$_ok"
fi

# --- packages -------------------------------------------------------------------------------------

if [ "$DO_INSTALL" -eq 0 ]; then
  skip "packages skipped (--no-install)"
else
  MISSING=""
  command -v docker >/dev/null 2>&1            || MISSING="$MISSING docker-ce docker-ce-cli containerd.io"
  command -v dockerd-rootless.sh >/dev/null 2>&1 || MISSING="$MISSING docker-ce-rootless-extras"
  command -v newuidmap >/dev/null 2>&1         || MISSING="$MISSING uidmap"
  if [ -z "$MISSING" ]; then
    skip "docker, the rootless extras and uidmap are all present"
  else
    say "installing:$MISSING"
    # shellcheck disable=SC2086  # deliberately word-split package list
    as_root apt-get install -y $MISSING
  fi
fi

# --- the account -----------------------------------------------------------------------------------

if have_user "$CUSER"; then
  skip "$CUSER exists (uid $(id -u "$CUSER"))"
else
  # NOT --system. useradd allocates the /etc/subuid and /etc/subgid ranges rootless Docker needs
  # only for ordinary users; a system account gets none and the daemon then fails to start with a
  # message that does not mention subuid at all.
  say "creating $CUSER"
  as_root useradd --create-home --shell /usr/sbin/nologin \
                  --comment 'ffbox/ffgithubrunners container account' "$CUSER"
fi

# THE POINT OF THIS ACCOUNT IS THAT IT OWNS NOTHING. If it has picked either group up since it was
# created, stop: continuing would build the rest of the system on top of a boundary that is no
# longer there, and it would keep working, which is the bad part.
for g in sudo docker; do
  if in_group "$CUSER" "$g"; then
    die "$CUSER is in the '$g' group. That group is root-equivalent and defeats the reason this
       account exists. Remove it and re-run:  sudo gpasswd -d $CUSER $g"
  fi
done

CU_SUBUID=$(subid_range /etc/subuid "$CUSER")
CU_SUBGID=$(subid_range /etc/subgid "$CUSER")
if [ -z "$CU_SUBUID" ] || [ -z "$CU_SUBGID" ]; then
  say "allocating a subuid/subgid range for $CUSER"
  as_root usermod --add-subuids 200000-265535 --add-subgids 200000-265535 "$CUSER" \
    || die "could not allocate a subuid range. Add one by hand:
       sudo usermod --add-subuids 200000-265535 --add-subgids 200000-265535 $CUSER"
  CU_SUBUID=$(subid_range /etc/subuid "$CUSER")
  CU_SUBGID=$(subid_range /etc/subgid "$CUSER")
fi
[ -n "$CU_SUBUID" ] || die "$CUSER still has no /etc/subuid range"
skip "$CUSER subuid $CU_SUBUID, subgid $CU_SUBGID"

# The owner's own range matters because ffbox's daemon runs under it and both daemons are on this
# box until section 17 of the design retires one of them.
OW_SUBUID=$(subid_range /etc/subuid "$OWNER")
# shellcheck disable=SC2086  # both are "start count" pairs meant to be split
if [ -n "$OW_SUBUID" ] && ranges_overlap $CU_SUBUID $OW_SUBUID; then
  die "$CUSER's subuid range ($CU_SUBUID) overlaps $OWNER's ($OW_SUBUID).
       Two daemons mapping the same host uids will write each other's files. Fix one of them in
       /etc/subuid and /etc/subgid before going further."
fi

if in_group "$OWNER" "$CUSER"; then
  skip "$OWNER is already in the $CUSER group"
else
  say "adding $OWNER to the $CUSER group, so it can reach $DOCKER_SOCK"
  as_root usermod -aG "$CUSER" "$OWNER"
  warn "group membership takes effect in NEW sessions only. Log out and back in, or the
         supervisor units will start fine and the CLI in this shell will not see the socket."
fi

if linger_on "$CUSER"; then
  skip "lingering already enabled for $CUSER"
else
  # Nothing ever logs in as this account, so without lingering its systemd user instance does not
  # exist and the daemon has nowhere to run at boot.
  say "enabling lingering for $CUSER"
  as_root loginctl enable-linger "$CUSER"
fi

# --- the socket directory ---------------------------------------------------------------------------

# 0750 and group-owned: the owner reaches the socket through the group and nobody else on the box
# does. A tmpfiles.d rule rather than a mkdir, because /run is a tmpfs and does not survive a boot.
if [ -r "$TMPFILES" ] && grep -q "$SOCK_DIR" "$TMPFILES"; then
  skip "$TMPFILES already covers $SOCK_DIR"
else
  say "writing $TMPFILES for $SOCK_DIR"
  printf 'd %s 0750 %s %s -\n' "$SOCK_DIR" "$CUSER" "$CUSER" | as_root tee "$TMPFILES" >/dev/null
fi
as_root systemd-tmpfiles --create "$TMPFILES"
[ -d "$SOCK_DIR" ] || die "$SOCK_DIR still does not exist after systemd-tmpfiles --create"
skip "$SOCK_DIR is $(stat -c '%U:%G %a' "$SOCK_DIR")"

# --- the daemon's store -------------------------------------------------------------------------------

if [ -z "$DAEMON_DS" ]; then
  # Not fatal: a machine without ZFS can still run all of this, it just does not get the dataset's
  # properties. Say so rather than silently doing something different.
  warn "no ZFS pool found — creating $DAEMON_ROOT as an ordinary directory, with no quota and no
         sync=disabled. On this machine that is not what was intended."
  as_root mkdir -p "$DAEMON_ROOT"
elif have_ds "$DAEMON_DS"; then
  skip "$DAEMON_DS exists at $DAEMON_ROOT"
else
  # sync=disabled for the same reason ffbox's store has it: every layer here is rebuildable from a
  # Dockerfile, nothing in it is state anyone would mourn, and the image build and `docker pull`
  # are fsync-heavy enough that the ZIL dominates them. The exposure is an unclean shutdown losing
  # a half-written layer, which costs a rebuild. Never copy this onto a dataset holding a checkout.
  say "creating $DAEMON_DS at $DAEMON_ROOT (sync=disabled, quota $DAEMON_QUOTA)"
  as_root zfs create -o mountpoint="$DAEMON_ROOT" -o sync=disabled -o quota="$DAEMON_QUOTA" "$DAEMON_DS"
fi

# Applied on every run, not only at create: the properties matter more than when they were set,
# and a dataset made by hand before this script existed would otherwise never get them.
if [ -n "$DAEMON_DS" ] && have_ds "$DAEMON_DS"; then
  [ "$(zfs get -H -o value sync "$DAEMON_DS")" = disabled ] \
    || { say "setting sync=disabled on $DAEMON_DS"; as_root zfs set sync=disabled "$DAEMON_DS"; }
  [ "$(zfs get -H -o value quota "$DAEMON_DS")" != none ] \
    || { say "setting quota=$DAEMON_QUOTA on $DAEMON_DS"; as_root zfs set quota="$DAEMON_QUOTA" "$DAEMON_DS"; }
fi
as_root chown "$CUSER:$CUSER" "$DAEMON_ROOT"
as_root chmod 0700 "$DAEMON_ROOT"

# --- the log directory -----------------------------------------------------------------------------------

# Written by the supervisor, which runs as the OWNER, so the directory is theirs. `docker run --rm`
# discards the container's own logs, and this is the only copy of what a job printed.
if [ -d "$LOG_DIR" ]; then
  skip "$LOG_DIR exists"
else
  say "creating $LOG_DIR"
  as_root mkdir -p "$LOG_DIR"
fi
as_root chown "$OWNER:$(id -gn "$OWNER")" "$LOG_DIR"
as_root chmod 0755 "$LOG_DIR"

if [ -r "$LOGROTATE" ]; then
  skip "$LOGROTATE exists"
else
  say "writing $LOGROTATE"
  # copytruncate: slot.sh tees into an open file descriptor and does not reopen it, so a rename
  # would leave it writing to a rotated inode nobody reads. daily+7 is a week of jobs at one slot.
  as_root tee "$LOGROTATE" >/dev/null <<EOF
$LOG_DIR/*.log {
    daily
    rotate 7
    missingok
    notifempty
    compress
    delaycompress
    copytruncate
    su $OWNER $(id -gn "$OWNER")
}
EOF
fi

say "host setup complete"
printf '\n'
skip "next: sh $HERE/02-daemon.sh"
if ! in_group "$OWNER" "$CUSER"; then
  skip "and log out and back in first, or $OWNER will not see $DOCKER_SOCK"
fi
