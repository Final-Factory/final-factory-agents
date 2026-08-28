#!/bin/sh
# slot.sh — one slot, one job, then exit.
#
#   mint a JIT config -> docker run -> the runner takes ONE job -> the container exits
#     -> remove the container, DELETE the registration -> exit 0 -> systemd starts us again
#
# The container did not exist before the job and does not exist after it. Nothing a job writes
# reaches the next job except through GitHub: no bind mounts, no socket, and a tmpfs workspace
# that dies with the container.
#
# Run by ffgithubrunners@<slot>.service as the supervisor account. Takes the slot number as its
# one argument. Everything else comes from lib/config.sh.
#
# EXIT 0 IS ALMOST ALWAYS RIGHT. A finished job, a failed job and a job that never arrived all
# mean the same thing here: this slot is done, and systemd should start a fresh one. Non-zero is
# reserved for a machine that is not fit to run a slot at all, and even then the unit restarts,
# which is why the unit sets StartLimitIntervalSec=0.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

SLOT=${1:?usage: slot.sh <slot number>}
case "$SLOT" in
    ''|*[!0-9]*) echo "slot.sh: slot must be a number, got '$SLOT'" >&2; exit 2 ;;
esac

. "$HERE/lib/config.sh"

log() { printf '[slot %s] %s\n' "$SLOT" "$*"; }

# --- state that teardown needs, set as we go -----------------------------------------------------
RUNNER_ID=""
CNAME=""

# TEARDOWN RUNS ON EVERY EXIT PATH, and that is the whole point of it being a trap. A clean exit
# deregisters itself, so the DELETE below usually returns 404; a container killed mid-job does
# not, which is why the id is captured at mint time and the DELETE is unconditional.
teardown() {
    _rc=$?
    trap - EXIT INT TERM

    if [ -n "$CNAME" ] && docker inspect "$CNAME" >/dev/null 2>&1; then
        log "removing container $CNAME"
        docker rm -f "$CNAME" >/dev/null 2>&1 || log "WARNING: could not remove $CNAME"
    fi

    if [ -n "$RUNNER_ID" ]; then
        if gh_delete_runner "$RUNNER_ID" 2>/dev/null; then
            log "registration $RUNNER_ID released"
        else
            # Not fatal, and not silent. The reaper sweeps registrations whose nonce has no
            # container here, so this is recoverable within one reap interval.
            log "WARNING: could not delete registration $RUNNER_ID; the reaper will get it"
        fi
    fi

    exit "$_rc"
}
trap teardown EXIT INT TERM

# --- drain ---------------------------------------------------------------------------------------

# A drained slot stays RUNNING and idle rather than being stopped, so nothing here has to talk to
# the system manager and no account needs a sudoers entry. Sleep and recheck rather than exiting,
# because exiting would have systemd restart us every RestartSec and fill the journal with it.
if ffghr_is_drained "$SLOT"; then
    log "drained; taking no work until the flag is cleared"
    while ffghr_is_drained "$SLOT"; do
        sleep 15
    done
    log "drain lifted"
fi

# --- preflight, BEFORE minting anything ------------------------------------------------------------
#
# Order matters. A registration minted against a machine that cannot then run a container is a
# leaked registration that the reaper has to clean up, and an operator staring at a runner on the
# org page that never comes online. Check first, mint second.

fail_unfit() {
    log "ERROR: $1"
    # A slow exit on purpose. The unit restarts us, and hammering a broken machine several times a
    # second turns one clear error in the journal into thousands.
    sleep 30
    exit 1
}

docker version >/dev/null 2>&1 \
    || fail_unfit "cannot reach the daemon at $DOCKER_SOCK (02-daemon.sh, and check group membership)"
docker image inspect "$IMAGE" >/dev/null 2>&1 \
    || fail_unfit "image $IMAGE is not built (03-image.sh)"
docker network inspect "$EGRESS_NET" >/dev/null 2>&1 \
    || fail_unfit "network $EGRESS_NET does not exist (03-image.sh)"
[ "$(docker inspect -f '{{.State.Running}}' "$EGRESS_NAME" 2>/dev/null)" = true ] \
    || fail_unfit "the egress proxy $EGRESS_NAME is not running; a job with no way out is worse
             than no job at all (03-image.sh --egress-only)"

# --- mint --------------------------------------------------------------------------------------------

HOST=$(hostname -s 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo host)
NONCE=$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')
# The container and the registration carry the SAME name. The reaper matches on the nonce, and
# giving it one string to match rather than two is one fewer way for the two to disagree.
CNAME="ffghr-$HOST-$SLOT-$NONCE"

. "$HERE/lib/gh.sh"

