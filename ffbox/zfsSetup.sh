#!/bin/sh
# zfsSetup.sh — prepare a machine's ZFS layout for ffbox (see README.md, next to this file).
#
# ffbox runs each one-shot Claude prompt against its own throwaway copy of the Final Factory
# checkout. Copying ~11GB per run is a non-starter, so instead the checkout lives in a dedicated
# ZFS dataset ("golden") and every run gets a `zfs clone` of it: instant, ~0 bytes, and it
# inherits golden's warm Unity Library/ so runs skip the 30-60 minute cold import.
#
# This script builds that layout. Designed for a brand-new machine with an empty /opt, and safe
# to re-run: each step is skipped if it is already in place.
#
#   <pool>/ff              mountpoint=none      container for everything ffbox owns
#   <pool>/ff/golden       /opt/FinalFactory    the golden checkout
#   <pool>/ff/run-<id>     /opt/ffruns/run-<id> per-run clones (created by ffbox, not here)
#
# WHY <pool>/ff AND NOT SOMEWHERE UNDER <pool>/ROOT
# Ubuntu's zsys auto-snapshots the root datasets on every apt transaction. Putting an 11GB+ Unity
# project there means every one of those snapshots pins a copy of it. On the first machine this
# was set up on, the root dataset had already accumulated 7,059 snapshots holding ~1TB. <pool>/ff
# sits outside both ROOT and USERDATA, so zsys leaves it alone.
#
# Requires root for the dataset work; it re-invokes itself through sudo where needed, so run it
# as the normal user who will own the checkout.

set -eu

REPO_URL="https://github.com/Final-Factory/FinalFactory.git"
GOLDEN_MNT="/opt/FinalFactory"
RUNS_MNT="/opt/ffruns"
SUDOERS_FILE="/etc/sudoers.d/ffbox"
POOL=""
OWNER=""
DO_CLONE=1
DO_SUDOERS=1
FORCE_SUDOERS=0
CHECK_ONLY=0
MIGRATE_FROM=""

usage() {
  cat <<EOF
Usage: sh ffbox/zfsSetup.sh [options]

Prepares this machine's ZFS layout for ffbox: a dedicated dataset for the Final Factory
checkout, a mountpoint for per-run clones, and an optional sudoers rule so ffbox can
snapshot/clone/destroy unattended. Idempotent — re-run any time.

Options (alphabetical):
  --check           Report what is and is not in place; change nothing.
  --force-sudoers   Overwrite ${SUDOERS_FILE} even if it was not written by this
                    script. Without it, a hand-written file is left untouched.
  --golden PATH     Mountpoint for the golden checkout (default: ${GOLDEN_MNT}).
  --help            Show this message.
  --migrate PATH    Move an existing checkout at PATH into the new dataset instead of
                    cloning. PATH is left in place afterwards for you to verify and
                    delete yourself — this script never removes a checkout.
  --no-clone        Create the datasets but leave golden empty; populate it yourself.
  --no-sudoers      Skip the sudoers rule. ffbox then prompts for a password per run.
  --owner USER      User who should own the checkout (default: the invoking user).
  --pool NAME       ZFS pool to build in (default: the pool holding /).
  --repo URL        Repository to clone (default: ${REPO_URL}).
  --runs PATH       Mountpoint for per-run clones (default: ${RUNS_MNT}).

After this, see ffbox/README.md: build the image, then create ~/.config/ffbox/secrets.env.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --check)      CHECK_ONLY=1; shift ;;
    --force-sudoers) FORCE_SUDOERS=1; shift ;;
    --golden)     GOLDEN_MNT=${2:?--golden needs a path}; shift 2 ;;
    --help|-h)    usage; exit 0 ;;
    --migrate)    MIGRATE_FROM=${2:?--migrate needs a path}; DO_CLONE=0; shift 2 ;;
    --no-clone)   DO_CLONE=0; shift ;;
    --no-sudoers) DO_SUDOERS=0; shift ;;
    --owner)      OWNER=${2:?--owner needs a user}; shift 2 ;;
    --pool)       POOL=${2:?--pool needs a name}; shift 2 ;;
    --repo)       REPO_URL=${2:?--repo needs a URL}; shift 2 ;;
    --runs)       RUNS_MNT=${2:?--runs needs a path}; shift 2 ;;
    *)            echo "zfsSetup.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
