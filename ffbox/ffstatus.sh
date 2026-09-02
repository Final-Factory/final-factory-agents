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
#   ffbox/ffstatus.sh --json     the same reading as one JSON document
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
#
# --json EXISTS SO THERE IS ONE READING OF THE BOX AND NOT TWO. ffweb's /status page runs this
# script rather than growing its own docker parsing beside it: the two would agree on the day
# they were written and drift the first time a label moved, and the version an operator trusts
# would be whichever one they happened to be looking at. Everything below gathers once and then
# renders twice, so the page and the terminal cannot disagree by construction.
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

# US, THE UNIT SEPARATOR, RATHER THAN A PIPE. Every field here is a name somebody else chose --
# a container name, a git ref off a label -- and a ref may legally contain most punctuation. A
# separator that cannot appear in the data is one class of mangling that simply cannot happen,
# and it costs one variable.
SEP=$'\x1f'

WATCH=0
INTERVAL=5
JSON=0
while [ $# -gt 0 ]; do
    case "$1" in
        -w|--watch) WATCH=1; shift; case "${1:-}" in ''|-*) ;; *) INTERVAL=$1; shift ;; esac ;;
        -j|--json)  JSON=1; shift ;;
        -h|--help)
            sed -n '3,11p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "ffstatus: unknown option $1" >&2; exit 2 ;;
    esac
done
# A document is a document; there is nothing to redraw. Said rather than silently ignored,
# because a caller that asked for both wanted something this cannot give them.
[ "$JSON" -eq 1 ] && WATCH=0

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "$JSON" -eq 0 ]; then
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

# --- gather -------------------------------------------------------------------------------------
#
# ONE PASS OVER THE BOX, into globals both renderers read. A record carries the TTL in seconds
# rather than as "3h47m", because a number is what a renderer can decide how to say -- the
# terminal wants the short form and a JSON consumer wants the number.
declare -a ROWS=() INFRA=()
declare -A SPARES=() RUNS=()
CI_BUSY=0 CI_WAITING=0 WORKLOADS=0 WIDEST=4 GATHER_ERR=

gather() {
    local now; now=$(date +%s)
    ROWS=(); INFRA=(); SPARES=(); RUNS=()
    CI_BUSY=0; CI_WAITING=0; WORKLOADS=0; WIDEST=4; GATHER_ERR=

    local fmt="{{.Names}}${SEP}{{.Label \"ffbox.workload\"}}${SEP}{{.Label \"ffbox.agent.class\"}}"
    fmt+="${SEP}{{.Label \"ffbox.pool\"}}${SEP}{{.Label \"ffbox.pool.id\"}}"
    fmt+="${SEP}{{.Label \"ffbox.slot\"}}${SEP}{{.RunningFor}}${SEP}{{.Status}}"

    local ps
    if ! ps=$("$DOCKER" ps --format "$fmt" 2>/dev/null); then
        GATHER_ERR="could not reach the ffbox daemon at $DOCKER_HOST"
        return 1
    fi

    local name workload class ref poolid slot age status
    while IFS="$SEP" read -r name workload class ref poolid slot age status; do
        [ -n "$name" ] || continue
        age=${age% ago}
        if [ -z "$workload" ]; then
            INFRA+=("$name$SEP$status")
            continue
        fi
        WORKLOADS=$((WORKLOADS + 1))
        [ ${#name} -gt "$WIDEST" ] && WIDEST=${#name}

        local lane state ttl
        ttl=''
        case "$workload" in
            ci)
                lane=ci; class=''; ref=''
                if [ -e "$FFGHR_STATE/$name.busy" ]; then
                    state=busy; CI_BUSY=$((CI_BUSY + 1))
                else
                    state=waiting; CI_WAITING=$((CI_WAITING + 1))
                fi ;;
            pool)
                case "$name" in
                    *-pool-*)
                        # A spare, still waiting. Its own out/ says how far it got: `staged` is
                        # written once the workspace is filled, `owner` once the host has claimed
                        # it (or the container has decided to retire).
                        lane=spare
                        SPARES[$class]=$(( ${SPARES[$class]:-0} + 1 ))
                        local out="$POOL_DIR/$poolid/out"
                        if [ -e "$out/staged" ]; then
                            state=warm
                            local staged_at ttl_secs t0
                            staged_at=$(sed -n 's/^staged_at=//p' "$out/staged" 2>/dev/null)
                            ttl_secs=$(sed -n 's/^ttl_secs=//p' "$out/staged" 2>/dev/null)
                            if [ -n "$staged_at" ] && [ -n "$ttl_secs" ]; then
                                t0=$(date -d "$staged_at" +%s 2>/dev/null) &&
                                    ttl=$(( t0 + ttl_secs - now ))
                            fi
                        else
                            state=filling
                        fi
                        [ -e "$out/owner" ] && state=claimed ;;
                    *)
                        # Renamed by dispatch: a turn that started from a warm workspace.
                        lane=agent; state='running*'; ref=''
                        RUNS[$class]=$(( ${RUNS[$class]:-0} + 1 )) ;;
                esac ;;
            agent)
                lane=agent; state=running; ref=''
                RUNS[$class]=$(( ${RUNS[$class]:-0} + 1 )) ;;
            *)
                lane=$workload; state=running; ref='' ;;
        esac
        ROWS+=("$lane$SEP$class$SEP$name$SEP$slot$SEP$state$SEP$ttl$SEP$ref$SEP$age")
    done <<< "$ps"
    return 0
}

