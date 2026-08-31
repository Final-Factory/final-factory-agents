#!/bin/sh
# 03-image.sh — the runner image, and the fence it runs behind.
#
# Two things, because neither is any use without the other: a container that cannot resolve a
# name is not a runner, and a fence with nothing behind it is not worth starting.
#
#   ffbox-egress:latest   the proxy image. ffbox's, but ffbox built it onto the OTHER daemon, and
#                         ffbox-egress.sh fails closed rather than building it.
#   ffbox:latest          the one image, for both agent runs and CI. See ffbox/Dockerfile.
#   ffghr-net             an --internal bridge, no default route, its own subnet.
#   ffghr-egress          the proxy, on both that and a routed uplink.
#
# EGRESS IS FFBOX'S SCRIPT, NOT A SECOND MECHANISM. ffbox/egress/ffbox-egress.sh already builds
# exactly this fence and parameterises every name through FFBOX_EGRESS_*, so this runs a second
# instance of it against a second allowlist. Under the rootless daemon the bridge lives inside
# rootlesskit's network namespace, so no host firewall rule and no root are involved.
#
# Needs no root. Everything happens against ffbox-container's daemon, through the group.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# ffbox/, one level up: this lives at ffbox/runners/ since the two systems became one tree.
FFBOX=$(CDPATH= cd -- "$HERE/.." && pwd)

DO_IMAGE=1
DO_EGRESS=1
NO_CACHE=""
EGRESS_LOG=0
RUNNER_VERSION=""
GH_VERSION=""

usage() {
  cat <<EOF
Usage: sh ffbox/runners/03-image.sh [options]

Builds the runner image and brings up its egress fence, both on ffbox-container's daemon.
Idempotent — re-run any time.

Options (alphabetical):
  --egress-log      Print the destinations the proxy has been asked for, and exit. This is how
                    open item (a) gets closed: run jobs with FFBOX_EGRESS_MODE=log, then read
                    back what they actually reached for.
  --egress-only     Bring up the fence; do not build the runner image.
  --gh VERSION      gh version to bake in (default: the Dockerfile's).
  --help            Show this message.
  --image-only      Build the images; do not touch the networks or the proxy.
  --no-cache        Rebuild the runner image from scratch.
  --runner VERSION  Actions runner version to bake in (default: the Dockerfile's).

Environment:
  FFBOX_EGRESS_MODE=log   Permit everything and record it. For discovering the allowlist on a new
                          Unity or runner version, never as a resting state.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --egress-log)  EGRESS_LOG=1; shift ;;
    --egress-only) DO_IMAGE=0; shift ;;
    --gh)          GH_VERSION=${2:?--gh needs a version}; shift 2 ;;
    --help|-h)     usage; exit 0 ;;
    --image-only)  DO_EGRESS=0; shift ;;
    --no-cache)    NO_CACHE=--no-cache; shift ;;
    --runner)      RUNNER_VERSION=${2:?--runner needs a version}; shift 2 ;;
    *)             echo "03-image.sh: unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
done

say()  { printf '==> %s\n' "$*"; }
skip() { printf '    %s\n' "$*"; }
die()  { printf '03-image.sh: %s\n' "$*" >&2; exit 1; }

. "$HERE/lib/config.sh"

EGRESS_SH="$FFBOX/egress/ffbox-egress.sh"
[ -x "$EGRESS_SH" ] || die "$EGRESS_SH is missing. This design shares ffbox's egress tooling; a
       checkout without ffbox/ cannot build the fence."

