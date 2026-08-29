#!/bin/sh
#
# warmLibrary.sh — bring the golden checkout up to date, then give it a warm Library/ by
# extracting the one CI already built.
#
# Every ffbox run is a ZFS clone of golden, so a warm Library/ here is a warm Library/ for every
# run, for free. What changed on 2026-08-29 is where it comes from: this script used to build it
# by opening the project in Unity, which meant running arbitrary repository code on the host
# account every five minutes. Now CI builds it in a hardened container and this copies the result.
# See design/ffcache_design.txt section 12, and the long comment above the extract below.
#
# No Unity, no container, no licence, and no secrets: this script reads a tar and moves a
# directory.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

GOLDEN_MNT=${FFBOX_GOLDEN_MNT:-/opt/FinalFactory}
CONFIG_DIR=${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}
GOLDEN_LOCK=${FFBOX_GOLDEN_LOCK:-$CONFIG_DIR/golden.lock}
DRAIN_SWITCH=$CONFIG_DIR/draining
FFWATCH=$HERE/ffwatch.py
# also the run that proves the allowlist covers UPM. Putting it somewhere laxer would hide that.

FORCE=0
SKIP_UPDATE=0

usage() {
    cat <<EOF
Usage: sh warmLibrary.sh [options]

Updates ${GOLDEN_MNT} from its remote, then extracts CI's Library/ so golden carries a
warm Library/. Slow on a cold project (30-60 minutes); fast and harmless once warm.

Options:
  --force         Extract even when golden's Library/ is newer than the cache entry.
  --skip-update   Do not touch git; warm whatever is currently checked out.
  --help          Show this message.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --force)       FORCE=1; shift ;;
        --skip-update) SKIP_UPDATE=1; shift ;;
        --help|-h)     usage; exit 0 ;;
        *)             echo "warmLibrary.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
    esac
done

log()  { printf '==> %s\n' "$*"; }
die()  { printf 'warmLibrary.sh: %s\n' "$*" >&2; exit 1; }

command -v tar >/dev/null || die "tar not found"
[ -d "$GOLDEN_MNT/.git" ] || die "$GOLDEN_MNT is not a git checkout"

# Unity takes an exclusive lock on a project directory, so two warm-ups on golden cannot overlap.
# No container to collide with any more. The golden lock below is the only mutual exclusion this
# needs, and it is the same lock a run takes before snapshotting.

# ------------------------------------------------------------------------------------------------
# Exclude everything else that touches golden
# ------------------------------------------------------------------------------------------------
# TWO mechanisms, because they answer two different questions.
#
# THE LOCK IS THE CORRECTNESS ONE, and it is held for the WHOLE run of this script rather than
# just its git phase. The import writes Library/ for up to an hour, and a run that snapshots
# golden in the middle of that clones a half-built import cache along with an inherited
# Library/UnityLockfile. That is worse than a torn worktree: Unity may trust a corrupt artifact
# database rather than reject it.
#
# THE DRAIN IS THE COURTESY ONE. It exists only so that the normal path does not spend an hour
# blocked on the lock: with the flag set, ffwatch stops launching and turns queue instead. It is
# deliberately NOT `--wait` — runs already in flight cannot hurt this import, because each one
# took its snapshot before it started and works from a clone that is now independent of golden.
# Nothing here waits on anything with a clock.
#
# The lock is still needed underneath it, because drain cannot reach `ffbox --direct`, which
# never consults ffwatch. That caller blocks on the lock, which is the correct outcome: it wants
# a consistent golden, and one exists an hour from now.
command -v flock >/dev/null 2>&1 || die "flock not found; it is not optional here"
mkdir -p "$CONFIG_DIR"
exec 9>"$GOLDEN_LOCK" || die "cannot open $GOLDEN_LOCK for writing"
log "waiting for the golden lock"
flock 9 || die "could not lock $GOLDEN_LOCK"

