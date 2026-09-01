#!/bin/sh
# lib-workloads.sh — the ONE ceiling on containers, shared by the agent lane and the CI lane.
# SOURCED, never executed.
#
# WHY THIS EXISTS. Until 2026-08-31 the two lanes counted separately and neither could see the
# other: ffwatch enforced max_concurrent_runs over its own runs and its own pool, ffgithubrunners
# enforced `slots` over its runners, and the box got the sum. At the values that were live that
# was six CI jobs plus two agent runs plus a staged container -- nine workspaces of 22-24 GiB, on
# a machine with 755 GiB, and nothing anywhere that would have said no. design/
# ffbox_idle_agents_design.txt section 9 wrote the combined arithmetic down and then implemented
# only the agent half of it.
#
# It is a RESOURCE ceiling, not a licensing one. It counts every container that holds a workspace,
# whether or not that container has a Unity editor in it: a staged agent container that has been
# asked to do nothing at all still holds its 22 GiB tmpfs, and RAM is what runs out.
#
# WHERE THE DECISION LIVES, and this is the part worth being careful about. The count is only
# meaningful if nothing can create a container between reading it and acting on it, so admission
# belongs where the container is CREATED and nowhere else:
#
#     ffbox            every agent container -- a cold run, and a staged pool container
#     slot.sh          every CI runner container
#
# Both take the same lock across "count, then docker run". ffwatch keeps its own pre-check, but
# that one is a scheduling courtesy -- it stops the daemon launching something that would be
# refused -- and not the boundary. ffgithubrunners' own pool lock is unchanged and still decides
# how many of ITS slots may be busy; this is the ceiling above both of them.
#
# A DISPATCH IS NOT AN ADMISSION. Dispatching a turn into a staged container renames a container
# that already exists and already counts; it creates nothing, so it asks nothing of this file.
# That is also why the label has to survive the rename, and it does.
# shellcheck shell=sh

# Every container that holds a workspace carries this label. Infrastructure does not: the egress
# proxies and the git mirror are long-lived, hold no workspace, and must not be counted.
FFBOX_WORKLOAD_LABEL=${FFBOX_WORKLOAD_LABEL:-ffbox.workload}

FFBOX_WL_CONFIG_DIR=${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}
FFBOX_WL_CONFIG=${FFBOX_WL_CONFIG:-$FFBOX_WL_CONFIG_DIR/config.json}
FFBOX_WL_LOCK=${FFBOX_WL_LOCK:-$FFBOX_WL_CONFIG_DIR/.admission.lock}

# The default lives HERE and in ffwatch.py's DEFAULTS, and they have to agree. Two readers, one
# number: this file is what a shell reads and DEFAULTS is what the daemon reads, and there is no
# third place that gets to have an opinion.
FFBOX_WORKLOAD_DEFAULT_MAX=6

ffbox_wl_log() { printf '[workloads] %s\n' "$*" >&2; }

# The ceiling, from the ffbox config. NOT from ffgithubrunners' config: `slots` there is still that
# lane's own limit on how many of its slots may be busy, and this is the limit on the box.
#
# An unreadable or nonsense config gives the default rather than an error. A machine that cannot
# parse its config must still be able to run something; the alternative is a box that goes quiet
# because of a stray comma.
ffbox_workload_max() {
    _wl_max=$(python3 - "$FFBOX_WL_CONFIG" <<'PY' 2>/dev/null
import json, sys
try:
    with open(sys.argv[1]) as fh:
        v = json.load(fh).get("max_concurrent_runs")
    print(int(v) if v is not None and int(v) >= 1 else "")
except Exception:
    print("")
PY
)
    case "$_wl_max" in
        ''|*[!0-9]*) _wl_max=$FFBOX_WORKLOAD_DEFAULT_MAX ;;
    esac
    [ "$_wl_max" -ge 1 ] 2>/dev/null || _wl_max=$FFBOX_WORKLOAD_DEFAULT_MAX
    printf '%s\n' "$_wl_max"
    unset _wl_max
}

# How many workspace-holding containers exist right now, both lanes together.
#
# `docker ps` is the source of truth rather than any bookkeeping of our own, because it is the
# only one that cannot drift: a supervisor killed with SIGKILL leaves its container running and
# its records stale, and the container is what is still holding the RAM.
#
# A daemon that cannot be reached counts as FULL, not as empty. Every caller is about to start a
# container on that daemon, so a docker that does not answer is not a reason to start more.
ffbox_workload_count() {
    _wl_docker=${FFBOX_DOCKER:-docker}
    if _wl_out=$("$_wl_docker" ps -q --filter "label=$FFBOX_WORKLOAD_LABEL" 2>/dev/null); then
        # THE EMPTY CASE HAS TO BE ITS OWN BRANCH. `printf '%s\n' "" | grep -c .` prints 0 and
        # exits 1, so a `|| printf 0` fallback appends a SECOND zero and the caller gets "0\n0" --
        # not a number, so every `[ "$n" -lt ... ]` errors and the box refuses everything exactly
        # when it is empty. Found by testing an idle machine.
        if [ -z "$_wl_out" ]; then
            printf '0\n'
        else
            printf '%s\n' "$_wl_out" | grep -c .
        fi
    else
        ffbox_wl_log "WARNING: could not ask docker what is running; treating the box as full"
        ffbox_workload_max
    fi
    unset _wl_docker _wl_out
}

