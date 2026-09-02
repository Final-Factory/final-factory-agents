#!/usr/bin/env bash
#
# ffstatus.sh — what is running on this box right now, and what the pools are trying to hold.
#
# A read-only operator view. It answers the two questions you ask when something looks wrong:
# WHICH containers hold a workspace (both lanes -- agent runs, staged spares, CI jobs), and IS
# EACH POOL AT THE SIZE IT WAS CONFIGURED FOR (idle, max, and the box-wide ceiling above both).
#
#   ffbox/ffstatus.sh            the tables
#   ffbox/ffstatus.sh --watch    refresh every 5s until ^C
#
# TWO SOURCES, AND NEITHER IS BOOKKEEPING. Live state comes from `docker ps` on the ffbox daemon
# for the same reason lib-workloads.sh counts there: a supervisor killed with SIGKILL leaves its
# container running and its records stale, and the container is what still holds the RAM. Wanted
# state comes from ~/.config/ffbox/config.json, read with the same coercions ffwatch's load_config
# applies (pool.idle/pool.max, a negative max meaning "no ceiling of my own" -> max_concurrent_runs)
# so this cannot report a target the daemon is not actually working towards.
#
# A DISPATCHED SPARE STILL CARRIES ffbox.workload=pool -- labels are fixed when a container is
# created and dispatch only renames it -- so the lane here is read from the label AND the name:
# `*-pool-*` is a spare waiting, anything else with that label is a turn that started warm.
set -uo pipefail

DOCKER_HOST=${DOCKER_HOST:-unix://${FFBOX_DOCKER_SOCK:-/run/ffbox-container/docker.sock}}
export DOCKER_HOST
DOCKER=${FFBOX_DOCKER:-docker}
CONFIG=${FFBOX_CONFIG_JSON:-${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}/config.json}
POOL_DIR=${FFBOX_POOL_DIR:-$HOME/ffbox-state/pool}
# WHERE THE CI LANE SAYS A RUNNER IS BUSY. ffgithubrunners keeps $SLOTS supervisors up but
# only mints a CONTAINER when the pool needs one -- $IDLE_POOL runners registered and
# waiting, plus one per job in flight -- so an idle CI runner is a running container in
# exactly the way an agent spare is, and `docker ps` alone cannot tell the two apart. The
# marker is what does: written by the supervisor that owns the container when its runner
# takes a job. Trusted only for a container that is still running, which is automatic here
# because the names come from `docker ps` -- a leftover marker names nothing we listed.
FFGHR_STATE=${FFGITHUBRUNNERS_CONFIG_DIR:-${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}/githubrunners}/state

WATCH=0
INTERVAL=5
while [ $# -gt 0 ]; do
    case "$1" in
        -w|--watch) WATCH=1; shift; case "${1:-}" in ''|-*) ;; *) INTERVAL=$1; shift ;; esac ;;
        -h|--help)
            sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "ffstatus: unknown option $1" >&2; exit 2 ;;
    esac
done

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    B=$'\033[1m'; DIM=$'\033[2m'; GRN=$'\033[32m'; YEL=$'\033[33m'; RED=$'\033[31m'; N=$'\033[0m'
else
    B=; DIM=; GRN=; YEL=; RED=; N=
fi

