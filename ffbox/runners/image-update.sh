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
# THE DRAIN FLAG IS CLEARED ON EVERY EXIT PATH. A flag left set idles every slot indefinitely, and
# that is a much worse failure than a skipped update. The flag records why and by whom, so
# `ffgithubrunners status` can say so if this is ever SIGKILLed between the two.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

RUNNER_VERSION=""
NO_DRAIN=0
case "${1:-}" in
    --no-drain) NO_DRAIN=1 ;;
    --runner)   RUNNER_VERSION=${2:?--runner needs a version} ;;
    --help|-h)  sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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

say "pulling the base image"
BASE=$(sed -n 's/^ARG UNITY_IMAGE=//p' "$HERE/Dockerfile" | head -1)
[ -n "$BASE" ] || die "could not read UNITY_IMAGE from the Dockerfile"
docker pull "$BASE" || die "could not pull $BASE"

say "building $IMAGE with runner $RUNNER_VERSION"
docker build --build-arg "RUNNER_VERSION=$RUNNER_VERSION" -t "$IMAGE" "$HERE" \
    || die "the build failed; the previous $IMAGE is untouched"

NEW_RUNNER=$(docker image inspect "$IMAGE" \
             --format '{{index .Config.Labels "org.finalfactory.runner-version"}}' 2>/dev/null || echo unknown)
say "$IMAGE now carries runner $NEW_RUNNER"

# Old layers from previous builds of THIS image only. Never `docker image prune`, which on a shared
# daemon would reach ffbox's images.
skip "note: superseded layers are left on the daemon; this store is shared with ffbox"