done

say()  { printf '==> %s\n' "$*"; }
skip() { printf '    %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die()  { printf 'zfsSetup.sh: %s\n' "$*" >&2; exit 1; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

# Run as the checkout's owner. Needed for the clone: a root-owned .git in golden would be
# inherited by every run clone, and the container maps to the owner's UID, not root's.
as_owner() {
  if [ "$(id -un)" = "$OWNER" ]; then "$@"; else as_root sudo -u "$OWNER" "$@"; fi
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

# SUDO_USER is only meaningful when we are actually root — it lingers in the environment of any
# shell that was itself started under sudo, and trusting it there would silently pick the wrong
# owner (and write a sudoers rule for a user who never runs ffbox).
if [ -z "$OWNER" ]; then
  if [ "$(id -u)" -eq 0 ]; then OWNER=${SUDO_USER:-root}; else OWNER=$(id -un); fi
fi
id "$OWNER" >/dev/null 2>&1 || die "no such user: $OWNER"
OWNER_GROUP=$(id -gn "$OWNER")

FF_DS="${POOL}/ff"
GOLDEN_DS="${FF_DS}/golden"

# ---------------------------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------------------------
have_ds() { zfs list -H -o name "$1" >/dev/null 2>&1; }

if [ "$CHECK_ONLY" -eq 1 ]; then
  printf 'pool:        %s\n' "$POOL"
  printf 'owner:       %s:%s\n' "$OWNER" "$OWNER_GROUP"
  printf '%-22s %s\n' "$FF_DS"     "$(have_ds "$FF_DS"     && echo present || echo MISSING)"
  printf '%-22s %s\n' "$GOLDEN_DS" "$(have_ds "$GOLDEN_DS" && echo "present -> $(zfs get -H -o value mountpoint "$GOLDEN_DS")" || echo MISSING)"
  printf '%-22s %s\n' "$RUNS_MNT"  "$([ -d "$RUNS_MNT" ] && echo present || echo MISSING)"
  printf '%-22s %s\n' "checkout"   "$(git -C "$GOLDEN_MNT" rev-parse --short HEAD 2>/dev/null || echo "not a git repo")"
  # /etc/sudoers.d is 0750 root:root on a stock Debian/Ubuntu, so an unprivileged `test -f`
  # cannot tell "absent" from "unreadable" and would report a present rule as MISSING. Retry
  # through a non-interactive sudo, and say "unknown" rather than guess if that is refused too.
  if [ -f "$SUDOERS_FILE" ] || sudo -n test -f "$SUDOERS_FILE" 2>/dev/null; then
    sudoers_state="$SUDOERS_FILE"
  elif [ -r /etc/sudoers.d ]; then
    sudoers_state="MISSING"
  else
    sudoers_state="unknown (need root to read /etc/sudoers.d)"
  fi
  printf '%-22s %s\n' "sudoers" "$sudoers_state"
  exit 0
fi

say "pool ${POOL}, owner ${OWNER}:${OWNER_GROUP}"

# ---------------------------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------------------------
if have_ds "$FF_DS"; then
  skip "$FF_DS already exists"
else
  # mountpoint=none is load-bearing: pool roots normally carry mountpoint=/, so without this the
  # dataset would try to mount itself at /ff.
  say "creating $FF_DS (mountpoint=none)"
  as_root zfs create -o mountpoint=none "$FF_DS"
fi

if have_ds "$GOLDEN_DS"; then
  skip "$GOLDEN_DS already exists"
else
  # A pre-existing non-empty directory at the mountpoint would be shadowed by the mount and look
  # like data loss. Refuse rather than hide it; --migrate is the supported way to move it in.
  if [ -d "$GOLDEN_MNT" ] && [ -n "$(ls -A "$GOLDEN_MNT" 2>/dev/null)" ] && [ -z "$MIGRATE_FROM" ]; then
    die "$GOLDEN_MNT exists and is not empty. Move it aside, or re-run with:
       sh ffbox/zfsSetup.sh --migrate $GOLDEN_MNT"
  fi
  say "creating $GOLDEN_DS -> $GOLDEN_MNT"
  as_root zfs create -o mountpoint="$GOLDEN_MNT" "$GOLDEN_DS"
  as_root chown "$OWNER:$OWNER_GROUP" "$GOLDEN_MNT"
fi

if [ -d "$RUNS_MNT" ]; then
  skip "$RUNS_MNT already exists"
else
  # Plain directory, not a dataset: ffbox's per-run clones mount themselves underneath it.
  say "creating $RUNS_MNT"
  as_root mkdir -p "$RUNS_MNT"
  as_root chown "$OWNER:$OWNER_GROUP" "$RUNS_MNT"
fi

# ---------------------------------------------------------------------------------------------
# Populate golden
# ---------------------------------------------------------------------------------------------
if [ -n "$(ls -A "$GOLDEN_MNT" 2>/dev/null)" ]; then
  skip "$GOLDEN_MNT already populated ($(git -C "$GOLDEN_MNT" rev-parse --short HEAD 2>/dev/null || echo 'not a git repo'))"
elif [ -n "$MIGRATE_FROM" ]; then
  [ -d "$MIGRATE_FROM" ] || die "--migrate source does not exist: $MIGRATE_FROM"
  say "copying $MIGRATE_FROM into $GOLDEN_MNT (this takes a while)"
  as_root rsync -aHAX --info=progress2 "${MIGRATE_FROM%/}/" "$GOLDEN_MNT/"
  as_root chown -R "$OWNER:$OWNER_GROUP" "$GOLDEN_MNT"
  warn "the original is still at $MIGRATE_FROM — verify the copy, then delete it yourself.
         Note that deleting it may free no space: existing zsys snapshots of the root dataset
         still reference those blocks."
elif [ "$DO_CLONE" -eq 1 ]; then
  command -v git >/dev/null 2>&1 || die "git not found"
  command -v git-lfs >/dev/null 2>&1 || warn "git-lfs not found — LFS payloads will stay as pointer files, and Unity will silently skip the affected plugins"
  say "cloning $REPO_URL (large repo with LFS; expect this to be slow)"
  as_owner git clone "$REPO_URL" "$GOLDEN_MNT"
else
  skip "golden left empty (--no-clone)"
fi

# ---------------------------------------------------------------------------------------------
# Sudoers
#
# ZFS mounting needs root on Linux no matter what, so ffbox cannot avoid elevation. Scope the
# grant as tightly as the operations allow: destroy is limited to run-* clones and ffbox-* golden
# snapshots, so a bug in ffbox — or anything else invoking this rule — cannot destroy golden.
# ---------------------------------------------------------------------------------------------
SUDOERS_MARKER="# Installed by final-factory-agents/ffbox/zfsSetup.sh"
# Ownership is detected on this stable substring rather than the full marker: the script has
# moved paths once already, and a rule written by an older copy is still ours to update.
SUDOERS_OWNED_BY="zfsSetup.sh"

sudoers_content() {
  ZFS_BIN=$(command -v zfs)
  cat <<EOF
${SUDOERS_MARKER} — lets ffbox manage its per-run clones.
# Regenerate by re-running that script; hand-edits are detected and left alone.
# Deliberately narrow: destroy can only ever name a run-* clone or an ffbox-* snapshot.
Cmnd_Alias FFBOX_ZFS = ${ZFS_BIN} snapshot ${GOLDEN_DS}@ffbox-*, \\
                       ${ZFS_BIN} clone -o * ${GOLDEN_DS}@ffbox-* ${FF_DS}/run-*, \\
                       ${ZFS_BIN} destroy ${FF_DS}/run-*, \\
                       ${ZFS_BIN} destroy ${GOLDEN_DS}@ffbox-*
${OWNER} ALL=(root) NOPASSWD: FFBOX_ZFS
EOF
}

# Never install an unvalidated sudoers file: a syntax error in /etc/sudoers.d can lock the
# machine out of sudo entirely. visudo -c parses a candidate without touching the real config.
install_sudoers() {   # $1 = candidate file, $2 = verb for the log line
  if ! as_root visudo -c -q -f "$1" >/dev/null 2>&1; then
    as_root visudo -c -f "$1" || true
    rm -f "$1"
    die "generated sudoers rule failed validation and was NOT installed"
  fi
  say "$2 $SUDOERS_FILE"
  as_root install -m 0440 -o root -g root "$1" "$SUDOERS_FILE"
  rm -f "$1"
}

# Print the installed rule, or return 1 if it genuinely cannot be read.
#
# /etc/sudoers.d is root-only, so this needs privilege — and privilege is not guaranteed: a
# correctly-hardened machine has no passwordless sudo, and a non-interactive run has no terminal
# to prompt at. Try unprivileged, then non-interactive sudo, then an interactive prompt only if
# there is a terminal to prompt at. Never let "could not check" masquerade as an answer.
read_sudoers() {
  if [ -r "$SUDOERS_FILE" ]; then
    cat "$SUDOERS_FILE"
  elif sudo -n cat "$SUDOERS_FILE" 2>/dev/null; then
    :
  elif [ -t 0 ] && as_root cat "$SUDOERS_FILE" 2>/dev/null; then
    :
  else
    return 1
  fi
}

if [ "$DO_SUDOERS" -eq 0 ]; then
  skip "sudoers rule skipped (--no-sudoers); ffbox will prompt for a password per run"
else
  tmp=$(mktemp)
  sudoers_content > "$tmp"
  cur=$(mktemp)

  if read_sudoers > "$cur" 2>/dev/null; then
    if cmp -s "$tmp" "$cur"; then
      skip "$SUDOERS_FILE already up to date"
      rm -f "$tmp"
    elif [ "$FORCE_SUDOERS" -eq 0 ] && ! grep -qF "$SUDOERS_OWNED_BY" "$cur"; then
      # Someone wrote this by hand. Silently overwriting a sudoers file is not a thing to do.
      rm -f "$tmp"
      warn "$SUDOERS_FILE exists but was not written by this script — leaving it alone.
         Inspect it with:  sudo visudo -f $SUDOERS_FILE
         Overwrite it with: sh ffbox/zfsSetup.sh --force-sudoers"
    else
      # Ours, and stale — the pool, owner, or rule shape changed since it was written.
      install_sudoers "$tmp" "updating"
    fi
  elif [ -e "$SUDOERS_FILE" ] || sudo -n test -e "$SUDOERS_FILE" 2>/dev/null; then
    # It exists but we could not read it. Say exactly that, rather than guessing it is foreign.
    rm -f "$tmp"
    warn "$SUDOERS_FILE exists but could not be read to check whether it is current.
         Re-run with root available (a terminal for the sudo prompt, or as root) to update it."
  elif [ -r /etc/sudoers.d ]; then
    install_sudoers "$tmp" "installing"
  else
    rm -f "$tmp"
    warn "cannot determine whether $SUDOERS_FILE exists (need root to read /etc/sudoers.d).
         Re-run with root available."
  fi
  rm -f "$cur"
fi

# ---------------------------------------------------------------------------------------------
say "done"
cat <<EOF

Layout:
  ${FF_DS}          mountpoint=none
  ${GOLDEN_DS}      ${GOLDEN_MNT}
  per-run clones    ${RUNS_MNT}/run-<id>

Next:
  1. sh ffbox/build.sh
  2. install -m 600 ffbox/secrets.env.example ~/.config/ffbox/secrets.env
     claude setup-token        # paste into that file, along with the Unity credentials
  3. ffbox/ffbox --no-unity 'summarise how the save migration system works'

Then warm golden's Library/ once, so every future clone inherits a warm Unity import cache.
EOF
