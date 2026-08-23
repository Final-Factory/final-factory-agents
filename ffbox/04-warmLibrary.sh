#!/bin/sh
#
# warmLibrary.sh — bring the golden checkout up to date, then open it once in Unity so it builds
# its Library/ import cache.
#
# Pay the cold import exactly once, here, in golden. Every ffbox run is a ZFS clone of golden, so
# each one then inherits the finished Library/ for free instead of importing from scratch.
#
# Runs Unity inside the ffbox image — there is no Unity on the host — with golden bind-mounted
# read-write, since the whole point is to leave Library/ behind.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

IMAGE=${FFBOX_IMAGE:-ffbox:latest}
GOLDEN_MNT=${FFBOX_GOLDEN_MNT:-/opt/FinalFactory}
CONFIG_DIR=${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}
GOLDEN_LOCK=${FFBOX_GOLDEN_LOCK:-$CONFIG_DIR/golden.lock}
DRAIN_SWITCH=$CONFIG_DIR/draining
FFWATCH=$HERE/ffwatch.py
SECRETS=${FFBOX_SECRETS:-$HOME/.config/ffbox/secrets.env}
RESULTS=${FFBOX_RESULTS:-$HOME/ffbox-runs}

FORCE=0
SKIP_UPDATE=0

usage() {
    cat <<EOF
Usage: sh warmLibrary.sh [options]

Updates ${GOLDEN_MNT} from its remote, then runs a Unity batch-mode import so golden carries a
warm Library/. Slow on a cold project (30-60 minutes); fast and harmless once warm.

Options:
  --force         Re-import even if Library/ already exists.
  --skip-update   Do not touch git; import whatever is currently checked out.
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

command -v docker >/dev/null || die "docker not found"
docker image inspect "$IMAGE" >/dev/null 2>&1 || die "image '$IMAGE' not built — run: sh ffbox/build.sh"
[ -d "$GOLDEN_MNT/.git" ] || die "$GOLDEN_MNT is not a git checkout"

# Unity takes an exclusive lock on a project directory, so two warm-ups on golden cannot overlap.
if docker ps --format '{{.Names}}' | grep -q '^ffbox-warm$'; then
    die "a warm-up is already running (container ffbox-warm)"
fi

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
# Import
# ------------------------------------------------------------------------------------------------
if [ -d "$GOLDEN_MNT/Library" ] && [ "$FORCE" -eq 0 ]; then
    log "Library/ already present ($(du -sh "$GOLDEN_MNT/Library" 2>/dev/null | cut -f1)) — re-importing to pick up the changes just pulled"
    log "(use --force only to rebuild from scratch; delete Library/ by hand for a truly cold import)"
fi

[ -r "$SECRETS" ] || die "no secrets file at $SECRETS — the import needs a Unity license.
       Run 'sh ffbox/setup.sh' to drop the template there, then fill it in."

OUT="${RESULTS}/warm-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"

set -a
# shellcheck disable=SC1090
. "$SECRETS"
set +a

# Same ULF-to-serial decode game-ci performs: the .ulf itself never enters the container.
if [ -z "${UNITY_SERIAL:-}" ] && [ -n "${UNITY_LICENSE_FILE:-}" ]; then
    [ -r "$UNITY_LICENSE_FILE" ] || die "cannot read UNITY_LICENSE_FILE=$UNITY_LICENSE_FILE"
    UNITY_SERIAL=$(sed -n 's/.*<DeveloperData Value="\([^"]*\)".*/\1/p' "$UNITY_LICENSE_FILE" \
                   | head -1 | base64 -d 2>/dev/null | cut -c5-)
    export UNITY_SERIAL
    [ ${#UNITY_SERIAL} -eq 27 ] || die "extracted a ${#UNITY_SERIAL}-char serial; expected 27"
fi

# Fail here, not after pulling up an 11GB container that gets as far as the activation call.
for _v in UNITY_EMAIL UNITY_PASSWORD UNITY_SERIAL; do
    eval "_set=\${$_v:-}"
    [ -n "$_set" ] || die "$_v is not set in $SECRETS.
       Unity activation is an ONLINE serial activation, so all three of UNITY_EMAIL,
       UNITY_PASSWORD and UNITY_SERIAL are required — even for a Personal license.
       Provide the 27-character serial directly, or set UNITY_LICENSE_FILE to a .ulf
       and ffbox will decode the serial out of it the way game-ci does."
done

log "starting Unity import (logs: $OUT/import.log)"
log "this is the slow step — a cold import can take 30-60 minutes"

# No --rm: on failure the container is worth inspecting. It is removed on success below.
docker run \
    --name ffbox-warm \
    --hostname ffbox-warm \
    -v "$GOLDEN_MNT:/workspace" \
    -v "$OUT:/ffbox/out" \
    -e FFBOX_ENTRY=/ffbox/import-project.sh \
    -e UNITY_SERIAL -e UNITY_EMAIL -e UNITY_PASSWORD \
    "$IMAGE" && rc=0 || rc=$?

if [ "$rc" -eq 0 ]; then
    docker rm ffbox-warm >/dev/null 2>&1 || true
    log "done — golden Library/ is $(du -sh "$GOLDEN_MNT/Library" 2>/dev/null | cut -f1)"
    log "every future ffbox run now clones a warm project"
else
    echo "warmLibrary.sh: import failed (exit $rc). Container 'ffbox-warm' kept for inspection:" >&2
    echo "  docker logs ffbox-warm | tail -50" >&2
    echo "  docker rm ffbox-warm" >&2
    echo "  log: $OUT/import.log" >&2
fi

exit "$rc"
