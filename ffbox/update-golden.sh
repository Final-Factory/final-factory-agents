#!/bin/sh
#
# NOTHING IN THE PIPELINE CALLS THIS ANY MORE. ffbox used to run it before snapshotting golden;
# runs now restore from CI's workspace cache and fetch from the local git mirror, so golden is not
# on the path at all. /opt/FinalFactory stays on the box as a checkout to edit Final Factory by
# hand, and this remains the right way to bring THAT up to date -- it verifies LFS pointers, which
# a bare `git pull` does not.
#
# update-golden.sh — bring the golden checkout to origin, exactly one updater at a time.
#
#   sh update-golden.sh              take the golden lock, update golden, release
#   sh update-golden.sh --locked     the CALLER already holds the lock (this is how ffbox and
#                                    04-warmLibrary.sh use it)
#   sh update-golden.sh --verify     scan every tracked file for LFS pointers even when HEAD
#                                    did not move
#   sh update-golden.sh --quiet      only complain
#
# WHY THIS IS ITS OWN FILE. Two callers need the identical update and neither can own it:
# `ffbox` has to run it INSIDE the lock it holds across `zfs snapshot`, and 04-warmLibrary.sh
# has to run it before a Unity import that then writes Library/ for an hour. A second
# implementation of "fetch and fast-forward golden" is a second place for the LFS trap below to
# be forgotten, and that trap costs a confusing CS0246 inside a container to rediscover.
#
# THE LOCK BLOCKS, WITH NO TIMEOUT, ON PURPOSE. A timeout would make mutual exclusion contingent
# on a number somebody guessed: the moment a pull runs longer than the guess, two writers touch
# golden, or a run snapshots it mid-write. Waiting is the correct behaviour — a run that arrives
# during an update WANTS the result of that update. `flock` holds the lock on an open file
# description, so if the holder dies for any reason, including SIGKILL, the kernel releases it.
# There is no stale-lock case to recover from and no PID file to reap.
#
# Liveness is a separate concern from mutual exclusion, and it gets a separate mechanism: the
# fetch below carries git's low-speed abort so a dead TCP connection cannot wedge the holder
# forever. That decides when to give up on a network, never who wins the lock.
#
# WHAT CALLERS ARE PROMISED. On exit 0, golden is clean, at origin/<its branch> as of a fetch
# that happened during this call, every OTHER branch origin has is present as a remote-tracking
# ref from that same fetch, the branches in FFBOX_BASE_REFS exist and have their LFS content on
# disk, and any file this pull touched has real content rather than an LFS pointer. On any other
# exit, golden was NOT left half-updated by us — every failure mode here either changes nothing
# or fails a fast-forward that git itself performs atomically.
#
# POSIX sh, like its siblings.
set -eu

GOLDEN_MNT=${FFBOX_GOLDEN_MNT:-/opt/FinalFactory}
CONFIG_DIR=${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}
LOCK=${FFBOX_GOLDEN_LOCK:-$CONFIG_DIR/golden.lock}

# The branches a RUN may base its work on, which is not the same set as the branch golden itself
# sits on. A run picks between them — a fix for the released build goes on master, everything
# else on develop — inside a container with no network, so whatever it checks out has to already
# be here.
#
# The REFS are not this list's job any more: the fetch below takes every branch origin has, the
# way a bare `git fetch` does. What this list still decides is which of them get their LFS
# content pre-materialized, and which must exist for the machine to be considered working at
# all. Both are things you cannot do for "every branch" without paying for every branch.
BASE_REFS=${FFBOX_BASE_REFS:-develop master}

LOCKED=0
VERIFY=0
QUIET=0

usage() {
    sed -n '3,9p' "$0" | sed 's/^# \{0,1\}//'
    cat <<EOF

Options:
  --locked   The caller already holds $LOCK. Do not acquire it again.
  --verify   Scan all tracked files for unmaterialized LFS pointers even when nothing changed.
  --quiet    Print only warnings and errors.
  --help     Show this message.

Environment: FFBOX_GOLDEN_MNT (default $GOLDEN_MNT), FFBOX_GOLDEN_LOCK, FFBOX_CONFIG_DIR,
FFBOX_BASE_REFS (default "$BASE_REFS") — the branches a run may base its work on. Every branch
on origin is fetched either way; these are the ones that must exist and that get their LFS
content pre-materialized, so a container with no network can check them out.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --locked)  LOCKED=1; shift ;;
        --verify)  VERIFY=1; shift ;;
        --quiet)   QUIET=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *)         echo "update-golden.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
    esac
done

log()  { [ "$QUIET" = 1 ] || printf '[golden] %s\n' "$*"; }
warn() { printf '[golden] WARNING: %s\n' "$*" >&2; }
die()  { printf 'update-golden.sh: %s\n' "$*" >&2; exit 1; }

