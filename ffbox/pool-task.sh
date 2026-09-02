#!/usr/bin/env bash
#
# ffbox's POOL task: fill the workspace before anybody has asked for anything, wait for a
# request, then become an ordinary turn. Invoked by entrypoint.sh as PID 1 when ffbox is called
# with --stage-pool; not meant to be run directly.
#
# WHY THIS EXISTS. Measured on 2026-08-31, from ffwatch writing job.json to the container writing
# .agent-started: 40 and 41 seconds on two consecutive turns, out of a 71-second answer. Almost
# none of it is the model. It is `docker run`, a 22 GiB tar onto a fresh tmpfs, a recursive chown
# over 89,664 files and a fetch from the mirror -- all of which can happen before the request
# exists, because none of it depends on what was asked.
#
# WHAT DOES NOT CHANGE. One prompt per container, still: this script waits once, hands over once,
# and the container is destroyed after. Nothing a run wrote is ever seen by a later run, the
# workspace is still a tmpfs the host cannot see, and the turn that eventually runs here is the
# same discord-task.sh with the same job.json that a cold run gets.
#
# HOW A JOB REACHES A CONTAINER THAT IS ALREADY RUNNING. A container's mounts are fixed when it
# is created, and every per-turn input is normally a mount. So staging creates a directory for
# this container on the host and mounts it empty:
#
#   /ffbox/in      READ-ONLY to us, written by the host at dispatch: job.json, prompt.txt,
#                  attachments/, env, and `dispatch` last of all
#   /ffbox/out     ours, and the only thing that outlives the container
#
# Read-only is the container's view, not the host's, which is the whole trick: the host goes on
# writing into a directory this container cannot alter.
#
# design/ffbox_idle_agents_design.txt sections 3 and 7.
#
# No `set -e`: a staged container that dies on an unchecked command is a container the host waits
# on for nothing. Everything here is checked.
set -uo pipefail

WORKSPACE=${FFBOX_WORKSPACE:-/opt/actions-runner/_work/FinalFactory/FinalFactory}
FFBOX_OUT=${FFBOX_OUT:-/ffbox/out}
FFBOX_IN=${FFBOX_IN:-/ffbox/in}
TURN_TASK=${FFBOX_TURN_TASK:-/ffbox/turn-task.sh}
# Four hours by default, and the host decides: it is passed in at stage time, so the deadline a
# container enforces is the one that was configured when it was staged.
TTL=${FFBOX_IDLE_TTL_SECS:-14400}
POLL=${FFBOX_POOL_POLL_SECS:-1}

log() { printf '[pool] %s\n' "$*"; }
die() { printf '[pool] ERROR: %s\n' "$*" >&2; exit 1; }

export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=safe.directory
export GIT_CONFIG_VALUE_0="$WORKSPACE"

# --- staged ------------------------------------------------------------------------------------
#
# entrypoint.sh already did the expensive half: it ran restore-workspace.sh as root, before
# dropping privilege, exactly as it does for a cold run. There is deliberately nothing to do here
# but record what came out of it, so that staging and a cold start cannot diverge.
[ -d "$WORKSPACE/.git" ] || die "nothing was restored into $WORKSPACE"
staged_at=$(git -C "$WORKSPACE" rev-parse HEAD 2>/dev/null || echo "")
[ -n "$staged_at" ] || die "the restored workspace has no HEAD"

{
    printf 'commit=%s\n' "$staged_at"
    printf 'entry=%s\n' "$(basename "${FFBOX_CACHE_ENTRY:-unknown}")"
    printf 'ref=%s\n' "${FFBOX_REF:-}"
    printf 'staged_at=%s\n' "$(date -Is)"
    printf 'ttl_secs=%s\n' "$TTL"
} > "$FFBOX_OUT/staged"
# The last two keys are lib-workloads.sh's clock format, and the host reads them with
# ffbox_clock_left: the keeper to decide this container has aged out, ffstatus to show how long it
# has left. Written here rather than through ffbox_clock_write because this file carries three
# more keys of its own and the helper owns two keys, not a file. Keep the names in step.

