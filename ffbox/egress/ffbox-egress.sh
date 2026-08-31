#!/bin/sh
#
# ffbox-egress.sh — bring up (or inspect) the one route out of ffbox-net.
#
# WHAT THIS BUILDS
#
#   ffbox-net          a Docker --internal bridge, 10.80.0.0/24, interface name ffbox0. Internal
#                      means no default route at all: a container on it cannot reach the internet,
#                      cannot reach the LAN, and has nothing to talk to except its neighbours.
#   ffbox-egress-net   an ordinary NATted bridge. Only the proxy is on it.
#   ffbox-egress       the proxy, on BOTH, at 10.80.0.2. DNS and SNI filtering; see Dockerfile.
#
# THERE USED TO BE A HOST FIREWALL RULE HERE, and it is worth knowing why there is not any more.
# Under the ROOT Docker daemon, --internal stops routing but does NOT stop a container reaching
# the HOST at the bridge gateway: measured on this design, an internal-network container could
# open 22 and 445 on 10.80.0.1. So this script inserted an iptables INPUT drop for ffbox0, and
# needed root to do it, which is why ffbox-egress.service was the only ffbox unit running as
# root off a script the ffbox user can write.
#
# Under the ROOTLESS daemon the bridge lives inside the rootlesskit network namespace. The host
# is not on the other side of it. Re-measured on 2026-08-25 with no rule anywhere: a container
# on the internal network could not reach this host at all, while the proxy path and the seal
# against the internet both behaved exactly as before. The rule had nothing left to drop, so it
# is gone and so is the root. See design/rootless_docker_design.txt section 5.
#
# The run container joins ffbox-net with --dns 10.80.0.2 and holds no capability to change any of
# the above: all of it lives in the daemon's network namespace, not in the run's.
#
# Usage:
#   ffbox/egress/ffbox-egress.sh up          create what is missing, start the proxy
#   ffbox/egress/ffbox-egress.sh down        stop the proxy (leaves the networks in place)
#   ffbox/egress/ffbox-egress.sh status      what exists and what is running
#   ffbox/egress/ffbox-egress.sh log         destinations this proxy has been asked for
#
# Environment: FFBOX_EGRESS_MODE=log permits everything and records it. For discovering an
# allowlist on a new Unity version, never as a resting state.
#              FFBOX_EGRESS_FORCE=1 recreates the proxy even when nothing it depends on changed.
#              `up` is otherwise a no-op on an unchanged fence, so that it can be called by the
#              updater without taking egress away from a job that is mid-fetch.
set -eu

NET=${FFBOX_EGRESS_NET:-ffbox-net}
UPLINK=${FFBOX_EGRESS_UPLINK:-ffbox-egress-net}
BRIDGE=${FFBOX_EGRESS_BRIDGE:-ffbox0}
SUBNET=${FFBOX_EGRESS_SUBNET:-10.80.0.0/24}
IP=${FFBOX_EGRESS_IP:-10.80.0.2}
NAME=${FFBOX_EGRESS_NAME:-ffbox-egress}
IMAGE=${FFBOX_EGRESS_IMAGE:-ffbox-egress:latest}
MODE=${FFBOX_EGRESS_MODE:-enforce}

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ALLOWLIST=${FFBOX_EGRESS_ALLOWLIST:-$HERE/allowlist.txt}

say()  { printf '==> %s\n' "$*"; }
skip() { printf '    %s\n' "$*"; }
die()  { printf 'ffbox-egress: %s\n' "$*" >&2; exit 1; }

# NO PRIVILEGE HELPERS, and no `sudo docker` fallback. There used to be one, taken whenever the
# caller was not in the docker group, and after the move to the rootless daemon that is the
# normal case — it would have sent every command in this file to the ROOT daemon, quietly, to
# build a fence in a network namespace nothing runs in.
#
# docker is called by name. Which daemon it reaches is DOCKER_HOST's business, set by the unit
# and by the profile.d line, never guessed at here.
docker_() {
    docker "$@"
}

# --- pieces ---------------------------------------------------------------------------------------

ensure_networks() {
    if docker_ network inspect "$NET" >/dev/null 2>&1; then
        skip "network $NET exists"
    else
        say "creating $NET (internal, $SUBNET, bridge $BRIDGE)"
        # The bridge name is pinned rather than left as br-<hash> because the INPUT rule below
        # names an interface, and a rule that names an interface Docker chose is a rule that
        # silently stops matching the next time the network is recreated.
        docker_ network create --internal \
            --subnet "$SUBNET" \
            -o com.docker.network.bridge.name="$BRIDGE" \
            "$NET" >/dev/null
    fi

    if docker_ network inspect "$UPLINK" >/dev/null 2>&1; then
        skip "network $UPLINK exists"
    else
        say "creating $UPLINK (routed; the proxy alone sits on it)"
        docker_ network create "$UPLINK" >/dev/null
    fi
}

# WHAT THE RUNNING PROXY WOULD HAVE TO CHANGE FOR, in one string. Everything that decides what
# this container does: the image it runs, the mode it runs in, and the contents of the allowlist —
# which is bind-mounted, so its CONTENTS matter and its path does not.
proxy_fingerprint() {
    printf '%s %s %s' \
        "$(docker_ image inspect "$IMAGE" --format '{{.Id}}' 2>/dev/null || echo none)" \
        "$MODE" \
        "$(sha256sum "$ALLOWLIST" 2>/dev/null | cut -c1-64)"
}

