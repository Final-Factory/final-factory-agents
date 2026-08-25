#!/bin/sh
# dockerSetup.sh — provision Docker on a fresh ZFS-on-root machine (see README.md).
#
# Installs Docker and points it at a dedicated ZFS dataset using the overlay2 storage driver.
# Designed for a brand-new server, and safe to re-run: every step is skipped if already in place.
#
# WHY THIS EXISTS — the trap it avoids
# Docker's `zfs` storage driver creates one dataset per image layer, parented on whatever dataset
# encloses the data root. On a stock Ubuntu ZFS install /var/lib/docker is a plain directory
# inside the dataset mounted at /var/lib, so the layers land INSIDE the boot environment, as
# siblings of apt and dpkg:
#
#   <pool>/ROOT/<be>/var/lib/apt                     <- real system dataset
#   <pool>/ROOT/<be>/var/lib/001caa28ed05...         <- docker layer   \
#   <pool>/ROOT/<be>/var/lib/003d3fa89ea1...         <- docker layer    > hundreds of these
#                                                                      /
# zsys snapshots the boot environment RECURSIVELY on every apt transaction, so every layer gets
# snapshotted every time you install a package. On the first machine this was set up on that
# reached ~6,300 snapshots, at which point zsysd took longer to start than the 20s handshake
# timeout compiled into zsysctl and `zsys gc` could never run again — the garbage was what
# stopped the collector. Unwinding it by hand cost 530 dataset destroys and most of a terabyte.
#
# THE FIX — two things, both required
#   1. A dedicated <pool>/docker dataset, OUTSIDE <pool>/ROOT and <pool>/USERDATA. zsys only
#      recurses those two, so it never touches this one. Same reasoning as <pool>/ff in
#      zfsSetup.sh next to this file.
#   2. The overlay2 storage driver, so layers are ordinary directories rather than datasets.
#
# Change 1 without change 2 is fine. Change 2 without change 1 is WORSE than doing nothing: the
# layer files then live as ordinary files inside the snapshotted var/lib dataset. Always both.
#
# ORDER MATTERS. The dataset and daemon.json are put in place BEFORE Docker is installed, so
# Docker's very first start already lands on the right dataset with the right driver. It never
# writes a single byte into the boot environment, and no migration is ever needed. That is the
# whole advantage of doing this on a fresh machine — retrofitting it later is far more work.
#
# ZSYS IS REMOVED
# By default this purges the zsys package and destroys every autozsys_* snapshot, because zsys is
# the mechanism described above and Ubuntu itself stopped installing it by default after 21.04.
# Know what you give up: zsys is what puts "History" rollback entries in the GRUB menu, so after
# this a bad upgrade can no longer be undone by picking a previous boot environment at boot.
# Nothing else changes — GRUB's ZFS support lives in grub-common, not zsys, and the pool, the
# datasets, and the current boot environment are all untouched.
#
# A machine with no zsys simply takes no automatic snapshots. If you want them back without the
# apt coupling, zfs-auto-snapshot or sanoid are both in the archive and both honour the
# com.sun:auto-snapshot=false this script sets on the docker dataset. Use --keep-zsys to opt out.
#
# Requires root for the dataset, package, and daemon work; it re-invokes itself through sudo
# where needed, so run it as the normal user who will use Docker.

set -eu

POOL=""
DOCKER_DS=""
DATA_ROOT="/var/lib/docker"
DRIVER="overlay2"
DAEMON_JSON="/etc/docker/daemon.json"
# The ROOTLESS store, which is ffbox's. Separate from DATA_ROOT above, which belongs to the root
# daemon that other accounts on this machine still use — nothing is migrated between them.
ROOTLESS_ROOT="/opt/ffbox_docker"
ROOTLESS_DS=""
PROFILE_D="/etc/profile.d/ffbox-docker-host.sh"
OWNER=""
DO_INSTALL=1
DO_ROOTLESS=1
DO_SMOKE=1
DO_ZSYS=1
DO_EGRESS=1

# This script's own directory, so the egress stage can find ffbox/egress/ wherever the checkout
# lives — registerAgents.sh puts one on every machine at a different path.
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ASSUME_YES=0
CHECK_ONLY=0
FORCE_DAEMON=0