# --- the Unity seat, taken NOW rather than when a turn arrives ----------------------------------
#
# The workspace is filled and synced and this container is about to go idle, which makes this the
# one moment in its life when nothing is waiting on it. Activation is an online round trip and a
# full editor launch; paying it here means a dispatched turn pays nothing, which is the whole
# reason the pool exists.
#
# THIS REVERSES THE LAZY ACQUISITION of 2026-08-31. That change was right when every container was
# cold: a plain question paid a licence round trip it never used, and the reply was measured 2m09s
# behind the agent finishing. With a warm pool the cost moves off the request path entirely rather
# than being avoided, so the reason for deferring it is gone.
#
# A STAGED CONTAINER NOW HOLDS A SEAT, which section 12 of the idle-agents design says it does not.
# That is the deliberate trade: `idle_agents` seats are held while the box is quiet, bounded by the
# same number as the pool and returned when a container retires or is dispatched and finishes. It
# is affordable precisely because the machine ids are per slot now -- the licence sees a small
# recycled set of machines rather than one per container.
#
# NEVER FATAL HERE. A container that cannot get a seat is still a warm workspace, and a turn
# dispatched into it will try again through the turn task's own ensure_unity_license. Retiring the
# container instead would turn a licensing hiccup into an empty pool.
# Overridable ONLY so the failsafe can be driven offline by test_pool_task.sh; every real
# container gets the bind-mounted path. The loop below is the one piece of this script whose
# failure mode is a container that never goes away, so it is worth being able to test.
. "${FFBOX_UNITY_LICENSE:-/ffbox/unity-license.sh}"
if try_unity_license; then
    log "holding a Unity seat for whatever is dispatched here"
else
    log "WARNING: could not take a Unity seat; the turn dispatched here will try again"
fi

log "staged on ${FFBOX_REF:-?} at ${staged_at:0:12}, waiting up to ${TTL}s for a request"
log "(the keeper enforces that; this container's own failsafe is ${TTL}s plus a margin)"

# --- the wait, and the one file that settles the race with the deadline -------------------------
#
# The host may be deciding to dispatch into this container at the same moment the deadline
# passes. Both sides create `out/owner` with O_EXCL and whoever wins says what happens next --
# the host dispatches, or this container retires. `set -o noclobber` plus a redirect is that
# create; there is no second check to get wrong and no lock to leak.
#
# `out` rather than `in` because `in` is read-only to us. Nothing untrusted is running inside a
# staged container at this point, which is what makes a container-writable handshake acceptable
# here and would not make it acceptable once the agent is up.
claim_owner() {
    ( set -o noclobber; : > "$FFBOX_OUT/owner" ) 2>/dev/null
}

# THE HOST IS THE ENFORCER NOW AND THIS IS THE FAILSAFE. Since 2026-09-02 the keeper compares
# out/staged on its own pass and retires a spare that has aged out, which removes the race rather
# than relocating it: the host is already the dispatcher, so retiring and dispatching became two
# decisions by one party. What a host-side clock loses is that a spare retires itself when nothing
# is watching -- and this one holds 22 GiB and a Unity seat -- so the container keeps a clock at
# TTL plus a margin. In normal operation the keeper gets there first and none of this runs.
FAILSAFE_MARGIN=${FFBOX_IDLE_FAILSAFE_MARGIN_SECS:-900}
deadline=$(( $(date +%s) + TTL + FAILSAFE_MARGIN ))
pushed=0
while [ ! -e "$FFBOX_IN/dispatch" ]; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        if claim_owner; then
            log "idle for $(( TTL + FAILSAFE_MARGIN ))s and unclaimed; retiring. The keeper should"
            log "have done this ${FAILSAFE_MARGIN}s ago, so something is wrong with it."
            exit 0
        fi
        # THE HOST HAS CLAIMED US. Two things look like this and only one of them is a dispatch.
        #
        # A real dispatch writes job.json, the attachments and the env, then `dispatch` last, about
        # a second later; the push exists so that arriving inside this branch is not a container
        # walking out on a request. A RETIREMENT claims the same file and then stops us, and a
        # keeper that dies between the two -- or whose `docker stop` fails -- leaves a claim that
        # never becomes a dispatch.
        #
        # SO THE PUSH IS TAKEN ONCE. Until 2026-09-02 it was re-armed every time round, and the
        # create it retried could never succeed once the file existed, so this waited and pushed
        # and waited for as long as the container lived. The comment on it said the opposite --
        # "left in place rather than disarmed so a host that claimed and then died does not leave a
        # container waiting for ever" -- and re-arming is not what achieves that; exiting is. That
        # was survivable while only a dispatch ever created `owner`. It is not once a retirement
        # does, which is why the intent is now implemented rather than merely stated.
        if [ "$pushed" = 1 ]; then
            log "the host claimed this container ${FAILSAFE_MARGIN}s ago and never dispatched;"
            log "it is not coming. Retiring rather than holding a workspace and a seat for ever."
            exit 0
        fi
        pushed=1
        log "the deadline passed but the host has claimed this container; waiting for the job"
        deadline=$(( $(date +%s) + FAILSAFE_MARGIN ))
    fi
    sleep "$POLL"