# --- wanted state -------------------------------------------------------------------------------
#
# The defaults here are ffwatch.py's DEFAULTS and lib-workloads.sh's FFBOX_WORKLOAD_DEFAULT_MAX.
# A box with no config file must still show the numbers it is actually running under.
read_config() {
    python3 - "$CONFIG" <<'PY' 2>/dev/null
import json, sys

try:
    with open(sys.argv[1]) as fh:
        cfg = json.load(fh)
except Exception:
    cfg = {}

def num(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default

box = max(1, num(cfg.get("max_concurrent_runs"), 6))
print("box_max=%d" % box)

# (class, default idle, default max) -- ffwatch's per-class DEFAULTS, written out rather than
# derived, for the same reason they are written out there: the classes exist to diverge.
for cls, d_idle, d_max in (("ffagent", 1, -1), ("ffdev", 1, 3)):
    block = cfg.get(cls) or {}
    pool = block.get("pool") or {}
    idle = max(0, num(pool.get("idle"), d_idle))
    cap = num(pool.get("max"), d_max)
    print("%s_idle=%d" % (cls, idle))
    # A negative max means "no ceiling of my own" and is read as max_concurrent_runs, exactly as
    # ffwatch's load_config coerces it -- so the number printed is the one actually enforced.
    print("%s_max=%d" % (cls, box if cap < 0 else cap))
    print("%s_ref=%s" % (cls, block.get("pool_ref") or block.get("base_ref") or "master"))
    print("%s_net=%s" % (cls, block.get("network") or ("bridge" if cls == "ffdev" else "ffbox-net")))

ci = (cfg.get("githubrunner") or {}).get("pool") or {}
print("ci_idle=%d" % max(0, num(ci.get("idle"), 1)))
print("ci_max=%d" % max(0, num(ci.get("max"), 1)))
PY
}

declare -A CFG=()
while IFS='=' read -r _k _v; do
    [ -n "$_k" ] && CFG["$_k"]=$_v
done < <(read_config)
# An unreadable config is not a reason to print nothing: fall back to the same built-ins.
: "${CFG[box_max]:=6}"
for _c in ffagent ffdev; do
    : "${CFG[${_c}_idle]:=1}"; : "${CFG[${_c}_max]:=${CFG[box_max]}}"
    : "${CFG[${_c}_ref]:=master}"
done
: "${CFG[ci_idle]:=1}"; : "${CFG[ci_max]:=1}"

human_secs() {
    local s=${1:-0}
    if [ "$s" -lt 0 ]; then printf 'expired'; return; fi
    if [ "$s" -ge 3600 ]; then printf '%dh%02dm' $((s / 3600)) $(((s % 3600) / 60))
    elif [ "$s" -ge 60 ]; then printf '%dm' $((s / 60))
    else printf '%ds' "$s"; fi
}

render() {
    local now; now=$(date +%s)

    local ps
    if ! ps=$("$DOCKER" ps --format \
        '{{.Names}}|{{.Label "ffbox.workload"}}|{{.Label "ffbox.agent.class"}}|{{.Label "ffbox.pool"}}|{{.Label "ffbox.pool.id"}}|{{.Label "ffbox.slot"}}|{{.RunningFor}}|{{.Status}}' \
        2>/dev/null); then
        printf '%sffstatus: could not reach the ffbox daemon at %s%s\n' "$RED" "$DOCKER_HOST" "$N" >&2
        return 1
    fi

    # rows[] is what gets printed; the counters beside it are what the pool table reports.
    local -a rows=() infra=()
    local -A spares=() runs=()
    local ci_busy=0 ci_waiting=0 workloads=0 widest=4

    local name workload class ref poolid slot age status
    while IFS='|' read -r name workload class ref poolid slot age status; do
        [ -n "$name" ] || continue
        age=${age% ago}
        if [ -z "$workload" ]; then
            infra+=("$name|$status")
            continue
        fi
        workloads=$((workloads + 1))
        [ ${#name} -gt "$widest" ] && widest=${#name}

        local lane state ttl
        ttl='-'
        case "$workload" in
            ci)
                lane=ci; class='-'; ref='-'
                if [ -e "$FFGHR_STATE/$name.busy" ]; then
                    state=busy; ci_busy=$((ci_busy + 1))
                else
                    state=waiting; ci_waiting=$((ci_waiting + 1))
                fi ;;
            pool)
                case "$name" in
                    *-pool-*)
                        # A spare, still waiting. Its own out/ says how far it got: `staged` is
                        # written once the workspace is filled, `owner` once the host has claimed
                        # it (or the container has decided to retire).
                        lane=spare
                        spares[$class]=$(( ${spares[$class]:-0} + 1 ))
                        local out="$POOL_DIR/$poolid/out"
                        if [ -e "$out/staged" ]; then
                            state=warm
                            local staged_at ttl_secs
                            staged_at=$(sed -n 's/^staged_at=//p' "$out/staged" 2>/dev/null)
                            ttl_secs=$(sed -n 's/^ttl_secs=//p' "$out/staged" 2>/dev/null)
                            if [ -n "$staged_at" ] && [ -n "$ttl_secs" ]; then
                                local t0
                                t0=$(date -d "$staged_at" +%s 2>/dev/null) &&
                                    ttl=$(human_secs $((t0 + ttl_secs - now)))
                            fi
                        else
                            state=filling
                        fi
                        [ -e "$out/owner" ] && state=claimed ;;
                    *)
                        # Renamed by dispatch: a turn that started from a warm workspace.
                        lane=agent; state='running*'
                        ref='-'
                        runs[$class]=$(( ${runs[$class]:-0} + 1 )) ;;
                esac ;;
            agent)
                lane=agent; state=running; ref='-'
                runs[$class]=$(( ${runs[$class]:-0} + 1 )) ;;
            *)
                lane=$workload; state=running; ref='-' ;;
        esac
        [ -n "$class" ] || class='-'
        [ -n "$ref" ] || ref='-'
        [ -n "$slot" ] || slot='-'
        rows+=("$lane|$class|$name|$slot|$state|$ttl|$ref|$age")
    done <<< "$ps"

    printf '\n%sffbox on %s%s  %s%s%s\n' "$B" "$(hostname -s)" "$N" "$DIM" "$(date '+%Y-%m-%d %H:%M:%S')" "$N"

    # --- containers ------------------------------------------------------------------------
    local box_max=${CFG[box_max]} colour=$GRN
    [ "$workloads" -ge "$box_max" ] && colour=$RED
    printf '\n%sCONTAINERS%s  %s%d of %d workspace containers%s\n\n' \
        "$B" "$N" "$colour" "$workloads" "$box_max" "$N"

    if [ ${#rows[@]} -eq 0 ]; then
        printf '  %s(none — the box is idle)%s\n' "$DIM" "$N"
    else
        printf "  %s%-6s %-8s %-${widest}s %-5s %-9s %-7s %-7s %s%s\n" \
            "$DIM" LANE CLASS NAME SLOT STATE TTL REF UP "$N"
        # spares last: a run is what you are usually looking for.
        printf '%s\n' "${rows[@]}" | sort -t'|' -k1,1 | while IFS='|' read -r l c n s st t r a; do
            local mark=$N
            case "$st" in
                warm|waiting) mark=$GRN ;;
                filling)      mark=$YEL ;;
                claimed)      mark=$YEL ;;
            esac
            printf "  %-6s %-8s %-${widest}s %-5s ${mark}%-9s${N} %-7s %-7s %s\n" \
                "$l" "$c" "$n" "$s" "$st" "$t" "$r" "$a"
        done
    fi

    # --- pools -----------------------------------------------------------------------------
    printf '\n%sPOOLS%s\n\n' "$B" "$N"
    # ONE VOCABULARY FOR BOTH LANES, because they hold the same kind of thing under two names:
    # an agent `spare` and an idle CI runner are both a container waiting for work, and both were
    # printed as RUNNING here until 2026-09-02 -- which made a CI pool that was doing exactly what
    # it was configured to do look like it had lost its idle runner.
    printf '  %s%-10s %-6s %-9s %-6s %s%s\n' "$DIM" CLASS IDLE WAITING BUSY MAX "$N"
    local cls
    for cls in ffagent ffdev; do
        local want=${CFG[${cls}_idle]} have=${spares[$cls]:-0} busy=${runs[$cls]:-0}
        local cap=${CFG[${cls}_max]}
        local mark=$GRN
        [ "$have" -lt "$want" ] && mark=$YEL
        printf '  %-10s %-6s %s%-9s%s %-6s %s\n' \
            "$cls" "$want" "$mark" "$have" "$N" "$busy" "$cap"
    done
    local ci_mark=$GRN
    [ "$ci_waiting" -lt "${CFG[ci_idle]}" ] && ci_mark=$YEL
    printf '  %-10s %-6s %s%-9s%s %-6s %s\n' \
        ci "${CFG[ci_idle]}" "$ci_mark" "$ci_waiting" "$N" "$ci_busy" "${CFG[ci_max]}"

    # --- infrastructure --------------------------------------------------------------------
    if [ ${#infra[@]} -gt 0 ]; then
        printf '\n%sINFRASTRUCTURE%s %s(holds no workspace, counts against nothing)%s\n\n' \
            "$B" "$N" "$DIM" "$N"
        printf '%s\n' "${infra[@]}" | sort | while IFS='|' read -r n s; do
            printf '  %-28s %s%s%s\n' "$n" "$DIM" "$s" "$N"
        done
    fi
    printf '\n'
}

if [ "$WATCH" -eq 1 ]; then
    while :; do
        clear
        render || exit 1
        sleep "$INTERVAL"
    done
else
    render
fi