[ -d "$GOLDEN_MNT/.git" ] || die "$GOLDEN_MNT is not a git checkout"
command -v git >/dev/null 2>&1 || die "git not found"

git_() { git -C "$GOLDEN_MNT" "$@"; }

# ------------------------------------------------------------------------------------------
# the lock
# ------------------------------------------------------------------------------------------
# Fd 9 rather than `flock CMD`: the fd stays open for the rest of this script, so the lock is
# held for the whole update and released when this process exits, however it exits. `--locked`
# callers hold their own fd and pass the lock down to us by inheritance.
#
# Children inherit fd 9, and therefore the lock, and that is deliberate. If this shell is killed
# while `git fetch` is still running, git is still writing to golden — a lock that ended with the
# shell would let a run snapshot the tree git is in the middle of. The lock ends when the last
# process that could still be writing has gone, which is exactly the property that matters.
if [ "$LOCKED" = 0 ]; then
    command -v flock >/dev/null 2>&1 || die "flock not found; it is not optional here"
    mkdir -p "$(dirname "$LOCK")" || die "cannot create $(dirname "$LOCK")"
    exec 9>"$LOCK" || die "cannot open $LOCK for writing"
    # No -w, no -n. See the header.
    flock 9 || die "could not lock $LOCK"
fi

# ------------------------------------------------------------------------------------------
# golden must be pristine
# ------------------------------------------------------------------------------------------
# REFUSED, not warned about and not stashed. Every run is a clone of this directory, so a stray
# edit here is not one contaminated run, it is every run launched until somebody notices — and
# with eight of them in flight nobody notices quickly. It is also a one-line fix for whoever
# left the file there, which is a much better outcome than a week of subtly wrong bases.
if [ -n "$(git_ status --porcelain)" ]; then
    git_ status --short | head -20 >&2
    die "$GOLDEN_MNT has local changes; golden must stay clean. Resolve them, then re-run."
fi

BRANCH=$(git_ rev-parse --abbrev-ref HEAD)
[ "$BRANCH" != HEAD ] || die "$GOLDEN_MNT is in detached HEAD; check out a branch first"
git_ rev-parse --verify --quiet "refs/remotes/origin/$BRANCH" >/dev/null 2>&1 \
    || die "golden is on '$BRANCH', which has no origin/$BRANCH to follow"

BEFORE=$(git_ rev-parse HEAD)

# Where each base ref stood before the fetch, so the LFS pre-fetch below can be skipped when it
# did not move. Encoded as "name=sha" words because POSIX sh has no arrays and this list has two
# entries; "none" for a ref that does not exist yet, which reads as "moved" and then fails the
# existence check on the next pass.
base_before=
for base_ref in $BASE_REFS; do
    base_before="$base_before $base_ref=$(git_ rev-parse --verify --quiet \
        "refs/remotes/origin/$base_ref" || echo none)"
done

# ------------------------------------------------------------------------------------------
# fetch, then fast-forward
# ------------------------------------------------------------------------------------------
# EVERY branch, exactly as a bare `git fetch origin` does: the remote's own refspec into
# refs/remotes/origin/*, plus --prune so a branch deleted on origin disappears here too. It used
# to fetch the single branch golden sits on, which updated that branch's remote-tracking ref and
# no other — so origin/develop, the ref every Discord run checks out, was only as fresh as the
# last time somebody fetched it by hand. Naming the refs a run might want was the first fix and the
# wrong shape: the set is not knowable here, a run can legitimately want any of them, and git
# already has a name for "all of them".
#
# Nothing is checked out and no local branch moves. The one fast-forward is golden's own, below.
#
# http.lowSpeedLimit/Time is a LIVENESS bound, not a correctness one: it aborts a transfer that
# has stalled below 1KB/s for a minute, so a half-dead connection cannot hold the lock for the
# rest of the day. Nothing about who-updates-when depends on it.
log "fetching $(git_ config --get remote.origin.url)"
git_ -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=60 fetch --prune --quiet origin \
    || die "fetch of origin failed"

# From the remote-tracking ref rather than FETCH_HEAD: with no refspec on the command line,
# FETCH_HEAD carries every branch that was fetched, and the first line of it is not this one.
TARGET=$(git_ rev-parse --verify --quiet "refs/remotes/origin/$BRANCH") \
    || die "origin/$BRANCH is gone from origin; $GOLDEN_MNT needs a human"

# --ff-only: a merge commit in golden would be nobody's intent and would diverge it from the
# remote permanently. When this fails the branch needs a human, and saying so beats inventing a
# merge nobody reviewed.
git_ merge --ff-only --quiet "$TARGET" \
    || die "origin/$BRANCH does not fast-forward onto golden's HEAD. Fix $GOLDEN_MNT by hand."

AFTER=$(git_ rev-parse HEAD)