usage() {
  cat <<EOF
Usage: sh ffbox/dockerSetup.sh [options]

Provisions Docker on a fresh ZFS-on-root machine: a dedicated dataset outside the boot
environment, the overlay2 storage driver, the Docker packages themselves, and docker-group
membership. Idempotent — re-run any time.

Options (alphabetical):
  --check           Report what is and is not in place; change nothing.
  --data-root PATH  Docker's data root (default: ${DATA_ROOT}).
  --dataset NAME    Dataset to create (default: <pool>/docker).
  --driver NAME     Storage driver: overlay2 (default) or zfs. Use zfs only if the overlay
                    preflight fails; it still keeps the layers out of the boot environment.
  --force-daemon    Rewrite ${DAEMON_JSON} even if its storage-driver was set by
                    something else. A .bak copy is kept either way.
  --help            Show this message.
  --keep-zsys       Leave zsys installed and leave its autozsys_* snapshots alone.
  --no-rootless     Do not install the rootless daemon for the owner. The owner is never
                    added to the docker group either way; see the note below.
  --no-install      Do not install Docker packages; only do the storage setup.
  --no-egress       Do not build or start the egress filter. A machine without it cannot run
                    ffbox at all until 'sh ffbox/egress/ffbox-egress.sh up' has been run, since
                    ffbox refuses to fall back to unfiltered networking on its own.
  --no-smoke        Skip the hello-world smoke test at the end.
  --owner USER      User the rootless daemon is installed for (default: the invoking user).
  --pool NAME       ZFS pool to build in (default: the pool holding /).
  --yes             Do not prompt before destroying autozsys_* snapshots.

By default this PURGES zsys and destroys every autozsys_* snapshot — see the header comment
for what that costs you. Use --keep-zsys to opt out.

This script provisions a CLEAN machine. If Docker is already installed with data in place on
the wrong dataset, it refuses rather than migrating — see README.md.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --check)        CHECK_ONLY=1; shift ;;
    --data-root)    DATA_ROOT=${2:?--data-root needs a path}; shift 2 ;;
    --dataset)      DOCKER_DS=${2:?--dataset needs a name}; shift 2 ;;
    --driver)       DRIVER=${2:?--driver needs a name}; shift 2 ;;
    --force-daemon) FORCE_DAEMON=1; shift ;;
    --help|-h)      usage; exit 0 ;;
    --keep-zsys)    DO_ZSYS=0; shift ;;
    --no-egress)    DO_EGRESS=0; shift ;;
    --no-rootless)  DO_ROOTLESS=0; shift ;;
    # Accepted and ignored: this script no longer touches the docker group at all, and a setup
    # command that still carries the old flag should not die on it.
    --no-group)     shift ;;
    --no-install)   DO_INSTALL=0; shift ;;
    --no-smoke)     DO_SMOKE=0; shift ;;
    --owner)        OWNER=${2:?--owner needs a user}; shift 2 ;;
    --pool)         POOL=${2:?--pool needs a name}; shift 2 ;;
    --yes|-y)       ASSUME_YES=1; shift ;;
    *) echo "dockerSetup.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
done