# Every FFBOX_EGRESS_* this system overrides, in one place, so the proxy's address and the --dns
# the supervisor passes cannot drift apart: both come from lib/config.sh.
egress() {
  FFBOX_EGRESS_NET="$EGRESS_NET" \
  FFBOX_EGRESS_UPLINK="$EGRESS_UPLINK" \
  FFBOX_EGRESS_BRIDGE="$EGRESS_BRIDGE" \
  FFBOX_EGRESS_SUBNET="$EGRESS_SUBNET" \
  FFBOX_EGRESS_IP="$EGRESS_IP" \
  FFBOX_EGRESS_NAME="$EGRESS_NAME" \
  FFBOX_EGRESS_IMAGE="$EGRESS_IMAGE" \
  FFBOX_EGRESS_ALLOWLIST="$HERE/egress/allowlist.txt" \
  sh "$EGRESS_SH" "$@"
}

# ffbox-egress.sh's own `log` greps for sni= lines, and so misses one of the two ways a name is
# refused. A name whose SUFFIX matches nothing on the list gets NXDOMAIN from dnsmasq and never
# opens a connection, so it leaves no sni= line at all; only a name that resolved and was then
# turned away by nginx appears there, as upstream=127.0.0.1:9. An operator whose job failed on a
# missing host would run the log, see nothing, and conclude nothing was blocked. Show both.
# docs/egress.md has the full decision path.
if [ "$EGRESS_LOG" -eq 1 ]; then
  egress log
  printf '\nrefused at DNS (count, name) — these never reached the SNI stage:\n\n'
  docker logs "$EGRESS_NAME" 2>&1 \
    | sed -n 's/.*config \([^ ]*\) is NXDOMAIN.*/\1/p' \
    | sort | uniq -c | sort -rn \
    | sed 's/^/  /'
  printf '\n'
  printf '  Nothing listed above means nothing was refused. A job that could not reach a host\n'
  printf '  and left no line here failed for some other reason.\n'
  exit 0
fi

docker version >/dev/null 2>&1 \
  || die "cannot reach $DOCKER_SOCK. Run 02-daemon.sh, and check you are in the $CONTAINER_USER
       group in THIS session — usermod -aG only applies to new ones."

# --- the images ---------------------------------------------------------------------------------

if [ "$DO_IMAGE" -eq 0 ]; then
  skip "runner image skipped (--egress-only)"
else
  BUILD_ARGS=""
  [ -z "$RUNNER_VERSION" ] || BUILD_ARGS="$BUILD_ARGS --build-arg RUNNER_VERSION=$RUNNER_VERSION"
  [ -z "$GH_VERSION" ]     || BUILD_ARGS="$BUILD_ARGS --build-arg GH_VERSION=$GH_VERSION"

  say "building $IMAGE (this pulls the Unity base image; it is slow the first time)"
  # shellcheck disable=SC2086  # NO_CACHE and BUILD_ARGS are deliberately word-split option lists
  # ONE Dockerfile, in ffbox/. The runner image and the ffbox image are the same image built from
  # the same source; only the tag and the daemon differ until section 17 merges those too.
  docker build $NO_CACHE $BUILD_ARGS -t "$IMAGE" "$FFBOX" \
    || die "the runner image did not build"
  skip "$IMAGE is $(docker image inspect "$IMAGE" --format '{{.Size}}' | awk '{printf "%.1f GB", $1/1073741824}'), runner $(docker image inspect "$IMAGE" --format '{{index .Config.Labels "org.finalfactory.runner-version"}}')"
fi

if [ "$DO_EGRESS" -eq 0 ]; then
  skip "egress skipped (--image-only)"
  exit 0
fi

# The proxy image is ffbox's and lives in ffbox/egress/. It was built onto FinalFactoryTester's
# daemon by ffbox's own setup, which this daemon knows nothing about, and ffbox-egress.sh fails
# closed rather than building it. So build it here.
if docker image inspect "$EGRESS_IMAGE" >/dev/null 2>&1; then
  skip "$EGRESS_IMAGE is present on this daemon"
else
  say "building $EGRESS_IMAGE from ffbox/egress/"
  docker build -t "$EGRESS_IMAGE" "$FFBOX/egress" || die "the egress image did not build"
fi

# --- the fence -------------------------------------------------------------------------------------

say "bringing up $EGRESS_NET and $EGRESS_NAME"
egress up