# ------------------------------------------------------------------------------------------
# the branches a run may base its work on
# ------------------------------------------------------------------------------------------
# The fetch above already brought every ref. What is left is the half that is easy to forget and
# expensive to rediscover: `git lfs pull` below materializes content for the CHECKED-OUT tree
# only, so a run that checks out one of these instead would find a pointer wherever the two
# branches disagree about a binary — and it has no network to fix that with. Unity then skips
# the DLL as a managed plugin and fails with a CS0246 that names nothing useful. `git lfs fetch`
# puts the objects in .git/lfs/objects, which the clone inherits, so the container's checkout
# smudges them from disk.
#
# Only these refs, not every branch that was just fetched: the harvest publishes work against
# one of them or nothing, and pre-materializing every feature branch's binaries would cost far
# more than it could ever save.
#
# A base ref that does not exist is fatal rather than skipped. The set is small and declared,
# and a run silently basing itself on a ref that is not there is the failure this file exists to
# prevent.
for base_ref in $BASE_REFS; do
    now=$(git_ rev-parse --verify --quiet "refs/remotes/origin/$base_ref" || echo none)
    [ "$now" != none ] \
        || die "origin/$base_ref does not exist, so runs cannot base on it. Set FFBOX_BASE_REFS if this repository has no such branch."
    was=
    for pair in $base_before; do
        case "$pair" in "$base_ref="*) was=${pair#*=} ;; esac
    done
    [ "$was" != "$now" ] || [ "$VERIFY" = 1 ] || continue
    if command -v git-lfs >/dev/null 2>&1; then
        log "materializing LFS content for origin/$base_ref, which runs may base on"
        git_ lfs fetch origin "refs/remotes/origin/$base_ref" >/dev/null 2>&1 \
            || warn "could not pre-fetch LFS content for origin/$base_ref; a run that checks it"\
                    "out may find pointers where it differs from $BRANCH"
    fi
done

# ------------------------------------------------------------------------------------------
# LFS, and the pointer trap
# ------------------------------------------------------------------------------------------
# actions/checkout's lfs handling has the same trap called out in main.yml: a file left as a
# pointer by an earlier failed smudge is considered UNMODIFIED by git, so nothing ever rewrites
# it. Unity then skips those DLLs as managed plugins and compilation fails with a confusing
# CS0246. `git lfs pull` re-smudges unconditionally.
#
# Both this and the scan are skipped when HEAD did not move, and that is a DATA-dependent skip,
# not a clock-dependent one: if no tracked file changed, this pull cannot have left a new
# pointer behind. It does mean a pointer stranded by some earlier interrupted smudge is not
# re-checked on every launch — `--verify` forces the scan, and 04-warmLibrary.sh passes it, so
# the full check still runs every time golden is warmed.
if [ "$BEFORE" = "$AFTER" ]; then
    log "already at $(printf %.12s "$AFTER") on $BRANCH — nothing to take"
else
    log "$(printf %.12s "$BEFORE") -> $(printf %.12s "$AFTER") ($(git_ rev-list --count "$BEFORE..$AFTER") commit(s))"
fi

if [ "$BEFORE" != "$AFTER" ] || [ "$VERIFY" = 1 ]; then
    if command -v git-lfs >/dev/null 2>&1; then
        log "materializing LFS content"
        git_ lfs pull || die "git lfs pull failed"

        # Scan every TRACKED file, not `git lfs ls-files`. That command resolves through
        # .gitattributes, and attribute patterns are matched CASE-SENSITIVELY on Linux while
        # Windows (core.ignoreCase=true on a case-insensitive filesystem) matches them either
        # way. The repo's patterns are lowercase — `*.png` — so on this machine the 236 `.PNG`
        # files, plus .JPG/.TGA/.PSD/.OBJ, are not LFS files at all: `git lfs ls-files` cannot
        # see them, and this check was blind exactly where the problem lives. `*.FBX` already
        # carries an uppercase twin in .gitattributes, which is why FBX is the one type that
        # behaves. Reading the first bytes of each file needs no attributes and cannot be fooled.
        pointers=$(cd "$GOLDEN_MNT" && git ls-files -z | python3 -c "
import sys
for path in sys.stdin.buffer.read().split(b'\0'):
    if not path:
        continue
    try:
        with open(path, 'rb') as fh:
            if fh.read(42).startswith(b'version https://git-lfs'):
                sys.stdout.write(path.decode('utf-8', 'replace') + '\n')
    except OSError:
        pass
" || true)
        if [ -n "$pointers" ]; then
            printf '%s\n' "$pointers" | head -20 >&2
            die "LFS content did not materialize; the files above are still pointers"
        fi
    else
        warn "git-lfs is not installed — LFS files may still be pointers"
    fi
fi

log "golden at $(git_ rev-parse --short HEAD) on $BRANCH"