# Is there room for one more? Prints the reason when there is not, so every caller reports the
# same thing in the same words.
#
# CALL THIS WITH THE LOCK HELD -- ffbox_workload_lock_acquire below. On its own it is a question
# whose answer expires the moment it is given.
ffbox_workload_has_room() {
    _wl_have=$(ffbox_workload_count)
    _wl_want=$(ffbox_workload_max)
    if [ "$_wl_have" -lt "$_wl_want" ]; then
        unset _wl_have _wl_want
        return 0
    fi
    ffbox_wl_log "at the ceiling: $_wl_have of $_wl_want containers already hold a workspace"
    unset _wl_have _wl_want
    return 1
}

# --- the long-running case ----------------------------------------------------------------------
#
# ACQUIRE, DECIDE, CREATE, RELEASE -- as four steps rather than one call, because every creator
# here needs to do something between deciding and creating: claim a slot, derive the machine id
# from it, and record the container against it. A cold agent run also keeps its `docker run` in the
# foreground for the whole run, backgrounded so a clock loop can watch it, and a lock held that
# long would stop the other lane admitting anything for the length of a run.
#
# The caller releases as soon as the container EXISTS, not when it exits. The window the lock has
# to cover is "counted, but not yet visible to the next count", and that is all it covers.
#
# These use fd 9 in the CALLER's shell rather than a subshell, on purpose: a subshell cannot hand
# back the `$!` of a process the caller has to `wait` on.
ffbox_workload_lock_acquire() {
    mkdir -p "$FFBOX_WL_CONFIG_DIR" 2>/dev/null || :
    command -v flock >/dev/null 2>&1 || return 0     # no flock: no lock, same as admit()
    exec 9>>"$FFBOX_WL_LOCK" || return 1
    flock 9 || return 1
    return 0
}

ffbox_workload_lock_release() {
    command -v flock >/dev/null 2>&1 || return 0
    exec 9>&- 2>/dev/null || :
    return 0
}

# Wait until a container exists, so the next count can see it. Bounded, and it also gives up the
# moment the process that was starting it has gone -- a `docker run` that failed immediately is
# never going to produce a container and there is nothing to wait for.
ffbox_workload_await_container() {
    _wl_name=${1:?ffbox_workload_await_container needs a name}
    _wl_pid=${2:-}
    _wl_tries=${3:-30}
    _wl_docker=${FFBOX_DOCKER:-docker}
    while [ "$_wl_tries" -gt 0 ]; do
        if [ -n "$("$_wl_docker" ps -q --filter "name=^${_wl_name}$" 2>/dev/null)" ]; then
            break
        fi
        if [ -n "$_wl_pid" ] && ! kill -0 "$_wl_pid" 2>/dev/null; then
            break
        fi
        _wl_tries=$((_wl_tries - 1))
        sleep 0.5
    done
    unset _wl_name _wl_pid _wl_tries _wl_docker
    return 0
}

# --- agent slots, and the Unity machine id they name ---------------------------------------------
#
# WHY THE AGENT LANE NEEDS A NUMBER AT ALL. Unity's licensing service identifies a machine by
# /etc/machine-id, and game-ci's base image pins that to one constant for every container built from
# it. That pin is right for a .ulf licence FILE, which is bound to a machine; it is wrong for the
# personal SERIAL activation this project does, where two containers presenting the same id are ONE
# machine holding ONE entitlement and the second concurrent activation dies with "Found 0
# entitlement groups and 0 free entitlements", exit 198. ffgithubrunners measured that on
# 2026-08-29 and fixed it per slot. The agent lane never did, and it does take a seat: whenever a
# turn verifies (discord-task.sh's verify block) and on every plain `ffbox` run (run-as-user.sh).
# At two concurrent runs the window was narrow enough never to have bitten. At six it is not.
#
# PER SLOT AND NOT PER CONTAINER, which is where this deliberately parts company with game-ci's
# `dbus-uuidgen`. An activation registers a machine and only -returnlicense gives it back, so a
# container that is SIGKILLed leaks one: with a random id per container every leak is permanent,
# because that machine never comes back, while an id derived from a small recycled set bounds the
# registrations and lets the next container on that number reuse the entitlement.
#
# THE TWO LANES CANNOT COLLIDE, and it costs nothing to be sure of it: ffgithubrunners derives from
# 'ffghr-<host>-slot-<n>' and this derives from 'ffbox-<host>-agent-<n>'. Different strings, so
# agent 2 and CI slot 2 are different machines, and neither lane has to know the other's numbering.
FFBOX_SLOT_DIR=${FFBOX_SLOT_DIR:-$FFBOX_WL_CONFIG_DIR/slots}