start_proxy() {
    docker_ image inspect "$IMAGE" >/dev/null 2>&1 \
        || die "image $IMAGE is not built. Run: sh $HERE/../01-dockerSetup.sh  (or docker build -t $IMAGE $HERE)"
    [ -r "$ALLOWLIST" ] || die "cannot read $ALLOWLIST"

    # UP IS A NO-OP WHEN NOTHING HAS CHANGED, and that is what makes it safe to call from an
    # automatic updater. `rm -f` and recreate takes the fence down for a couple of seconds, and a
    # job or a run that is mid-fetch when that happens fails for a reason nobody will connect to
    # "someone pushed a commit". The old unconditional recreate was fine when a human ran this and
    # is not fine on a five-minute timer.
    #
    # The fingerprint lives on the container as a LABEL rather than in a file on the host: it then
    # cannot disagree with the thing it describes, and a container someone started by hand simply
    # has no label and gets recreated.
    _want=$(proxy_fingerprint)
    _have=$(docker_ inspect -f '{{index .Config.Labels "ffbox.egress.fingerprint"}}' "$NAME" 2>/dev/null || echo "")
    if [ "${FFBOX_EGRESS_FORCE:-0}" != 1 ] \
       && [ "$(docker_ inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = true ] \
       && [ -n "$_have" ] && [ "$_have" = "$_want" ]; then
        say "$NAME is already up with this image, mode and allowlist — leaving it alone"
        return 0
    fi
    [ -z "$_have" ] || [ "$_have" = "$_want" ] || say "the image, mode or allowlist changed; recreating $NAME"

    docker_ rm -f "$NAME" >/dev/null 2>&1 || true

    say "starting $NAME at $IP (mode=$MODE)"
    # Created then connected then started, rather than run --network twice: a container gets its
    # --ip on one network at creation, and the uplink has to be attached before it starts or the
    # proxy comes up with no way to reach anything itself.
    #
    # The allowlist is bind-mounted, so changing what is permitted is an edit and a restart of
    # this container. Nothing about it reaches the run container, which never sees this file.
    docker_ create \
        --name "$NAME" \
        --hostname ffbox-egress \
        --network "$NET" --ip "$IP" \
        --restart unless-stopped \
        --label ffbox.egress.fingerprint="$_want" \
        --read-only --tmpfs /var/run --tmpfs /var/cache/nginx --tmpfs /tmp \
        --cap-drop ALL --cap-add NET_BIND_SERVICE --cap-add SETUID --cap-add SETGID \
        --security-opt no-new-privileges \
        -e FFBOX_EGRESS_IP="$IP" \
        -e FFBOX_EGRESS_MODE="$MODE" \
        -v "$ALLOWLIST:/etc/ffbox/allowlist.txt:ro" \
        "$IMAGE" >/dev/null
    docker_ network connect "$UPLINK" "$NAME"
    docker_ start "$NAME" >/dev/null

    # A proxy that exits three seconds later leaves every run to fail at Unity activation with an
    # error about licensing, which is a long way from the truth. Say so here instead.
    sleep 2
    if [ "$(docker_ inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != true ]; then
        docker_ logs "$NAME" 2>&1 | tail -20 >&2
        die "$NAME did not stay up (logs above)"
    fi
    say "$NAME is up"
}

# --- commands -------------------------------------------------------------------------------------

cmd_up() {
    command -v docker >/dev/null || die "docker not found"
    ensure_networks
    start_proxy
    printf '\n'
    skip "allowing: $(sed 's/#.*//' "$ALLOWLIST" | tr -d ' \t\r' | grep -v '^$' | tr '\n' ' ')"
    skip "runs join with: --network $NET --dns $IP"
}

cmd_down() {
    docker_ rm -f "$NAME" >/dev/null 2>&1 && say "$NAME removed" || skip "$NAME was not running"
    skip "networks left in place — a half-removed fence is worse than none"
}

cmd_status() {
    for n in "$NET" "$UPLINK"; do
        if docker_ network inspect "$n" >/dev/null 2>&1; then
            printf '  network %-18s present\n' "$n"
        else
            printf '  network %-18s MISSING\n' "$n"
        fi
    done
    state=$(docker_ inspect -f '{{.State.Status}}' "$NAME" 2>/dev/null || echo absent)
    printf '  proxy   %-18s %s\n' "$NAME" "$state"
    printf '  daemon  %-18s %s\n' "" "${DOCKER_HOST:-<default socket>}"
    mode=$(docker_ inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$NAME" 2>/dev/null \
           | sed -n 's/^FFBOX_EGRESS_MODE=//p')
    [ -z "$mode" ] || printf '  mode    %-18s %s\n' "" "$mode"
    [ "$mode" != log ] || printf '  WARNING: log mode permits everything. Restart in enforce mode.\n'
}

cmd_log() {
    printf 'destinations asked for (count, name, verdict):\n\n'
    docker_ logs "$NAME" 2>&1 \
        | sed -n 's/.*sni=\([^ ]*\) upstream=\([^ ]*\).*/\1 \2/p' \
        | awk '{ v = ($2 == "127.0.0.1:9" ? "DENIED" : "allowed"); print $1, v }' \
        | sort | uniq -c | sort -rn
}

case "${1:-up}" in
    up)      cmd_up ;;
    down)    cmd_down ;;
    status)  cmd_status ;;
    log)     cmd_log ;;
    -h|--help) sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//' ;;
    *)       die "unknown command '$1' (up|down|status|log)" ;;
esac
