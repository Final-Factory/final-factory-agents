#!/bin/sh
# image-update.sh — rebuild the runner image with a current runner and a current base.
#
# GitHub enforces a minimum runner version, and a runner baked into a container cannot self-update
# (--disableupdate is a config.sh option that `run` does not accept, and there is no environment
# variable for it either). So a stale image eventually stops being given jobs, and this weekly
# rebuild is the only thing that prevents it.
#
# DRAINS FIRST. Not to protect a running job, which is unaffected: a container holds its image by
# id and a rebuild only retags. The drain is so a slot does not pick up a NEW job partway through
# an update, finish it, and leave the operator unsure which image ran it.
#
# IT COMMITS. The new version is written into ffbox/Dockerfile and pushed, because every other
# build path uses that ARG and a version living only in one image is undone by the next rebuild.
# See pin_runner_version below for the guards; the short version is that it only ever commits a
# version that has just built, on a clean checkout that is exactly at origin, under the
# self-updater's lock, and it rolls the commit back if the push fails.
#
# THE DRAIN FLAG IS CLEARED ON EVERY EXIT PATH. A flag left set idles every slot indefinitely, and
# that is a much worse failure than a skipped update. The flag records why and by whom, so
# `ffgithubrunners status` can say so if this is ever SIGKILLed between the two.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# ffbox/, one level up, where the one Dockerfile lives. Same line as 03-image.sh.
FFBOX=$(CDPATH= cd -- "$HERE/.." && pwd)

RUNNER_VERSION=""
NO_DRAIN=0
# Record a version in the Dockerfile and push it, WITHOUT draining or building. For a version that
# was built by hand, for a rebuild whose push failed, and — the reason it exists — so the commit
# path can be tested against a scratch checkout without a Unity base image. test_pin.sh.
PIN_ONLY=""
case "${1:-}" in
    --no-drain) NO_DRAIN=1 ;;
    --runner)   RUNNER_VERSION=${2:?--runner needs a version} ;;
    --pin-only) PIN_ONLY=${2:?--pin-only needs a version}; RUNNER_VERSION=$PIN_ONLY ;;
    --help|-h)  sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    "")         ;;
    *)          echo "image-update.sh: unknown option $1" >&2; exit 2 ;;
esac

. "$HERE/lib/config.sh"

say()  { printf '==> %s\n' "$*"; }
skip() { printf '    %s\n' "$*"; }
die()  { printf 'image-update.sh: %s\n' "$*" >&2; exit 1; }

DRAINED_BY_US=0
undrain() {
    _rc=$?
    trap - EXIT INT TERM
    if [ "$DRAINED_BY_US" = 1 ]; then
        rm -f "$FFGHR_DRAIN_FLAG" && say "drain lifted"
    fi
    exit "$_rc"
}
trap undrain EXIT INT TERM