# Only ours to lift if it was not already set: an updater or an operator may own the drain, and
# clearing somebody else's is how a box quietly starts launching again mid-deploy.
DRAINED=0
lift_drain() {
    [ "$DRAINED" = 1 ] || return 0
    DRAINED=0
    rm -f "$DRAIN_SWITCH" 2>/dev/null || :
}
trap 'lift_drain' EXIT HUP INT TERM

if [ -e "$DRAIN_SWITCH" ]; then
    log "already drained by someone else — leaving the flag alone"
elif [ -r "$FFWATCH" ]; then
    if python3 "$FFWATCH" drain >/dev/null 2>&1; then
        DRAINED=1
        log "drained: ffwatch will not launch while this runs"
    else
        echo "warmLibrary.sh: WARNING: could not set the drain flag; runs may queue on the lock" >&2
    fi
fi

# ------------------------------------------------------------------------------------------------
# Update golden
# ------------------------------------------------------------------------------------------------
if [ "$SKIP_UPDATE" -eq 1 ]; then
    log "skipping git update (--skip-update)"
else
    # --locked: the fd above is the lock, and re-acquiring it here would deadlock on a
    # non-recursive mutex. --verify: this is the deliberate, once-in-a-while pass over golden, so
    # it pays for the full LFS pointer scan that the per-run path skips when HEAD did not move.
    [ -x "$HERE/update-golden.sh" ] || die "$HERE/update-golden.sh is missing or not executable"
    sh "$HERE/update-golden.sh" --locked --verify || die "golden update failed"
fi

# ------------------------------------------------------------------------------------------------
# Warm Library/ from the CI cache
#
# THIS USED TO OPEN THE PROJECT IN UNITY. It ran `docker run ... -v "$GOLDEN_MNT:/workspace"` with
# no hardening flags and `unity-editor -quit -projectPath /workspace`, on FinalFactoryTester's own
# daemon, every time ffbox-update.timer brought commits — every five minutes. Opening the project
# IS running the project: the domain reload runs every [InitializeOnLoad] static constructor in
# the tree, and compilation runs the ILPostProcessors that com.unity.entities and com.unity.burst
# install. That was arbitrary repository code executing unattended as uid 1015, the account
# holding ~/.git-credentials, ~/.claude/.credentials.json and secrets.env, and in the sudo group.
# It is finding F1's outstanding half, reached by a path the finding does not name. See section 12
# of design/ffcache_design.txt.
#
# Now CI builds the Library, in a hardened single-use container as an account that owns nothing,
# and golden takes a copy. Data movement, not code execution: no container, no licence, no editor,
# nothing to escape from, and no 30-60 minute window to drain around.
#
# NEVER FATAL. No cache, no entry for the default branch, a truncated archive, a tar error: all of
# them leave golden with whatever Library it already had, which is stale at worst. The updater
# calls this on every commit and must not start failing because CI has not run yet.
# ------------------------------------------------------------------------------------------------

CACHE_DIR=${FFCACHE_DIR:-/opt/ffcache}
ENTRIES="$CACHE_DIR/entries"

# ONLY THE DEFAULT BRANCH'S ENTRY, and this is a security rule rather than a preference. A feature
# branch's entry is written by a CI job running code from that branch, contained at
# ffbox-container trust. Extracting it into golden would hand it to an editor that ffbox later
# runs at uid 1015. The default branch is not an escalation, because golden already IS the default
# branch's code by construction.
DEFAULT_BRANCH=${FFBOX_DEFAULT_BRANCH:-}
if [ -z "$DEFAULT_BRANCH" ]; then
    DEFAULT_BRANCH=$(git -C "$GOLDEN_MNT" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null \
                     | sed 's|^origin/||')
    [ -n "$DEFAULT_BRANCH" ] || DEFAULT_BRANCH=master
fi
# The same sanitisation main.yml applies before naming an entry, so the two agree on the filename.
SAFE_BRANCH=$(printf '%s' "$DEFAULT_BRANCH" | sed 's/[^a-zA-Z0-9._-]/-/g')

# The checkout's own answer, not a second copy of the version to keep in step with main.yml.
SCOPE=$(sed -n 's/^m_EditorVersion: *//p' "$GOLDEN_MNT/ProjectSettings/ProjectVersion.txt" 2>/dev/null \
        | tr -d ' \r')