# ffbox is on its own subnet on this same daemon. Overlapping them would put a job on the same
# wire as an ffbox run, which is the one thing two separate fences exist to prevent.
FFBOX_SUBNET=$(docker network inspect ffbox-net --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null || true)
if [ -n "$FFBOX_SUBNET" ] && [ "$FFBOX_SUBNET" = "$EGRESS_SUBNET" ]; then
  die "ffbox-net and $EGRESS_NET are both $EGRESS_SUBNET. Change egress_subnet and egress_ip in
       config.json; two fences sharing a wire is not two fences."
fi

printf '\n'
# --- the local git mirror ---------------------------------------------------------------------
#
# Where a job fetches the repository instead of github.com. It has to be a CONTAINER on
# $EGRESS_NET rather than a daemon on the host: that network is --internal, and under the rootless
# daemon the real host is not reachable from it at all.
#
# Additive while github.com is still on the allowlist -- a job whose mirror is missing or behind
# just fetches from GitHub as before -- so nothing here is allowed to be fatal.
if [ -d "$MIRROR_DIR/$MIRROR_REPO" ]; then
  if docker image inspect "$MIRROR_IMAGE" >/dev/null 2>&1; then
    skip "$MIRROR_IMAGE is present"
  else
    say "building $MIRROR_IMAGE from ffbox/runners/gitmirror/"
    docker build -t "$MIRROR_IMAGE" "$HERE/gitmirror" \
      || say "WARNING: the mirror image did not build; jobs will fetch from github.com"
  fi
  if docker image inspect "$MIRROR_IMAGE" >/dev/null 2>&1; then
    # LEFT ALONE WHEN IT IS ALREADY SERVING THIS IMAGE, for the same reason the fence is: a
    # recreate takes the mirror away for a second, and a job mid-fetch through it fails for a
    # reason nobody will connect to a commit landing. The container records the image id it was
    # created from, so that comparison needs nothing kept on the side.
    _mwant=$(docker image inspect "$MIRROR_IMAGE" --format '{{.Id}}' 2>/dev/null || echo none)
    _mhave=$(docker inspect -f '{{.Image}}' "$MIRROR_NAME" 2>/dev/null || echo "")
    _mrun=$(docker inspect -f '{{.State.Running}}' "$MIRROR_NAME" 2>/dev/null || echo false)
    if [ "$_mrun" = true ] && [ "$_mhave" = "$_mwant" ]; then
      skip "$MIRROR_NAME is already up on this image at $MIRROR_IP"
      skip "jobs fetch the repository from $MIRROR_URL"
      _mskip=1
    else
      _mskip=0
    fi
  fi
  if docker image inspect "$MIRROR_IMAGE" >/dev/null 2>&1 && [ "${_mskip:-0}" = 0 ]; then
    docker rm -f "$MIRROR_NAME" >/dev/null 2>&1 || true
    say "bringing up $MIRROR_NAME at $MIRROR_IP"
    docker run -d --name "$MIRROR_NAME" --hostname "$MIRROR_NAME" \
      --network "$EGRESS_NET" --ip "$MIRROR_IP" \
      --restart unless-stopped \
      --read-only --tmpfs /tmp \
      --cap-drop ALL --security-opt no-new-privileges \
      -v "$MIRROR_DIR:/srv:ro" \
      "$MIRROR_IMAGE" >/dev/null \
      && skip "jobs fetch the repository from $MIRROR_URL" \
      || say "WARNING: $MIRROR_NAME did not start; jobs will fetch from github.com"
  fi
else
  say "no mirror at $MIRROR_DIR/$MIRROR_REPO; jobs will fetch from github.com"
  say "  create one with: git clone --bare --no-local $GOLDEN_MNT $MIRROR_DIR/$MIRROR_REPO"
fi

skip "jobs join with: --network $EGRESS_NET --dns $EGRESS_IP"
skip "next: sh $HERE/04-github.sh"
