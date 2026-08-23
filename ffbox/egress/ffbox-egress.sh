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
#   an INPUT rule      Docker's --internal stops routing, but it does NOT stop the container from
#                      reaching the HOST at the bridge gateway address. Measured on this design:
#                      an internal-network container could open 22 and 445 on 10.80.0.1. So every
#                      packet arriving from ffbox0 addressed to the host itself is dropped here.
#                      Without this the fence has a gate in it.
#
# The run container joins ffbox-net with --dns 10.80.0.2 and holds no capability to change any of
# the above: all of it lives in the host's network namespace and in Docker's, not in the run's.
#
# Usage:
#   ffbox/egress/ffbox-egress.sh up          create what is missing, apply rules, start the proxy
#   ffbox/egress/ffbox-egress.sh down        stop the proxy (leaves the networks and the rules)
#   ffbox/egress/ffbox-egress.sh status      what exists, what is running, whether rules are live
#   ffbox/egress/ffbox-egress.sh log         destinations this proxy has been asked for
#   ffbox/egress/ffbox-egress.sh rules       (re)apply the host INPUT rules only
#
# Environment: FFBOX_EGRESS_MODE=log permits everything and records it. For discovering an
# allowlist on a new Unity version, never as a resting state.
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

# Root is checked ONCE, up front, and said plainly. Discovering it inside the rule check means
# the message lands on a stderr that the check has already redirected to /dev/null, and the script
# looks like it stopped for no reason.
have_root() {
    [ "$(id -u)" = 0 ] || sudo -n true 2>/dev/null || [ -t 0 ]
}

require_root() {
    have_root && return 0
    printf 'ffbox-egress: %s needs root, and there is no terminal to ask on.\n' "$1" >&2
    printf '              Run this once, from a terminal:  sudo sh %s rules\n' "$0" >&2
    exit 1
}

as_root() {
    if [ "$(id -u)" = 0 ]; then "$@"; else sudo "$@"; fi
}

docker_() {
    if [ "$(id -u)" = 0 ] || id -nG 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
        docker "$@"
    else
        sudo docker "$@"
    fi
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

# Idempotent by check-then-insert. Applied at "up" and again at boot by ffbox-egress.service,
# because netfilter rules do not survive a reboot and a missing rule is silent.
apply_rules() {
    require_root "the INPUT rule that keeps $BRIDGE off this host"
    _applied=0
    for _ipt in iptables ip6tables; do
        command -v "$_ipt" >/dev/null 2>&1 || continue
        if as_root "$_ipt" -C INPUT -i "$BRIDGE" -j DROP 2>/dev/null; then
            skip "$_ipt: INPUT drop for $BRIDGE already present"
        else
            as_root "$_ipt" -I INPUT 1 -i "$BRIDGE" -j DROP
            say "$_ipt: dropping traffic from $BRIDGE to this host"
            _applied=1
        fi
    done
    [ "$_applied" = 0 ] || true
}

rules_present() {
    have_root || return 2
    as_root iptables -C INPUT -i "$BRIDGE" -j DROP 2>/dev/null
}

start_proxy() {
    docker_ image inspect "$IMAGE" >/dev/null 2>&1 \
        || die "image $IMAGE is not built. Run: sh $HERE/../01-dockerSetup.sh  (or docker build -t $IMAGE $HERE)"
    [ -r "$ALLOWLIST" ] || die "cannot read $ALLOWLIST"

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
    apply_rules
    start_proxy
    printf '\n'
    skip "allowing: $(sed 's/#.*//' "$ALLOWLIST" | tr -d ' \t\r' | grep -v '^$' | tr '\n' ' ')"
    skip "runs join with: --network $NET --dns $IP"
}

cmd_down() {
    docker_ rm -f "$NAME" >/dev/null 2>&1 && say "$NAME removed" || skip "$NAME was not running"
    skip "networks and INPUT rules left in place — a half-removed fence is worse than none"
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
    if rules_present; then
        printf '  INPUT drop for %-11s present\n' "$BRIDGE"
    elif [ $? = 2 ]; then
        printf '  INPUT drop for %-11s unknown (needs root to read)\n' "$BRIDGE"
    else
        printf '  INPUT drop for %-11s MISSING — the container can reach this host\n' "$BRIDGE"
    fi
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
    rules)   apply_rules ;;
    -h|--help) sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//' ;;
    *)       die "unknown command '$1' (up|down|status|log|rules)" ;;
esac