# --- keep it ---------------------------------------------------------------------------------
#
# THE BUILD ARG IS NOT WHERE A VERSION LIVES. This used to end here, with the new runner in the
# image and nothing else, and the version therefore lasted until the next rebuild: every other
# path — ffbox/03-build.sh, ffbox/runners/03-image.sh, the self-updater on every commit — builds
# with no --build-arg and gets the Dockerfile's ARG RUNNER_VERSION. On a box that takes a commit
# every few minutes, Sunday's bump was gone by Monday and the weekly log then said "already
# current" forever, because it compares against the image it had just rebuilt. Nobody would have
# noticed until GitHub stopped scheduling jobs.
#
# So the version goes where every build already reads it from: the Dockerfile, in git, pushed. The
# self-updater then carries it to every machine the way it carries anything else, and the bump is
# one revertible commit rather than a mutation nothing recorded.
#
# ORDER MATTERS AND IS THE SAFETY PROPERTY. The build above ALREADY PROVED this version: the
# Dockerfile runs `./bin/Runner.Listener --version` at build time, so a release that does not
# unpack or does not run fails the build and this is never reached. Only a version that built is
# ever written down.
pin_runner_version() {
    _pin=$(sed -n 's/^ARG RUNNER_VERSION=//p' "$FFBOX/Dockerfile" | head -1)
    if [ -z "$_pin" ]; then
        say "WARNING: no ARG RUNNER_VERSION in $FFBOX/Dockerfile; the version was not recorded and
    the next rebuild will undo this one"
        return 0
    fi
    if [ "$_pin" = "$RUNNER_VERSION" ]; then
        skip "the Dockerfile already pins $RUNNER_VERSION; nothing to record"
        return 0
    fi

    # NOT AS ROOT. git as root leaves root-owned objects in .git and breaks every later pull by
    # the owner — the same reason update_ffbox.sh has its as_owner dance. A human who ran this
    # under sudo gets the image and a line telling them what is owed.
    if [ "$(id -u)" = 0 ]; then
        say "WARNING: running as root, so the pin was NOT committed. As the checkout's owner:"
        say "         sed -i 's/^ARG RUNNER_VERSION=.*/ARG RUNNER_VERSION=$RUNNER_VERSION/' $FFBOX/Dockerfile"
        return 0
    fi

    _repo=$(git -C "$FFBOX" rev-parse --show-toplevel 2>/dev/null || echo "")
    [ -n "$_repo" ] || { say "WARNING: $FFBOX is not in a git checkout; the pin was not recorded"; return 0; }

    # UNDER THE SELF-UPDATER'S OWN LOCK, and this is not optional. update_ffbox.sh fast-forwards
    # this same checkout every five minutes; a merge landing between the checks below and the push
    # would have this committing onto a HEAD that moved, and the rollback would rewind the box to
    # a commit it had already deployed. The updater takes this lock non-blocking, so while it is
    # held the updater says "another update is already running" and comes back in five minutes.
    #
    # Everything inside is a fetch, a sed, a commit and a push: about a second.
    _lock=${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}/update.lock
    mkdir -p "$(dirname "$_lock")" 2>/dev/null || true
    (
        flock -w 60 9 || { printf 'could not take %s within 60s; not recording the pin\n' "$_lock" >&2; exit 3; }
        set -eu
        _branch=$(git -C "$_repo" rev-parse --abbrev-ref HEAD)
        [ "$_branch" = "${FFBOX_UPDATE_BRANCH:-master}" ] \
            || { printf 'on branch %s, not %s; not recording the pin\n' "$_branch" "${FFBOX_UPDATE_BRANCH:-master}" >&2; exit 3; }
        [ -z "$(git -C "$_repo" status --porcelain)" ] \
            || { printf 'the working tree is dirty; not recording the pin\n' >&2; exit 3; }

        git -C "$_repo" fetch --quiet origin "$_branch"
        _head=$(git -C "$_repo" rev-parse HEAD)
        _remote=$(git -C "$_repo" rev-parse FETCH_HEAD)
        # A COMMIT ONLY ON TOP OF THE REMOTE. Committing while behind produces a merge nobody
        # asked for; committing while ahead means an earlier push failed and this would stack a
        # second unpushed commit on it — and an unpushed commit here stops the self-updater dead,
        # because "local is ahead of origin" is one of its reasons to do nothing.
        [ "$_head" = "$_remote" ] \
            || { printf 'HEAD and origin/%s differ; not recording the pin\n' "$_branch" >&2; exit 3; }

        sed -i "s|^ARG RUNNER_VERSION=.*|ARG RUNNER_VERSION=$RUNNER_VERSION|" "$FFBOX/Dockerfile"
        git -C "$_repo" add -- "$FFBOX/Dockerfile"
        git -C "$_repo" commit --quiet -m "ffghr: runner $_pin -> $RUNNER_VERSION

Written by the weekly image rebuild (ffgithubrunners-image.service) on $(hostname -s).
The version has to live in the Dockerfile rather than in a --build-arg: every other
build path uses the ARG default, so a version that exists only in one image is undone
by the next rebuild.

This version was BUILT before it was written here -- the Dockerfile runs
Runner.Listener --version, so a release that does not unpack or run never gets this
far. Revert this commit to go back; the next rebuild follows the pin." \
            || { printf 'the commit failed; nothing was recorded\n' >&2; exit 3; }

        if git -C "$_repo" push --quiet origin "HEAD:$_branch"; then
            printf 'recorded runner %s in the Dockerfile and pushed\n' "$RUNNER_VERSION"
        else
            # LEAVE NOTHING BEHIND. An unpushed commit stops the self-updater on this box, and a
            # dirty tree stops it too, so a failed push must undo both. Safe here and only here:
            # the tree was clean and at the remote a moment ago, under this lock.
            git -C "$_repo" reset --hard --quiet "$_head"
            printf 'the push failed; rolled back to %s. The image has runner %s, the Dockerfile
    still pins %s, and the next rebuild will go back to it.\n' "$(printf %.12s "$_head")" "$RUNNER_VERSION" "$_pin" >&2
            exit 3
        fi
    ) 9>>"$_lock" 2>&1 | while IFS= read -r _line; do skip "$_line"; done
}