ffbox_agent_machine_id() {
    _wl_n=${1:?ffbox_agent_machine_id needs a slot}
    _wl_host=$(hostname -s 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo host)
    printf 'ffbox-%s-agent-%s' "$_wl_host" "$_wl_n" | sha256sum | cut -c1-32
    unset _wl_n _wl_host
}

# A claim is a file naming the container that holds the number. THE FILE IS NOT THE TRUTH -- the
# container is. A number is free when its file is absent OR when the thing the file names is gone,
# which is the same rule ffgithubrunners applies to its busy markers and for the same reason:
#
#     THE MARKER IS ONLY EVER TRUSTED FOR A CONTAINER THAT IS STILL RUNNING, which is what makes
#     a stale one harmless in both directions.
#
# That is what makes this survive a SIGKILL with no reaper and no lock held for the length of a
# run. It matters most for a STAGED container, which nothing outlives: `ffbox --stage-pool` starts
# it detached and returns, so there is no process anywhere that could hold a lock on its behalf.
#
# THE FILE HOLDS AN ID ONCE THERE IS ONE, not a name, because `docker rename` moves the name and
# dispatch renames every pooled container to its run. An id does not move.
ffbox_slot_claim_file() { printf '%s/agent-%s\n' "$FFBOX_SLOT_DIR" "${1:?}"; }

# Claim the lowest free number for a container about to be created, or return 1.
# CALL THIS WITH THE ADMISSION LOCK HELD: choosing a number and creating the container that holds
# it must be one act, or two creators pick the same one.
ffbox_agent_slot_claim() {
    _wl_for=${1:?ffbox_agent_slot_claim needs the container name}
    _wl_docker=${FFBOX_DOCKER:-docker}
    mkdir -p "$FFBOX_SLOT_DIR" 2>/dev/null || :
    # One listing for the whole scan: ids and names of everything running, ours or not.
    _wl_live=$( { "$_wl_docker" ps -q --no-trunc; "$_wl_docker" ps --format '{{.Names}}'; } \
                2>/dev/null | tr '\n' ' ')
    _wl_max=$(ffbox_workload_max)
    _wl_i=1
    while [ "$_wl_i" -le "$_wl_max" ]; do
        _wl_f=$(ffbox_slot_claim_file "$_wl_i")
        if [ ! -e "$_wl_f" ]; then
            printf '%s\n' "$_wl_for" > "$_wl_f" && { printf '%s\n' "$_wl_i"; \
                unset _wl_for _wl_docker _wl_live _wl_max _wl_i _wl_f; return 0; }
        else
            _wl_held=$(cat "$_wl_f" 2>/dev/null)
            case " $_wl_live " in
                *" $_wl_held "*) : ;;   # still held by something that is running
                *)
                    # Stale: whatever held it is gone, so the number and its entitlement come back.
                    printf '%s\n' "$_wl_for" > "$_wl_f" && { printf '%s\n' "$_wl_i"; \
                        unset _wl_for _wl_docker _wl_live _wl_max _wl_i _wl_f _wl_held; return 0; } ;;
            esac
        fi
        _wl_i=$((_wl_i + 1))
    done
    unset _wl_for _wl_docker _wl_live _wl_max _wl_i _wl_f _wl_held
    return 1
}

# Record the container's ID against a claim, once docker has told us what it is. Best effort: a
# claim still holding a NAME is only wrong after a rename, and the next scan treats it as stale,
# which costs a recycled number rather than a collision.
ffbox_agent_slot_confirm() {
    _wl_n=${1:?}; _wl_id=${2:-}
    [ -n "$_wl_id" ] || { unset _wl_n _wl_id; return 0; }
    printf '%s\n' "$_wl_id" > "$(ffbox_slot_claim_file "$_wl_n")" 2>/dev/null || :
    unset _wl_n _wl_id
    return 0
}

# Hand a number back the moment a creation fails, rather than leaving it claimed by a container
# that never existed. The scan would recycle it anyway; this just does not make the next caller
# wait for that.
ffbox_agent_slot_release() {
    [ -n "${1:-}" ] || return 0
    rm -f "$(ffbox_slot_claim_file "$1")" 2>/dev/null || :
    return 0
}