# --- the terminal reading -------------------------------------------------------------------
render_text() {
    printf '\n%sffbox on %s%s  %s%s%s\n' "$B" "$(hostname -s)" "$N" "$DIM" "$(date '+%Y-%m-%d %H:%M:%S')" "$N"

    local box_max=${CFG[box_max]} colour=$GRN
    [ "$WORKLOADS" -ge "$box_max" ] && colour=$RED
    printf '\n%sCONTAINERS%s  %s%d of %d workspace containers%s\n\n' \
        "$B" "$N" "$colour" "$WORKLOADS" "$box_max" "$N"

    if [ ${#ROWS[@]} -eq 0 ]; then
        printf '  %s(none — the box is idle)%s\n' "$DIM" "$N"
    else
        printf "  %s%-6s %-8s %-${WIDEST}s %-5s %-9s %-7s %-7s %s%s\n" \
            "$DIM" LANE CLASS NAME SLOT STATE TTL REF UP "$N"
        # spares last: a run is what you are usually looking for.
        printf '%s\n' "${ROWS[@]}" | sort -t"$SEP" -k1,1 |
        while IFS="$SEP" read -r l c n s st t r a; do
            local mark=$N
            case "$st" in
                warm|waiting) mark=$GRN ;;
                filling)      mark=$YEL ;;
                claimed)      mark=$YEL ;;
            esac
            [ -n "$t" ] && t=$(human_secs "$t")
            printf "  %-6s %-8s %-${WIDEST}s %-5s ${mark}%-9s${N} %-7s %-7s %s\n" \
                "$l" "${c:--}" "$n" "${s:--}" "$st" "${t:--}" "${r:--}" "$a"
        done
    fi

    printf '\n%sPOOLS%s\n\n' "$B" "$N"
    # ONE VOCABULARY FOR BOTH LANES, because they hold the same kind of thing under two names:
    # an agent `spare` and an idle CI runner are both a container waiting for work, and both were
    # printed as RUNNING here until 2026-09-02 -- which made a CI pool that was doing exactly what
    # it was configured to do look like it had lost its idle runner.
    printf '  %s%-10s %-6s %-9s %-6s %s%s\n' "$DIM" CLASS IDLE WAITING BUSY MAX "$N"
    local cls
    for cls in ffagent ffdev; do
        local want=${CFG[${cls}_idle]} have=${SPARES[$cls]:-0} busy=${RUNS[$cls]:-0}
        local mark=$GRN
        [ "$have" -lt "$want" ] && mark=$YEL
        printf '  %-10s %-6s %s%-9s%s %-6s %s\n' \
            "$cls" "$want" "$mark" "$have" "$N" "$busy" "${CFG[${cls}_max]}"
    done
    local ci_mark=$GRN
    [ "$CI_WAITING" -lt "${CFG[ci_idle]}" ] && ci_mark=$YEL
    printf '  %-10s %-6s %s%-9s%s %-6s %s\n' \
        ci "${CFG[ci_idle]}" "$ci_mark" "$CI_WAITING" "$N" "$CI_BUSY" "${CFG[ci_max]}"

    if [ ${#INFRA[@]} -gt 0 ]; then
        printf '\n%sINFRASTRUCTURE%s %s(holds no workspace, counts against nothing)%s\n\n' \
            "$B" "$N" "$DIM" "$N"
        printf '%s\n' "${INFRA[@]}" | sort | while IFS="$SEP" read -r n s; do
            printf '  %-28s %s%s%s\n' "$n" "$DIM" "$s" "$N"
        done
    fi
    printf '\n'
}

# --- the same reading, as a document ----------------------------------------------------------
#
# TAGGED RECORDS INTO PYTHON, which does the quoting. Building JSON in shell means escaping
# strings a stranger named -- a container name, a branch, a docker status line -- and getting
# that subtly wrong is how a page ends up with broken markup or worse. json.dumps is right by
# construction, so the shell's only job is to hand over fields it has already separated.
render_json() {
    {
        printf 'B%s%s%s%s\n' "$SEP" "$WORKLOADS" "$SEP" "${CFG[box_max]}"
        local cls
        for cls in ffagent ffdev; do
            printf 'P%s%s%s%s%s%s%s%s%s%s\n' "$SEP" "$cls" \
                "$SEP" "${CFG[${cls}_idle]}" "$SEP" "${SPARES[$cls]:-0}" \
                "$SEP" "${RUNS[$cls]:-0}" "$SEP" "${CFG[${cls}_max]}"
        done
        printf 'P%s%s%s%s%s%s%s%s%s%s\n' "$SEP" ci \
            "$SEP" "${CFG[ci_idle]}" "$SEP" "$CI_WAITING" \
            "$SEP" "$CI_BUSY" "$SEP" "${CFG[ci_max]}"
        [ ${#ROWS[@]} -gt 0 ] && printf "C$SEP%s\n" "${ROWS[@]}"
        [ ${#INFRA[@]} -gt 0 ] && printf "I$SEP%s\n" "${INFRA[@]}"
    # THE PROGRAM COMES IN AS AN ARGUMENT, NOT ON STDIN. `python3 - <<PY` puts the heredoc on
    # stdin, which is where the interpreter reads the program from -- so the records piped in
    # from the block above were thrown away and this rendered an empty document that looked
    # exactly like an idle box. -c leaves stdin to the pipe, which is the whole point of it here.
    } | python3 -c '
import json, sys

SEP = "\x1f"
doc = {"host": sys.argv[1], "generated_at": sys.argv[2],
       "box": {"used": 0, "max": 0}, "pools": [], "containers": [], "infrastructure": []}

def num(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None

for line in sys.stdin.read().splitlines():
    if not line:
        continue
    tag, _, rest = line.partition(SEP)
    f = rest.split(SEP)
    if tag == "B":
        doc["box"] = {"used": num(f[0]), "max": num(f[1])}
    elif tag == "P":
        doc["pools"].append({"class": f[0], "idle": num(f[1]), "waiting": num(f[2]),
                             "busy": num(f[3]), "max": num(f[4])})
    elif tag == "C":
        doc["containers"].append({
            "lane": f[0], "class": f[1] or None, "name": f[2], "slot": f[3] or None,
            "state": f[4], "ttl_secs": num(f[5]), "ref": f[6] or None, "uptime": f[7]})
    elif tag == "I":
        doc["infrastructure"].append({"name": f[0], "status": f[1]})

json.dump(doc, sys.stdout, indent=2, sort_keys=False)
sys.stdout.write("\n")
' "$(hostname -s)" "$(date -Is)"
}

# --- and what a failure looks like in each ------------------------------------------------------
#
# A CONSUMER MUST NOT HAVE TO GUESS. The terminal gets the sentence on stderr and a non-zero
# status; --json gets a document with an `error` key and the same status, so ffweb can say what
# went wrong on the page rather than rendering an empty table that looks like an idle box.
fail() {
    if [ "$JSON" -eq 1 ]; then
        python3 -c 'import json,sys; json.dump({"error": sys.argv[1]}, sys.stdout); print()' \
            "$GATHER_ERR"
    else
        printf '%sffstatus: %s%s\n' "$RED" "$GATHER_ERR" "$N" >&2
    fi
    exit 1
}

if [ "$WATCH" -eq 1 ]; then
    while :; do
        clear
        gather || fail
        render_text
        sleep "$INTERVAL"
    done
else
    gather || fail
    # if/else rather than `a && b || c`: a render_json that failed would fall through to
    # render_text and print a table after the document.
    if [ "$JSON" -eq 1 ]; then render_json; else render_text; fi
fi