if [ -n "$PIN_ONLY" ]; then
    pin_runner_version
    exit 0
fi

docker version >/dev/null 2>&1 || die "cannot reach $DOCKER_SOCK"

# What is baked in now, so the log says what changed rather than just that something did.
OLD_RUNNER=$(docker image inspect "$IMAGE" \
             --format '{{index .Config.Labels "org.finalfactory.runner-version"}}' 2>/dev/null || echo none)

# The latest runner release. Asked for rather than assumed, because the whole point of this script
# is that the version moves. This runs on the HOST, which is not behind the egress fence.
if [ -z "$RUNNER_VERSION" ]; then
    RUNNER_VERSION=$(curl -fsSL --max-time 30 \
        https://api.github.com/repos/actions/runner/releases/latest 2>/dev/null \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tag_name","").lstrip("v"))' 2>/dev/null || echo "")
    [ -n "$RUNNER_VERSION" ] || die "could not determine the latest runner version; pass --runner X.Y.Z"
fi

say "runner: $OLD_RUNNER installed, $RUNNER_VERSION available"
if [ "$OLD_RUNNER" = "$RUNNER_VERSION" ]; then
    skip "already current; rebuilding anyway to pick up base image and package updates"
fi

if [ "$NO_DRAIN" = 0 ]; then
    if [ -e "$FFGHR_DRAIN_FLAG" ]; then
        skip "already drained by someone else; leaving the flag alone"
    else
        printf 'image-update pid=%s started=%s\n' "$$" "$(date -Is)" > "$FFGHR_DRAIN_FLAG"
        DRAINED_BY_US=1
        say "drained; slots will idle rather than take new work"
    fi
fi

# THE DOCKERFILE IS IN ffbox/, NOT HERE, and this script had its own copy of the build command
# that still said otherwise. From 2026-08-23 to 2026-08-31 every weekly rebuild died on
#   sed: can't read .../ffbox/runners/Dockerfile: No such file or directory
# and left ffgithubrunners-image.service in `failed`, which is a silent way to stop being given
# jobs: a runner that falls below GitHub's minimum version is simply never scheduled.
#
# So the build is DELEGATED rather than repeated. 03-image.sh already knows where the Dockerfile
# is, what to tag and what to pass; two copies of that is what drifted in the first place.
say "pulling the base image"
BASE=$(sed -n 's/^ARG UNITY_IMAGE=//p' "$FFBOX/Dockerfile" | head -1)
[ -n "$BASE" ] || die "could not read UNITY_IMAGE from $FFBOX/Dockerfile"
docker pull "$BASE" || die "could not pull $BASE"

say "building $IMAGE with runner $RUNNER_VERSION"
sh "$HERE/03-image.sh" --image-only --runner "$RUNNER_VERSION" \
    || die "the build failed; the previous $IMAGE is untouched"

NEW_RUNNER=$(docker image inspect "$IMAGE" \
             --format '{{index .Config.Labels "org.finalfactory.runner-version"}}' 2>/dev/null || echo unknown)
say "$IMAGE now carries runner $NEW_RUNNER"


pin_runner_version

# Old layers from previous builds of THIS image only. Never `docker image prune`, which on a shared
# daemon would reach ffbox's images.
skip "note: superseded layers are left on the daemon; this store is shared with ffbox"
