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
# CALL THIS WITH THE LOCK HELD. On its own it is a question whose answer expires immediately;
# ffbox_workload_admit below is the one that is safe to act on.
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

# Run a command that creates ONE container, under the shared lock, if there is room for it.
#
#     ffbox_workload_admit agent docker run -d --label ffbox.workload=agent ...
#
# Returns the command's own status, or 77 when the box is full and the command was not run. 77
# rather than 1 so a caller can tell "no room" from "docker failed", which are different things to
# a scheduler: one is worth retrying in a moment and the other is not.
#
# THE LOCK IS HELD ACROSS THE CREATE, which is the whole point -- see the header. It is released
# the moment docker returns, NOT when the container exits: every creator here starts a container
# that outlives the command (`-d`, or a backgrounded foreground run), so the lock covers the gap
# between counting and the container existing to be counted, and nothing longer.
#
# flock releases on process death, so a creator that is SIGKILLed mid-admission does not wedge the
# other lane. That is why this is a lock file and not a marker file with a reaper.
ffbox_workload_admit() {
    _wl_kind=${1:?ffbox_workload_admit needs a kind}
    shift
    mkdir -p "$FFBOX_WL_CONFIG_DIR" 2>/dev/null || :
    if ! command -v flock >/dev/null 2>&1; then
        # Not fatal and loud about it. A box without flock still runs; it just cannot promise the
        # two lanes will not both admit the last place at the same instant.
        ffbox_wl_log "WARNING: no flock; admitting $_wl_kind without the shared lock"
        ffbox_workload_has_room || { unset _wl_kind; return 77; }
        "$@"
        return $?
    fi
    (
        flock 9 || exit 76
        ffbox_workload_has_room || exit 77
        "$@"
    ) 9>>"$FFBOX_WL_LOCK"
    _wl_rc=$?
    if [ "$_wl_rc" -eq 76 ]; then
        ffbox_wl_log "WARNING: could not take $FFBOX_WL_LOCK; refusing rather than overshooting"
        _wl_rc=77
    fi
    unset _wl_kind
    return $_wl_rc
}

# --- the long-running case ----------------------------------------------------------------------
#
# ffbox_workload_admit above runs a command and returns, which fits `docker run -d`. A COLD AGENT
# RUN does not: its `docker run` stays in the foreground for the whole run, backgrounded by the
# caller so a clock loop can watch it, and holding the lock for that long would stop the other lane
# admitting anything for the length of a run.
#
# So the three steps are separate here, and the caller releases as soon as the container EXISTS
# rather than when it exits. The window the lock has to cover is "counted, but not yet visible to
# the next count", and that is all it covers.
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