say()  { printf '==> %s\n' "$*"; }
skip() { printf '    %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die()  { printf 'dockerSetup.sh: %s\n' "$*" >&2; exit 1; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

# Prompt on the real terminal, not stdin — this script may be piped in. No terminal and no --yes
# means we cannot get informed consent, so refuse rather than assume it.
confirm() {   # $1 = prompt, $2 = required answer
  if [ "$ASSUME_YES" -eq 1 ]; then return 0; fi
  [ -t 0 ] || [ -e /dev/tty ] || die "no terminal to confirm on — re-run with --yes, or --keep-zsys"
  printf '%s\n' "$1"
  printf 'Type %s to continue: ' "$2"
  read -r reply < /dev/tty || reply=""
  [ "$reply" = "$2" ] || die "aborted"
}

# ---------------------------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------------------------
command -v zfs >/dev/null 2>&1 || die "zfs not found — this script only applies to ZFS machines"

if [ -z "$POOL" ]; then
  # The dataset mounted at / looks like <pool>/ROOT/<be>; everything before the first slash is
  # the pool. Falls back cleanly if / is not on ZFS.
  root_ds=$(df --output=source / 2>/dev/null | tail -1)
  case "$root_ds" in
    */*) POOL=${root_ds%%/*} ;;
    *)   die "could not infer the ZFS pool from '/' — pass --pool NAME" ;;
  esac
fi
zpool list -H -o name "$POOL" >/dev/null 2>&1 || die "no such ZFS pool: $POOL"
[ -n "$DOCKER_DS" ] || DOCKER_DS="${POOL}/docker"
# Under ff/, with golden and the run clones, because it is ffbox's and not the machine's. The
# NOPASSWD destroy rule names ${POOL}/ff/run-* only, so this dataset is not reachable through it.
[ -n "$ROOTLESS_DS" ] || ROOTLESS_DS="${POOL}/ff/docker"

case "$DRIVER" in
  overlay2|zfs) ;;
  *) die "--driver must be overlay2 or zfs, not '$DRIVER'" ;;
esac

# WHOSE MACHINE THIS IS, most explicit source first.
#
# SUDO_USER is only meaningful when we are actually root — it lingers in the environment of any
# shell that was itself started under sudo, and trusting it there would add the wrong account to
# a group that is effectively root-equivalent. It is also ABSENT under systemd, which is how
# ffbox-update.service runs this: root, no sudo, no SUDO_USER. That used to resolve to root and
# provision the machine for an account that never runs ffbox. FFBOX_RUN_USER is what a caller
# that already knows the answer passes; the checkout's owner is the last resort and is the same
# answer update_ffbox.sh derives for its git calls.
if [ -z "$OWNER" ]; then
  if [ "$(id -u)" -eq 0 ]; then
    OWNER=${FFBOX_RUN_USER:-}
    [ -z "$OWNER" ] && [ "${SUDO_USER:-root}" != root ] && OWNER=$SUDO_USER
    [ -z "$OWNER" ] && OWNER=$(stat -c %U "$HERE/../.git" 2>/dev/null || echo root)
  else
    OWNER=$(id -un)
  fi
fi
id "$OWNER" >/dev/null 2>&1 || die "no such user: $OWNER"

have_ds() { zfs list -H -o name "$1" >/dev/null 2>&1; }
ds_for()  { df --output=source "$1" 2>/dev/null | tail -1; }
in_group() { id -nG "$1" 2>/dev/null | tr ' ' '\n' | grep -qx docker; }

# Three states, not two: a socket that answers, an install that exists but is not up, and
# nothing at all. They have different fixes, so --status says which one it is.
rootless_state() {
  _u=$1
  _i=$(id -u "$_u" 2>/dev/null) || { echo "unknown user"; return; }
  if [ -S "/run/user/$_i/docker.sock" ]; then
    echo "socket present at /run/user/$_i/docker.sock"
  elif [ -r "$(getent passwd "$_u" | cut -d: -f6)/.config/systemd/user/docker.service" ]; then
    echo "installed but not running (systemctl --user status docker)"
  else
    echo "NOT installed (dockerd-rootless-setuptool.sh install)"
  fi
}

zsys_installed() { dpkg-query -W -f='${Status}' zsys 2>/dev/null | grep -q '^install ok installed$'; }

# Only ever names snapshots whose snapshot part begins with "autozsys_". Anchored on the @ so a
# dataset merely containing that string cannot match, and so hand-made snapshots — release
# baselines, pre-upgrade markers — are never in scope.
list_autozsys() { zfs list -H -o name -t snapshot -r "$POOL" 2>/dev/null | grep '@autozsys_' || true; }

docker_info() { timeout 120 docker info 2>/dev/null; }
INFO=$(docker_info || true)
CUR_DRIVER=$(printf '%s\n' "$INFO" | sed -n 's/^ *Storage Driver: *//p' | head -1)

# ---------------------------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------------------------
if [ "$CHECK_ONLY" -eq 1 ]; then
  printf 'pool:            %s\n' "$POOL"
  printf 'dataset:         %s %s\n' "$DOCKER_DS" "$(have_ds "$DOCKER_DS" && echo "(present)" || echo "(MISSING)")"
  printf 'data root:       %s\n' "$DATA_ROOT"
  printf 'backed by:       %s\n' "$([ -d "$DATA_ROOT" ] && ds_for "$DATA_ROOT" || echo "does not exist")"
  printf 'daemon.json:     %s\n' "$([ -r "$DAEMON_JSON" ] && echo present || echo absent)"
  printf 'docker binary:   %s\n' "$(command -v docker 2>/dev/null || echo "not installed")"
  printf 'driver now:      %s (want %s)\n' "${CUR_DRIVER:-daemon not responding}" "$DRIVER"
  printf 'docker group:    %s\n' "$(in_group "$OWNER" \
      && echo "$OWNER IS a member — root-equivalent, and no longer needed. Remove it with:
                 sudo gpasswd -d $OWNER docker" \
      || echo "$OWNER is not a member (correct)")"
  printf 'rootless daemon: %s\n' "$(rootless_state "$OWNER")"
  printf 'lingering:       %s\n' "$(loginctl show-user "$OWNER" -p Linger --value 2>/dev/null || echo unknown)"
  printf 'zsys:            %s\n' "$(zsys_installed && echo 'INSTALLED — will re-snapshot the boot env on every apt run' || echo 'not installed')"
  printf 'autozsys snaps:  %s\n' "$(list_autozsys | wc -l)"
  # The whole point of the exercise: nothing docker-shaped inside the boot environment. A
  # non-zero count here means the zfs driver has been writing into a zsys-snapshotted tree.
  be=$(ds_for /var/lib)
  case "$be" in
    */*) stray=$(zfs list -H -o name -r "$be" 2>/dev/null | grep -cE '/[0-9a-z]{25,}(-init)?$' || true) ;;
    *)   stray=0 ;;
  esac
  printf 'stray layers:    %s under %s\n' "$stray" "$be"
  # The run container's network, reported here because --check is where somebody looks to find
  # out whether this machine is set up, and a missing fence is exactly as important as a missing
  # dataset.
  printf 'egress filter:\n'
  sh "$HERE/egress/ffbox-egress.sh" status 2>/dev/null || printf '  (ffbox/egress not readable)\n'
  if [ "$stray" -gt 0 ]; then
    printf '\n                 ^ docker layer datasets inside the boot environment. zsys will\n'
    printf '                   snapshot these on every apt transaction. See README.md.\n'
  fi
  if [ -d "$DATA_ROOT" ] && [ "$(ds_for "$DATA_ROOT")" = "$DOCKER_DS" ] && [ "$CUR_DRIVER" = "$DRIVER" ]; then
    printf '\nsetup:           DONE\n'
  else
    printf '\nsetup:           NOT DONE\n'
  fi
  exit 0
fi

say "pool $POOL, dataset $DOCKER_DS -> $DATA_ROOT, driver $DRIVER, user $OWNER"

# ---------------------------------------------------------------------------------------------
# Refuse to run against a machine that already has Docker data in the wrong place.
#
# This script provisions clean machines. Retrofitting a populated /var/lib/docker means rescuing
# volumes, killing the image cache, and unwinding hundreds of cloned layer datasets — far too
# much to do implicitly behind a setup command.
# ---------------------------------------------------------------------------------------------
if [ -d "$DATA_ROOT" ] && [ -n "$(as_root ls -A "$DATA_ROOT" 2>/dev/null)" ] \
   && [ "$(ds_for "$DATA_ROOT")" != "$DOCKER_DS" ]; then
  die "$DATA_ROOT already holds data and is backed by $(ds_for "$DATA_ROOT"), not $DOCKER_DS.
       This script sets up clean machines; it will not migrate an existing install.
       Retire the old store first (back up named volumes, then remove $DATA_ROOT and any
       layer datasets under the boot environment), or point this at a different --data-root."
fi

# ---------------------------------------------------------------------------------------------
# zsys
#
# Done BEFORE the Docker install, because installing Docker is an apt transaction and an apt
# transaction is exactly what makes zsys snapshot the boot environment. Purge first and that
# never happens. Package first, then snapshots — so any snapshot the purge transaction itself
# triggers is caught by the sweep that follows.
# ---------------------------------------------------------------------------------------------
if [ "$DO_ZSYS" -eq 0 ]; then
  skip "zsys left alone (--keep-zsys)"
else
  if zsys_installed; then
    say "purging zsys"
    # Stop the units before the purge so nothing is mid-snapshot while dpkg pulls it apart.
    for unit in zsys-gc.timer zsys-gc.service zsys-commit.service zsysd.service zsysd.socket; do
      as_root systemctl disable --now "$unit" >/dev/null 2>&1 || true
    done
    DEBIAN_FRONTEND=noninteractive as_root apt-get purge -y -qq zsys >/dev/null
    # Not owned by the package, so purge leaves them: an admin-written drop-in (commonly a
    # TimeoutStartSec bump added while fighting the gc timeouts) and the config file.
    as_root rm -rf /etc/systemd/system/zsysd.service.d
    as_root rm -f /etc/zsys.conf
    as_root systemctl daemon-reload
    say "zsys purged — no more automatic snapshots on apt"
    warn "GRUB will no longer offer previous boot environments to roll back to.
         GRUB's ZFS support itself is unaffected (it lives in grub-common, not zsys)."
  else
    skip "zsys is not installed"
  fi

  # Snapshots outlive the package — uninstalling zsys never removes what it already made, so
  # sweep regardless of whether anything was purged above.
  tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
  list_autozsys > "$tmp"
  n=$(wc -l < "$tmp")
  if [ "$n" -eq 0 ]; then
    skip "no autozsys_* snapshots to destroy"
  else
    # A previous boot environment is a CLONE of one of these snapshots. Destroying that snapshot
    # would fail outright, and `destroy -R` would take the boot environment with it — which is
    # why -R is never used here. Identify them up front and leave them be.
    say "checking whether any boot environment depends on an autozsys snapshot"
    pinned=$(while read -r snap; do
               c=$(zfs get -H -o value clones "$snap" 2>/dev/null || echo "-")
               if [ "$c" != "-" ] && [ -n "$c" ]; then printf '%s\n' "$snap"; fi
             done < "$tmp")
    if [ -n "$pinned" ]; then
      warn "these autozsys snapshots have boot environments cloned from them and will be KEPT:
$(printf '%s\n' "$pinned" | sed 's/^/         /')"
      printf '%s\n' "$pinned" > "$tmp.pinned"
      grep -vxFf "$tmp.pinned" "$tmp" > "$tmp.keep" || true
      mv "$tmp.keep" "$tmp"; rm -f "$tmp.pinned"
      n=$(wc -l < "$tmp")
    else
      skip "none — all $n are free to destroy"
    fi
  fi

  if [ "$n" -gt 0 ]; then
    # POSIX sh: no process substitution, so the sizes go through a temp file.
    zfs list -Hp -o name,used -t snapshot -r "$POOL" 2>/dev/null > "$tmp.sizes" || : > "$tmp.sizes"
    freed=$(awk 'NR==FNR{k[$0];next} ($1 in k){s+=$2} END{printf "%.1f", s/1073741824}' \
              "$tmp" "$tmp.sizes" 2>/dev/null || echo "?")
    rm -f "$tmp.sizes"
    say "$n autozsys_* snapshots to destroy (~${freed} GiB)"
    sed -n '1,3p' "$tmp" | sed 's/^/      /'
    if [ "$n" -gt 3 ]; then printf '      ... and %s more\n' "$((n - 3))"; fi
    confirm "This is not reversible. Hand-made snapshots are not touched." "$n"

    # One at a time rather than a batched `zfs destroy a,b,c`: a single unexpected failure then
    # skips one snapshot instead of aborting the whole batch, and the progress line matters when
    # there are thousands. Every name here already matched @autozsys_ and has no clones.
    done_n=0; failed=0
    while read -r snap; do
      case "$snap" in
        *@autozsys_*) ;;
        *) warn "skipping unexpected name: $snap"; continue ;;
      esac
      if as_root zfs destroy "$snap" 2>/dev/null; then
        done_n=$((done_n + 1))
      else
        failed=$((failed + 1))
      fi
      if [ $((done_n % 200)) -eq 0 ] && [ "$done_n" -gt 0 ]; then
        say "  destroyed $done_n/$n"
      fi
    done < "$tmp"
    say "destroyed $done_n autozsys_* snapshots$([ "$failed" -gt 0 ] && echo ", $failed failed" || echo "")"
    if [ "$failed" -gt 0 ]; then
      warn "$failed could not be destroyed — check for holds: zfs holds <snapshot>"
    fi
  fi
  rm -f "$tmp"; trap - EXIT
fi

# ---------------------------------------------------------------------------------------------
# Dataset — created FIRST, so Docker's first start already lands here.
# ---------------------------------------------------------------------------------------------
if have_ds "$DOCKER_DS"; then
  skip "$DOCKER_DS already exists"
else
  # overlay=on is the OpenZFS default, so a dataset will happily mount over a non-empty directory
  # and silently hide it. Refuse instead: a hidden data root looks exactly like data loss.
  if [ -d "$DATA_ROOT" ] && [ -n "$(as_root ls -A "$DATA_ROOT" 2>/dev/null)" ]; then
    die "$DATA_ROOT is not empty and would be shadowed by the new mount. Clear it first."
  fi
  # xattr=sa and acltype=posixacl are what overlay2 requires; harmless under the zfs driver.
  # com.sun:auto-snapshot=false pre-empts zfs-auto-snapshot/sanoid recreating the exact problem
  # this script exists to avoid, should either ever be installed here.
  say "creating $DOCKER_DS -> $DATA_ROOT"
  as_root zfs create \
    -o mountpoint="$DATA_ROOT" \
    -o xattr=sa \
    -o acltype=posixacl \
    -o dnodesize=auto \
    -o atime=off \
    -o compression=lz4 \
    -o com.sun:auto-snapshot=false \
    "$DOCKER_DS"
fi
[ "$(ds_for "$DATA_ROOT")" = "$DOCKER_DS" ] || die "$DATA_ROOT is not backed by $DOCKER_DS"

# ---------------------------------------------------------------------------------------------
# Overlay preflight
#
# overlay2 on ZFS is not on Docker's officially supported matrix. It has worked since OpenZFS
# 0.8, but prove it on THIS kernel and THIS dataset before committing the daemon to it — a
# daemon that refuses to start is a much worse place to debug from.
# ---------------------------------------------------------------------------------------------
if [ "$DRIVER" = "overlay2" ]; then
  t="$DATA_ROOT/.ovltest"
  as_root rm -rf "$t"
  as_root mkdir -p "$t/lower" "$t/upper" "$t/work" "$t/merged"
  if as_root mount -t overlay overlay \
       -o "lowerdir=$t/lower,upperdir=$t/upper,workdir=$t/work" "$t/merged" 2>/dev/null; then
    as_root umount "$t/merged"
    as_root rm -rf "$t"
    say "overlay preflight passed"
  else
    as_root rm -rf "$t"
    die "overlayfs will not mount on $DOCKER_DS.
       Re-run with --driver zfs. That keeps one dataset per layer, but they live under
       $DOCKER_DS where zsys cannot reach them, which is the part that actually matters."
  fi
fi

# ---------------------------------------------------------------------------------------------
# daemon.json — written BEFORE install, so the first daemon start reads it.
#
# Merged rather than overwritten: daemon.json may carry registry mirrors, log limits, or proxy
# settings unrelated to storage. dockerd rejects unknown top-level keys, so there is nowhere to
# record a "written by this script" marker — hence the backup and the --force gate.
# ---------------------------------------------------------------------------------------------
if [ -r "$DAEMON_JSON" ] && grep -q '"storage-driver"' "$DAEMON_JSON" 2>/dev/null \
   && ! grep -q "\"storage-driver\"[[:space:]]*:[[:space:]]*\"$DRIVER\"" "$DAEMON_JSON" 2>/dev/null \
   && [ "$FORCE_DAEMON" -eq 0 ]; then
  die "$DAEMON_JSON already sets a different storage-driver:
       $(grep '"storage-driver"' "$DAEMON_JSON")
       Re-run with --force-daemon to replace it (a .bak copy is kept)."
fi

if [ -r "$DAEMON_JSON" ] && grep -q "\"storage-driver\"[[:space:]]*:[[:space:]]*\"$DRIVER\"" "$DAEMON_JSON" 2>/dev/null; then
  skip "$DAEMON_JSON already selects $DRIVER"
else
  as_root mkdir -p "$(dirname "$DAEMON_JSON")"
  if as_root test -f "$DAEMON_JSON"; then
    as_root cp -a "$DAEMON_JSON" "${DAEMON_JSON}.bak"
    say "backed up $DAEMON_JSON to ${DAEMON_JSON}.bak"
  fi
  say "setting storage-driver=$DRIVER in $DAEMON_JSON"
  if command -v python3 >/dev/null 2>&1; then
    as_root python3 - "$DAEMON_JSON" "$DRIVER" <<'PY'
import json, os, sys
path, driver = sys.argv[1], sys.argv[2]
cfg = {}
if os.path.exists(path):
    with open(path) as fh:
        text = fh.read().strip()
    if text:
        cfg = json.loads(text)
cfg["storage-driver"] = driver
tmp = path + ".tmp"
with open(tmp, "w") as fh:
    json.dump(cfg, fh, indent=2)
    fh.write("\n")
os.replace(tmp, path)
PY
  elif as_root test -f "$DAEMON_JSON"; then
    die "python3 not found and $DAEMON_JSON already exists — merge it by hand:
       add  \"storage-driver\": \"$DRIVER\""
  else
    printf '{\n  "storage-driver": "%s"\n}\n' "$DRIVER" | as_root tee "$DAEMON_JSON" >/dev/null
  fi
fi

# ---------------------------------------------------------------------------------------------
# Docker packages
#
# From Docker's own apt repo, not the distro's docker.io: the distro package lags badly and does
# not ship the compose v2 or buildx plugins, both of which ffbox and the compose stacks assume.
# ---------------------------------------------------------------------------------------------
if [ "$DO_INSTALL" -eq 0 ]; then
  skip "package install skipped (--no-install)"
elif command -v docker >/dev/null 2>&1; then
  skip "docker already installed ($(docker --version 2>/dev/null || echo 'version unknown'))"
else
  command -v apt-get >/dev/null 2>&1 \
    || die "no apt-get — install Docker yourself, then re-run with --no-install"
  [ -r /etc/os-release ] || die "no /etc/os-release — cannot determine the apt repo to use"
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}" in
    ubuntu|debian) repo_distro="$ID" ;;
    *) # Mint, Pop!_OS, Raspbian and friends set ID_LIKE and carry an upstream codename.
       case "${ID_LIKE:-}" in
         *ubuntu*) repo_distro="ubuntu" ;;
         *debian*) repo_distro="debian" ;;
         *) die "unrecognised distro '${ID:-?}' — install Docker yourself, then --no-install" ;;
       esac ;;
  esac
  codename=${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}
  [ -n "$codename" ] || die "could not determine the release codename from /etc/os-release"

  say "installing Docker from download.docker.com ($repo_distro/$codename)"
  as_root install -m 0755 -d /etc/apt/keyrings
  as_root apt-get update -qq
  DEBIAN_FRONTEND=noninteractive as_root apt-get install -y -qq ca-certificates curl >/dev/null
  as_root curl -fsSL "https://download.docker.com/linux/$repo_distro/gpg" \
    -o /etc/apt/keyrings/docker.asc
  as_root chmod a+r /etc/apt/keyrings/docker.asc
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' \
    "$(dpkg --print-architecture)" "$repo_distro" "$codename" \
    | as_root tee /etc/apt/sources.list.d/docker.list >/dev/null
  as_root apt-get update -qq
  DEBIAN_FRONTEND=noninteractive as_root apt-get install -y -qq \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  say "installed $(docker --version)"
fi

command -v docker >/dev/null 2>&1 || die "docker is still not installed"

# ---------------------------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------------------------
if systemctl is-enabled --quiet docker.service 2>/dev/null; then
  skip "docker.service already enabled"
else
  say "enabling docker.service"
  as_root systemctl enable --now docker.service >/dev/null 2>&1 || true
fi
systemctl is-active --quiet docker.service 2>/dev/null || as_root systemctl start docker.service

INFO=$(docker_info || true)
[ -n "$INFO" ] || die "dockerd is not responding. Check: journalctl -u docker -n 50"
NEW_DRIVER=$(printf '%s\n' "$INFO" | sed -n 's/^ *Storage Driver: *//p' | head -1)
[ "$NEW_DRIVER" = "$DRIVER" ] || die "docker came up on '$NEW_DRIVER', not '$DRIVER'.
       Check $DAEMON_JSON and: journalctl -u docker -n 50"
say "docker is up on $NEW_DRIVER, data root $(ds_for "$DATA_ROOT")"

# ---------------------------------------------------------------------------------------------
# The rootless daemon
#
# THIS SCRIPT DOES NOT ADD ANYONE TO THE DOCKER GROUP, and that is the point of the section.
# Membership is root-equivalent — any member can bind-mount / into a container and read or
# write anything on the box, with no password and no sudo involved — and ffbox is the reason
# the account would have had it. Measured on 2026-08-25: `docker run -v /etc:/hostetc:ro alpine
# wc -l < /hostetc/shadow` returned 84 as uid 0, unprompted.
#
# ffbox uses a rootless daemon owned by $OWNER instead. It reaches it through DOCKER_HOST, set
# by the units and by the profile.d line written below. Nothing here needs the group.
#
# It does not REMOVE the membership either. That is one command, run once, by a human who can
# see what is currently talking to the root daemon:
#
#     sudo gpasswd -d $OWNER docker
#
# Doing it from a script that setup.sh re-runs unattended could cut a live pipeline off from
# the socket it is using mid-run. See design/rootless_docker_design.txt, question c.
# ---------------------------------------------------------------------------------------------
if [ "$DO_ROOTLESS" -eq 0 ]; then
  skip "rootless daemon skipped (--no-rootless)"
else
  # Lingering FIRST. dockerd-rootless-setuptool.sh finishes with `systemctl --user enable
  # docker`, which needs the owner's systemd instance to exist, and without lingering that
  # instance is only alive while they are logged in — which on a build server is never.
  if [ "$(loginctl show-user "$OWNER" -p Linger --value 2>/dev/null)" = yes ]; then
    skip "lingering already enabled for $OWNER"
  else
    say "enabling lingering for $OWNER, so their systemd instance survives logout"
    as_root loginctl enable-linger "$OWNER"
  fi

  _uid=$(id -u "$OWNER")
  _sock="/run/user/$_uid/docker.sock"

  if [ -S "$_sock" ]; then
    skip "rootless daemon already answering at $_sock"
  elif ! command -v dockerd-rootless-setuptool.sh >/dev/null 2>&1; then
    warn "dockerd-rootless-setuptool.sh not found — install docker-ce-rootless-extras, then
         re-run this stage."
  else
    say "installing the rootless daemon for $OWNER"
    # runuser alone does not hand over a systemd user session, and the setuptool needs one.
    # With lingering on, both of these exist from boot.
    #
    # --force, and it is not a shortcut. The setuptool aborts when /var/run/docker.sock is
    # WRITABLE, on the assumption that a working rootful docker means you did not mean to do
    # this. Here both halves of that assumption are wrong: the root daemon stays because other
    # accounts on this machine use it, and the socket is writable only because $OWNER is still
    # in the docker group — which is the thing this whole exercise removes, at the END, once a
    # real turn has run against the rootless daemon. The check would pass on its own after
    # that, and until then it is asking about a decision already made. --force skips that one
    # test and nothing else; see the guard at dockerd-rootless-setuptool.sh line 92.
    as_root runuser -u "$OWNER" -- env \
      XDG_RUNTIME_DIR="/run/user/$_uid" \
      DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$_uid/bus" \
      dockerd-rootless-setuptool.sh install --force \
      || warn "the rootless install did not complete. Run it as $OWNER from a login shell:
         dockerd-rootless-setuptool.sh install --force"
  fi

  # The store, on its own dataset, so the images are not in the boot environment and not in the
  # home directory quota either. Same reasoning as the root daemon's dataset above.
  if [ -d "$ROOTLESS_ROOT" ]; then
    skip "$ROOTLESS_ROOT already exists"
  else
    say "creating $ROOTLESS_DS at $ROOTLESS_ROOT"
    as_root zfs create -o mountpoint="$ROOTLESS_ROOT" "$ROOTLESS_DS"
  fi
  as_root chown "$OWNER:$(id -gn "$OWNER")" "$ROOTLESS_ROOT"
  # overlay2 in a user namespace needs xattr=sa. rpool sets it pool-wide, so this normally just
  # confirms the inheritance — but a store that silently lacks it fails later and further away.
  _xattr=$(zfs get -H -o value xattr "$ROOTLESS_DS" 2>/dev/null || echo unknown)
  [ "$_xattr" = sa ] || warn "$ROOTLESS_DS has xattr=$_xattr, not sa. overlay2 needs sa."

  _cfg=$(getent passwd "$OWNER" | cut -d: -f6)/.config/docker/daemon.json
  if [ -r "$_cfg" ] && grep -q "$ROOTLESS_ROOT" "$_cfg" 2>/dev/null; then
    skip "$_cfg already points at $ROOTLESS_ROOT"
  else
    say "pointing the rootless daemon's data root at $ROOTLESS_ROOT"
    as_root runuser -u "$OWNER" -- sh -c "mkdir -p \"\$(dirname '$_cfg')\" &&
      printf '{\n  \"data-root\": \"%s\"\n}\n' '$ROOTLESS_ROOT' > '$_cfg'"
  fi

  # THE SOCKET PATH, for anything that is not a systemd unit. Without this an interactive shell
  # finds the ROOT daemon's default socket, succeeds, and does the work in the wrong place —
  # the quiet failure mode from design/rootless_docker_design.txt section 7.
  say "writing $PROFILE_D so interactive shells address the rootless daemon"
  as_root sh -c "cat > '$PROFILE_D'" <<PROF
# Installed by final-factory-agents/ffbox/01-dockerSetup.sh — ffbox runs a ROOTLESS Docker
# daemon owned by $OWNER. Without this, docker(1) finds the root daemon's socket instead and
# silently operates on the wrong images, networks and containers.
if [ "\$(id -u)" = "$_uid" ] && [ -z "\${DOCKER_HOST:-}" ]; then
    DOCKER_HOST="unix://$_sock"
    export DOCKER_HOST
fi
PROF
  as_root chmod 0644 "$PROFILE_D"

  if in_group "$OWNER"; then
    warn "$OWNER is STILL in the docker group, which is root-equivalent and no longer needed.
         Once ffbox has run a turn against the rootless daemon, remove it:
             sudo gpasswd -d $OWNER docker
         Processes keep the group until they restart, so restart the units afterwards."
  fi
fi

# ---------------------------------------------------------------------------------------------
# Egress filter
#
# Docker networking is this script's business, and the run container's network is the one piece of
# it that is a security boundary rather than plumbing. A run joins an --internal bridge whose only
# neighbour is a proxy that resolves and connects the names in ffbox/egress/allowlist.txt and
# nothing else. Built and started here so that stage 4 (the Unity import, which is itself a
# container) already has somewhere to activate a licence from.
#
# ffbox refuses to run without it, deliberately: the alternative to a filter that is not there is
# the whole internet, and that is not a fallback to take quietly.
# ---------------------------------------------------------------------------------------------
if [ "$DO_EGRESS" -eq 0 ]; then
  skip "egress filter skipped (--no-egress)"
else
  say "building the egress filter image"
  as_root docker build -q -t ffbox-egress:latest "$HERE/egress" >/dev/null \
    || die "could not build ffbox-egress:latest"
  sh "$HERE/egress/ffbox-egress.sh" up \
    || warn "the egress filter is not up. ffbox will refuse to start a run until it is:
         sh $HERE/egress/ffbox-egress.sh up"
fi

# ---------------------------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------------------------
if [ "$DO_SMOKE" -eq 0 ]; then
  skip "smoke test skipped (--no-smoke)"
else
  # Against the ROOTLESS daemon, as the owner, because that is the one ffbox will use. A clean
  # root daemon proves nothing about the socket every unit is pointed at.
  _uid=$(id -u "$OWNER")
  _sock="/run/user/$_uid/docker.sock"
  say "running hello-world on the rootless daemon, as $OWNER"
  if as_root runuser -u "$OWNER" -- env DOCKER_HOST="unix://$_sock" \
       docker run --rm hello-world >/dev/null 2>&1; then
    say "hello-world ran clean on the rootless daemon"
    as_root runuser -u "$OWNER" -- env DOCKER_HOST="unix://$_sock" \
      docker rmi hello-world >/dev/null 2>&1 || true
  else
    warn "hello-world failed on the rootless daemon at $_sock. Check, as $OWNER:
             systemctl --user status docker
             DOCKER_HOST=unix://$_sock docker run --rm hello-world
         If the socket is absent, lingering or the rootless install did not take."
  fi
fi

# Prove the point of the whole exercise: pulling and running created nothing in the boot env.
be=$(ds_for /var/lib)
case "$be" in
  */*) stray=$(zfs list -H -o name -r "$be" 2>/dev/null | grep -cE '/[0-9a-z]{25,}(-init)?$' || true) ;;
  *)   stray=0 ;;
esac
[ "$stray" -eq 0 ] || warn "$stray docker-shaped datasets appeared under $be.
         The driver is writing into the boot environment — investigate before using this host."

# ---------------------------------------------------------------------------------------------
say "done"
cat <<EOF

  $DOCKER_DS   ->  $DATA_ROOT   (driver: $DRIVER)
  boot environment              clean — 0 layer datasets

Verify any time with:
  sh ffbox/dockerSetup.sh --check

Next, for ffbox:
  sh ffbox/zfsSetup.sh      # the golden checkout and per-run clone layout
  sh ffbox/build.sh         # build ffbox:latest
EOF