done

waited=$(( TTL + FAILSAFE_MARGIN - (deadline - $(date +%s)) ))
log "dispatched after ~${waited}s idle"

# --- what the host handed us --------------------------------------------------------------------
#
# Parsed rather than sourced. The host is trusted, but a file that is executed is a channel that
# has to be reasoned about every time somebody edits either end, and a loop over KEY=VALUE is not
# harder to write. Only FFBOX_* keys are honoured, so this cannot set PATH or LD_PRELOAD even by
# accident.
if [ -r "$FFBOX_IN/env" ]; then
    while IFS='=' read -r _k _v; do
        [ -n "$_k" ] || continue
        case "$_k" in
            FFBOX_*) export "$_k=$_v" ;;
            \#*)     ;;
            *)       log "ignoring an unexpected key in the dispatch env: $_k" ;;
        esac
    done < "$FFBOX_IN/env"
fi

# --- sync to what the turn asked for -------------------------------------------------------------
#
# The mirror is a live read-only mount, so a container staged four hours ago sees every commit
# fetched since. This is the same fetch-and-reset a cold run does, run by the same script, which
# is the point: a pooled run and a cold run land on the same tree by the same path.
#
# It is not always forwards. A follow-up turn carries conversation.base_sha, which pins turn 1's
# commit, so this can reset backwards onto a commit from days ago -- and a cold run would pay the
# identical reset from an identical tar, so there is nothing to prefer between them.
log "syncing to ${FFBOX_TARGET_SHA:-${FFBOX_REF:-HEAD}}"
_t0=$(date +%s)
if ! /ffbox/restore-workspace.sh --resync; then
    # Say so in the one place the host reads, because a container that fails here has already
    # been claimed and the turn behind it is waiting on an answer.
    printf 'the pooled workspace could not be synced to the requested commit\n' \
        > "$FFBOX_OUT/pool_error.txt"
    die "resync failed"
fi
log "synced in $(( $(date +%s) - _t0 ))s to $(git -C "$WORKSPACE" rev-parse --short HEAD 2>/dev/null)"

# --- become an ordinary turn -----------------------------------------------------------------
#
# exec, so the turn task is PID 1 and `docker stop` reaches ITS traps: the harvest and the Unity
# licence return. A fork here would leave this script as PID 1 holding a signal handler that
# knows nothing about either.
export FFBOX_JOB_FILE="${FFBOX_JOB_FILE:-$FFBOX_IN/job.json}"
export FFBOX_ATTACHMENTS="${FFBOX_ATTACHMENTS:-$FFBOX_IN/attachments}"
export FFBOX_PROMPT_FILE="${FFBOX_PROMPT_FILE:-$FFBOX_IN/prompt.txt}"
export FFBOX_OUT

[ -r "$TURN_TASK" ] || die "no turn task mounted at $TURN_TASK"
log "handing over to $(basename "$TURN_TASK")"
exec bash "$TURN_TASK"