ENTRY="$ENTRIES/$SAFE_BRANCH@$SCOPE.tar"

if [ ! -d "$ENTRIES" ]; then
    log "no cache at $ENTRIES — leaving Library/ as it is"
    log "  (provision it with: sudo sh $HERE/../ffgithubrunners/01-hostSetup.sh)"
    exit 0
fi
if [ -z "$SCOPE" ]; then
    log "could not read m_EditorVersion from $GOLDEN_MNT/ProjectSettings/ProjectVersion.txt"
    log "  leaving Library/ as it is"
    exit 0
fi
if [ ! -r "$ENTRY" ]; then
    log "no entry for the default branch at $(basename "$ENTRY") — leaving Library/ as it is"
    log "  present: $(ls "$ENTRIES" 2>/dev/null | tr '\n' ' ')"
    log "  one CI job on $DEFAULT_BRANCH will create it"
    exit 0
fi

if [ -d "$GOLDEN_MNT/Library" ] && [ "$FORCE" -eq 0 ]; then
    _entry_age=$(( $(date +%s) - $(stat -c %Y "$ENTRY" 2>/dev/null || echo 0) ))
    _lib_age=$((   $(date +%s) - $(stat -c %Y "$GOLDEN_MNT/Library" 2>/dev/null || echo 0) ))
    if [ "$_lib_age" -lt "$_entry_age" ]; then
        log "Library/ is newer than $(basename "$ENTRY") — nothing to do (--force to extract anyway)"
        exit 0
    fi
fi

log "warming Library/ from $(basename "$ENTRY") ($(du -h "$ENTRY" 2>/dev/null | cut -f1) on disk)"

# EXTRACT BESIDE, THEN SWAP. The design says replace wholesale, and this is that with a smaller
# window: a crash mid-extract leaves the old Library intact rather than half of a new one. The
# golden lock is held throughout either way, so no run can clone a torn tree — but the updater is
# killed by a timeout often enough that "the old one" is a better resting state than "half".
STAGE="$GOLDEN_MNT/.Library.warming.$$"
rm -rf "$STAGE"
mkdir -p "$STAGE"
# BOTH, and the same signal list as the drain trap above. A bare `trap cleanup_stage EXIT`
# REPLACES that earlier trap rather than adding to it, which would leave ffwatch drained forever
# after a successful warm: the flag is only removed by lift_drain, and nothing else ever clears
# it. Found by writing it that way first.
cleanup_stage() { rm -rf "$STAGE"; lift_drain; }
trap cleanup_stage EXIT HUP INT TERM

# ONLY ./Library. Never .git and never the worktree: update-golden.sh owns those, and a
# job-written .git is exactly what must never meet the host-side git of section 11. Members are
# stored with a leading ./ — verified against a real entry on 2026-08-29.
if ! tar -xf "$ENTRY" -C "$STAGE" ./Library 2>/dev/null; then
    log "WARNING: could not extract ./Library from $(basename "$ENTRY") — leaving Library/ as it is"
    exit 0
fi
[ -d "$STAGE/Library" ] || { log "WARNING: the archive had no ./Library — leaving Library/ as it is"; exit 0; }

_new=$(du -sh "$STAGE/Library" 2>/dev/null | cut -f1)
OLD="$GOLDEN_MNT/.Library.old.$$"
if [ -d "$GOLDEN_MNT/Library" ]; then
    mv "$GOLDEN_MNT/Library" "$OLD" || die "could not move the existing Library/ aside"
fi
if ! mv "$STAGE/Library" "$GOLDEN_MNT/Library"; then
    # Put it back rather than leaving golden with no Library at all.
    [ -d "$OLD" ] && mv "$OLD" "$GOLDEN_MNT/Library"
    die "could not move the extracted Library/ into place"
fi
rm -rf "$OLD"

log "done — golden Library/ is $_new, from $DEFAULT_BRANCH"
log "every future ffbox run now clones a warm project"
exit 0