log "minting a JIT config for $CNAME"
MINT=$(gh_mint_jitconfig "$CNAME") || fail_unfit "could not mint a JIT config; see above"
RUNNER_ID=$(printf '%s' "$MINT" | cut -d' ' -f1)
JIT=$(printf '%s' "$MINT" | cut -d' ' -f2-)
[ -n "$RUNNER_ID" ] && [ -n "$JIT" ] || fail_unfit "generate-jitconfig returned nothing usable"
log "registration $RUNNER_ID, labels $LABELS"

# --- run ------------------------------------------------------------------------------------------------

LOG_FILE="$LOG_DIR/slot-$SLOT.log"
# Appended, not truncated, because logrotate is configured copytruncate and an O_APPEND fd keeps
# writing at the end of the file after a truncation rather than leaving a sparse hole.
: >> "$LOG_FILE" 2>/dev/null || log "WARNING: cannot write $LOG_FILE (01-hostSetup.sh creates it)"

# THE CREDENTIAL GOES THROUGH THE ENVIRONMENT, NOT THROUGH argv. `-e NAME` with no value tells
# docker to carry the variable over from this process, so the JIT config never appears in the
# host's process list the way `-e NAME=value` would.
FFGHR_JITCONFIG=$JIT
export FFGHR_JITCONFIG
unset JIT MINT

# THE TMPFS TARGET MUST EQUAL THE work_folder PASSED TO generate-jitconfig. If they differ the
# runner writes into the image's writable layer instead, everything still works, and the entire
# speed argument for the ram disk quietly evaporates. Both come from $WORK_FOLDER for that reason.
log "starting $CNAME (workspace tmpfs $WORKSPACE_SIZE at $WORK_FOLDER)"
# LABELS SO THE REAPER CAN TELL AN ORPHAN FROM A LIVE JOB. A supervisor killed with SIGKILL
# leaves its container RUNNING and its registration ONLINE, which is indistinguishable from a job
# in progress unless the container says who is looking after it. The pid is checked against a
# cmdline, not on its own, because pids are recycled.
docker run -d \
    --name "$CNAME" \
    --hostname "$CNAME" \
    --label ffghr.supervisor.pid="$$" \
    --label ffghr.slot="$SLOT" \
    --label ffghr.runner.id="$RUNNER_ID" \
    --network "$EGRESS_NET" --dns "$EGRESS_IP" \
    --tmpfs "$WORK_FOLDER:size=$WORKSPACE_SIZE,mode=1777,exec" \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    --pids-limit "$PIDS_LIMIT" \
    --memory "$MEMORY" \
    -e FFGHR_JITCONFIG \
    "$IMAGE" >/dev/null \
    || fail_unfit "docker run failed for $CNAME"

unset FFGHR_JITCONFIG

# Container output goes to the FILE, not to this script's stdout. stdout is the journal, and a
# Unity job log is tens of megabytes; the journal gets this script's own lines instead, which are
# the ones anyone reads first.
( docker logs -f "$CNAME" >> "$LOG_FILE" 2>&1 || true ) &
LOGGER=$!

# --- wait, with the watchdog ---------------------------------------------------------------------------

# Above main.yml's timeout-minutes: 90, so a job GitHub still wants is never killed here. This
# exists for a container that is wedged rather than for one that is slow.
DEADLINE=$(( $(date +%s) + WATCHDOG_MINUTES * 60 ))
KILLED=0

while [ "$(docker inspect -f '{{.State.Running}}' "$CNAME" 2>/dev/null)" = true ]; do
    if [ "$(date +%s)" -ge "$DEADLINE" ]; then
        log "WATCHDOG: $WATCHDOG_MINUTES minutes elapsed; stopping $CNAME"
        # TERM first, then KILL after the grace period. The grace is for the licence trap in the
        # job's shell to run `unity-editor -returnlicense`, which is an editor launch and takes
        # tens of seconds. Whether the signal actually reaches that trap through the runner is
        # open item (d) in the design and is NOT established; if it does not, a watchdog kill
        # leaks a Unity seat and this comment is where to start looking.
        docker stop -t 90 "$CNAME" >/dev/null 2>&1 || true
        KILLED=1
        break
    fi
    sleep 5
done

wait "$LOGGER" 2>/dev/null || true

EXIT_CODE=$(docker inspect -f '{{.State.ExitCode}}' "$CNAME" 2>/dev/null || echo unknown)
if [ "$KILLED" = 1 ]; then
    log "killed by the watchdog after $WATCHDOG_MINUTES minutes"
elif [ "$EXIT_CODE" = 0 ]; then
    log "job finished, container exited 0"
else
    # Not an error here. A failing job is a job that ran; GitHub already knows and has the log.
    log "container exited $EXIT_CODE"
fi

log "log: $LOG_FILE"

# teardown runs from the trap, then systemd starts a fresh slot.
exit 0
