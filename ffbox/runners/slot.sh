#!/bin/sh
# slot.sh — one slot, one job, then exit.
#
#   wait for a place in the pool -> mint a JIT config -> docker run -> the runner takes ONE job
#     -> the container exits -> remove the container, DELETE the registration -> exit 0
#     -> systemd starts us again
#
# A SLOT IS A PLACE FOR A RUNNER, NOT A RUNNER. $SLOTS supervisors run all the time; a container
# exists only while the pool is short of idle runners, so a quiet machine carries $IDLE_POOL
# registrations rather than $SLOTS of them. lib/config.sh's pool section is the rule.
#
# The container did not exist before the job and does not exist after it. No socket, and a tmpfs
# workspace that dies with the container.
#
# ONE THING DOES CROSS: the workspace cache. A job reads $CACHE_DIR/entries READ-ONLY and may drop
# one candidate archive in its own staging directory; THIS SCRIPT decides whether that becomes an
# entry, under a validated name. A job cannot delete or alter an existing entry, cannot reach
# another slot's staging, and cannot write anywhere else on the host. design/ffcache_design.txt
# section 11 states what that costs; an empty cache_dir turns it off entirely.
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

# THE BOX'S CEILING, shared with the agent lane. `slots` above is still this lane's own limit on
# how many of ITS places may be busy; this is the limit on how many containers the machine holds
# altogether, agent runs and staged agent containers included. Both lanes create containers on the
# same daemon and neither could see the other until this existed.
#
# Missing file is survivable for the same reason it is in ffbox: warn, no-op, carry on.
if [ -r "$HERE/../lib-workloads.sh" ]; then
    . "$HERE/../lib-workloads.sh"
else
    echo "slot.sh: WARNING: ../lib-workloads.sh is missing; running with no shared ceiling" >&2
    ffbox_workload_lock_acquire() { return 0; }
    ffbox_workload_lock_release() { return 0; }
    ffbox_workload_has_room() { return 0; }
    FFBOX_WORKLOAD_LABEL=ffbox.workload
fi

log() { printf '[slot %s] %s\n' "$SLOT" "$*"; }

# --- state that teardown needs, set as we go -----------------------------------------------------
RUNNER_ID=""
CNAME=""
STAGE=""

# THE POOL LOCK IS HELD ACROSS THE MINT AND THE `docker run`, so it has to be released on every
# exit path in between, teardown included. Defined here because teardown calls it.
POOL_FD_OPEN=0
pool_unlock() {
    # The SHARED ceiling lock is taken alongside this one and covers the same window -- counted,
    # then created -- so it is released here too and by every path that reaches here, teardown
    # included. Unconditional: releasing one that was never taken is a no-op.
    ffbox_workload_lock_release
    [ "$POOL_FD_OPEN" = 1 ] || return 0
    POOL_FD_OPEN=0
    exec 7>&-
}

# TEARDOWN RUNS ON EVERY EXIT PATH, and that is the whole point of it being a trap. A clean exit
# deregisters itself, so the DELETE below usually returns 404; a container killed mid-job does
# not, which is why the id is captured at mint time and the DELETE is unconditional.
teardown() {
    _rc=$?
    pool_unlock
    # The pool counts a container, not a supervisor, so this marker has to go with the container.
    ffghr_clear_busy "$CNAME"
    # The claim outlives the decision on purpose, so a second slot cannot grant itself the same
    # entry while this job is still working. It has to come back here on EVERY exit path, or one
    # crashed run stops that branch being archived until the claim ages past the watchdog.
    [ -z "${CACHE_CLAIM:-}" ] || ffghr_cache_release_claim "$CACHE_CLAIM"
    trap - EXIT INT TERM

    if [ -n "$CNAME" ] && docker inspect "$CNAME" >/dev/null 2>&1; then
        log "removing container $CNAME"
        docker rm -f "$CNAME" >/dev/null 2>&1 || log "WARNING: could not remove $CNAME"
    fi

    # THE WORKSPACE CACHE, and it happens here because here is where the container is definitely
    # gone and nothing is still writing into staging. design/ffcache_design.txt section 8.
    #
    # EVERY PART OF THIS IS BEST-EFFORT AND NONE OF IT MAY ABORT teardown. The registration delete
    # below is the important half: a cache that fails to promote costs one cold job, a registration
    # that never gets deleted is an orphan on the org page. `|| true` on both, deliberately.
    if [ -n "$STAGE" ]; then
        # FIRST, because it is the only part of teardown anybody is waiting to see. The job wrote
        # a check-run payload instead of POSTing it, so that api.github.com could come off the CI
        # allowlist -- measured: that one step was the only thing in an editmode job that used it.
        # Validated hard inside gh_post_check_run: this token is far stronger than the job's own.
        gh_post_check_run "$STAGE" 2>&1 \
            | while IFS= read -r _line; do log "$_line"; done || true

        ffghr_cache_with_lock ffghr_cache_promote "$STAGE" 2>&1 \
            | while IFS= read -r _line; do log "cache: $_line"; done || true
        ffghr_cache_with_lock ffghr_cache_prune 2>&1 \
            | while IFS= read -r _line; do log "cache: $_line"; done || true
        rm -rf "$STAGE" 2>/dev/null || true
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

# --- wait for a place in the pool -----------------------------------------------------------------
#
# This is where a slot spends most of its life on a quiet machine, and it is also where drain
# lives: both are the same question, "may this slot start a runner right now", and answering them
# in one loop means a drained slot and a slot with no place in the pool behave identically —
# RUNNING, holding nothing, taking no work. Sleeping rather than exiting, because exiting would
# have systemd restart us every RestartSec and fill the journal with it.
#
# AFTER PREFLIGHT, NOT BEFORE. The counts come from the daemon, so a machine that cannot reach it
# should say that once and clearly rather than sit here counting zero containers and admitting
# everything.
#
# THE LOCK IS STILL HELD WHEN THIS RETURNS, and that is the point of it. Admission is decided from
# a count that minting then changes, so the count has to stay frozen until the new container
# exists and is countable — the `docker run` below, a couple of seconds later. Releasing here and
# re-taking it afterwards would put every other waiter's decision inside that gap.
# WHAT CODE THIS SUPERVISOR IS RUNNING, so it can notice that the answer has changed.
#
# THE POOL MADE THIS NECESSARY. Before it, a slot ran one job and exited, so systemd restarted it
# into whatever was on disk and a merge reached every slot within a job or two. A slot that is
# WAITING now sits in the loop below for as long as the machine is quiet — hours — and it is
# still executing the file the self-updater rewrote underneath it, which is both stale and, since
# `sh` reads a script by byte offset, not necessarily even coherent. The updater's own header
# makes exactly this point about ffbox: editing a file is not deploying it.
#
# A waiting slot holds NOTHING — no container, no registration, no lock — so exiting costs
# nothing and systemd starts a fresh one five seconds later on the new code.
code_stamp() {
    stat -c '%n %Y %s' "$0" "$HERE/lib/config.sh" 2>/dev/null | tr '\n' ' '
}
CODE_STAMP=$(code_stamp)

pool_summary() {
    _ps=$(ffghr_pool_counts)
    printf '%s of %s slots in use, %s idle, want %s' "${_ps% *}" "$SLOTS" "${_ps#* }" "$IDLE_POOL"
    unset _ps
}

wait_for_a_place() {
    _announced=""
    while :; do
        if ffghr_is_drained "$SLOT"; then
            [ "$_announced" = drained ] || log "drained; taking no work until the flag is cleared"
            _announced=drained
            sleep "$POOL_POLL_SECONDS"
            continue
        fi
        [ "$_announced" != drained ] || log "drain lifted"

        if [ "$(code_stamp)" != "$CODE_STAMP" ]; then
            log "slot.sh or lib/config.sh changed on disk; exiting so systemd starts the new code"
            exit 0
        fi

        ffghr_reload_limits

        # Opened and closed each time round rather than held across the sleep: an fd waiting on
        # flock is invisible, and a supervisor that took the lock and then slept would stall every
        # other slot for as long as it sat here.
        exec 7>>"$FFGHR_POOL_LOCK"
        POOL_FD_OPEN=1
        if ! flock -w 30 7; then
            # SAID EVERY TIME, unlike the two below. Thirty seconds means another slot has been
            # holding this across a mint for half a minute, which is a GitHub API that is retrying,
            # not a busy machine — and the count in the other messages would be a guess.
            pool_unlock
            log "could not take $FFGHR_POOL_LOCK within 30s; another slot is still minting"
            _announced=""
            sleep "$POOL_POLL_SECONDS"
            continue
        fi
        if ffghr_pool_admit; then
            # THIS LANE HAS A PLACE. Whether the BOX does is a second question, and it is asked
            # under a second lock held across the same window -- see lib-workloads.sh. Ordering is
            # always pool lock then ceiling lock; the agent lane takes only the ceiling lock, so
            # there is no cycle to deadlock on.
            if ffbox_workload_lock_acquire && ffbox_workload_has_room; then
                log "starting a runner ($(pool_summary))"
                return 0
            fi
            pool_unlock
            if [ "$_announced" != full ]; then
                log "this lane has a place, but the box is at its container ceiling; waiting"
                _announced=full
            fi
            sleep "$POOL_POLL_SECONDS"
            continue
        fi
        pool_unlock

        if [ "$_announced" != waiting ]; then
            log "the pool is satisfied ($(pool_summary)); waiting"
            _announced=waiting
        fi
        sleep "$POOL_POLL_SECONDS"
    done
}

wait_for_a_place

# --- mint --------------------------------------------------------------------------------------------

HOST=$(hostname -s 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo host)
NONCE=$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')
# The container and the registration carry the SAME name. The reaper matches on the nonce, and
# giving it one string to match rather than two is one fewer way for the two to disagree.
CNAME="ffghr-$HOST-$SLOT-$NONCE"

. "$HERE/lib/gh.sh"
. "$HERE/lib/mirror.sh"

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
# Drop everything, then add back only what Unity's package extraction needs. See lib/config.sh.
CAP_ADD_ARGS=""
for _cap in $(printf '%s' "$CAP_ADD" | tr ',' ' '); do
    CAP_ADD_ARGS="$CAP_ADD_ARGS --cap-add=$_cap"
done
# shellcheck disable=SC2086  # CAP_ADD_ARGS, CACHE_ARGS and MACHINE_ID_ARGS are deliberately
# word-split option lists

# THE WORKSPACE CACHE MOUNTS. Two of them, and the asymmetry is the design:
#
#   /ffcache     entries, READ-ONLY. The job restores from it and cannot alter what is there.
#   /ffghr/out   this slot's drop box, read-write. The job proposes a candidate; teardown decides.
#
# STAGING IS CREATED HERE, BEFORE THE RUN, AND NEVER ONLY CLEANED UP AFTER IT. A teardown that did
# not complete — SIGKILL, a reboot — would otherwise leave the next job on this slot reading a dead
# job's drop box and promoting its archive under its name. Creating it fresh up front is the one
# ordering that cannot get that wrong.
#
# 0770 and the group comes from staging/'s setgid bit: the job writes as the daemon's own uid and
# nothing here can chown. See 01-hostSetup.sh.
CACHE_ARGS=""
if ffghr_cache_ready; then
    STAGE=$(ffghr_cache_stage_dir "$SLOT")
    rm -rf "$STAGE" 2>/dev/null || true
    # THE MODE COMES FROM THE UMASK, NOT FROM A chmod, AND THAT IS NOT A STYLE CHOICE.
    #
    # `mkdir -p "$STAGE" && chmod 0770 "$STAGE"` fails here with EPERM, and the chain is worth
    # writing down because every link looks harmless:
    #
    #   1. staging/ is setgid (2775) on purpose, so slot-N inherits group ffbox-container.
    #   2. mkdir under the service's UMask=0022 therefore leaves slot-N at 2755 — group r-x,
    #      NO WRITE, so the job (host uid 1020) cannot write its drop box.
    #   3. GNU chmod PRESERVES a directory's setgid bit for a numeric mode unless you write an
    #      extra leading zero. `chmod 0770 dir` requests 02770; only `chmod 00770` requests 0770.
    #      Measured: 0770 -> drwxrws---, 00770 -> drwxrwx---.
    #   4. The unit sets RestrictSUIDSGID=yes, whose seccomp filter denies any chmod that SETS
    #      S_ISGID. So step 3 is refused with "Operation not permitted" on a directory this
    #      account owns, which is a confusing enough sentence to lose an hour to.
    #
    # umask 007 gets the mode right in the mkdir itself: 0777 & ~007 = 0770, and the kernel adds
    # the setgid from the parent. Same 2770 result, one syscall, and nothing for the seccomp
    # filter to object to because the SYSCALL ARGUMENT never carries S_ISGID.
    #
    # The error is captured rather than discarded for the same reason: "could not prepare" on its
    # own says nothing, and the errno says which of the four links broke.
    if _err=$( umask 007; mkdir -p "$STAGE" 2>&1 ); then
        CACHE_ARGS="-v $FFGHR_CACHE_ENTRIES:/ffcache:ro -v $STAGE:/ffghr/out"
        log "cache: $(find "$FFGHR_CACHE_ENTRIES" -maxdepth 1 -type f -name '*@*.tar' 2>/dev/null | wc -l) entries at $FFGHR_CACHE_ENTRIES, staging $STAGE"
    else
        # Not fatal, and never fatal. A job with no cache is a slow job, not a failed one.
        log "WARNING: could not prepare $STAGE (${_err:-no error text}); running without the cache"
        STAGE=""
    fi
    unset _err
else
    log "cache: not provisioned or disabled; running without it"
fi

# THE UNITY MACHINE ID. Passed in rather than baked, because it is derived from the SLOT: see the
# machine id section of lib/config.sh for why per-slot rather than game-ci's per-container random.
# Empty means "leave the image's alone", which is what machine_id=image asks for.
# THE UNITY LICENCE, MOUNTED READ-ONLY. A file rather than the account credentials the job used to
# activate with; see ffbox/unity-offline-license.sh. Absent is not fatal here -- the job still has
# the workflow's own UNITY_* secrets to fall back on, and unity-license.sh says so loudly.
# Refreshed at container-creation time for the same reason ffbox does it: a Personal .ulf carries a
# rolling ~24-hour UpdateDate, and a CI job wants one that outlives the job. Quiet when there is
# nothing to do, and never fatal -- a job with the workflow's own credentials can still activate.
_FFGHR_LICTOOL=$HERE/../unity-offline-license.sh
if [ -x "$_FFGHR_LICTOOL" ]; then
    sh "$_FFGHR_LICTOOL" ensure "${FFGHR_LICENCE_MIN_HOURS:-4}" 2>&1 | while IFS= read -r _l; do
        log "$_l"
    done || :
fi

LICENCE_ARGS=""
if [ -r "$FFGHR_UNITY_ULF" ]; then
    LICENCE_ARGS="-v $FFGHR_UNITY_ULF:/ffbox/unity/Unity_lic.ulf:ro -e FFBOX_UNITY_ULF=/ffbox/unity/Unity_lic.ulf"
else
    log "WARNING: no Unity licence at $FFGHR_UNITY_ULF; jobs will fall back to workflow credentials"
fi

MACHINE_ID_ARGS=""
if _mid=$(ffghr_machine_id "$SLOT"); then
    # Not a secret, so the value may sit in argv: it identifies a machine, it does not authenticate
    # one, and it is derived from this host's name and a slot number.
    MACHINE_ID_ARGS="-e FFGHR_MACHINE_ID=$_mid"
    log "machine id $_mid (Unity sees this slot as its own machine)"
    unset _mid
fi

log "starting $CNAME (workspace tmpfs $WORKSPACE_SIZE at $WORK_FOLDER, caps +$CAP_ADD)"
# LABELS SO THE REAPER CAN TELL AN ORPHAN FROM A LIVE JOB. A supervisor killed with SIGKILL
# leaves its container RUNNING and its registration ONLINE, which is indistinguishable from a job
# in progress unless the container says who is looking after it. The pid is checked against a
# cmdline, not on its own, because pids are recycled.
docker run -d \
    --name "$CNAME" \
    --hostname "$CNAME" \
    --label "$FFBOX_WORKLOAD_LABEL=ci" \
    --label ffghr.supervisor.pid="$$" \
    --label ffghr.slot="$SLOT" \
    --label ffghr.runner.id="$RUNNER_ID" \
    --network "$EGRESS_NET" --dns "$EGRESS_IP" \
    --tmpfs "$WORK_FOLDER:size=$WORKSPACE_SIZE,mode=1777,exec" \
    $CACHE_ARGS \
    $LICENCE_ARGS \
    $MACHINE_ID_ARGS \
    --cap-drop=ALL \
    $CAP_ADD_ARGS \
    --security-opt=no-new-privileges \
    --pids-limit "$PIDS_LIMIT" \
    --memory "$MEMORY" \
    -e FFBOX_MODE=ci \
    -e FFGHR_GIT_MIRROR="$MIRROR_URL" \
    -e FFGHR_GIT_ORIGIN="$MIRROR_ORIGIN" \
    -e FFGHR_LFS_URL="$MIRROR_LFS_URL" \
    -e FFGHR_JITCONFIG \
    "$IMAGE" >/dev/null \
    || fail_unfit "docker run failed for $CNAME"

unset FFGHR_JITCONFIG

# THE POOL LOCK GOES HERE, AND NOT ONE LINE LATER. The container now exists, so `docker ps` counts
# it and the next waiter's decision is made against the truth. It also has to come BEFORE the
# background logger below: a child inherits open file descriptors, and a `docker logs -f` that
# outlives this line would hold the lock for the length of the job.
pool_unlock

# Container output goes to the FILE, not to this script's stdout. stdout is the journal, and a
# Unity job log is tens of megabytes; the journal gets this script's own lines instead, which are
# the ones anyone reads first.
# A marker per job, so `ffgithubrunners logs` can show THE LAST JOB rather than everything the
# file has accumulated since logrotate last touched it.
printf '===== ffghr job %s started %s =====\n' "$CNAME" "$(date -Is)" >> "$LOG_FILE" 2>/dev/null || true
( docker logs -f "$CNAME" >> "$LOG_FILE" 2>&1 || true ) &
LOGGER=$!

# --- wait, with the watchdog ---------------------------------------------------------------------------

# Above main.yml's timeout-minutes: 90, so a job GitHub still wants is never killed here. This
# exists for a container that is wedged rather than for one that is slow.
# THE JOB DECLARES, THE HOST GRANTS, AND NOBODY WAITS. The job writes branch.info as one of its
# first steps; this loop is already awake every five seconds for the watchdog, so it decides while
# the tests run — tens of minutes of slack — and drops cache.request into the same staging
# directory. By the time the job reaches its archive step the answer is already there.
#
# Deciding here rather than at container start is forced: slot.sh mints a JIT config and launches
# the container BEFORE GitHub hands it a job, so the branch does not exist yet.
CACHE_DECIDED=0
CACHE_CLAIM=""

decide_cache_archive() {
    [ "$CACHE_DECIDED" = 0 ] || return 0
    [ -n "${STAGE:-}" ] && [ -r "$STAGE/branch.info" ] || return 0

    _want=$(head -1 "$STAGE/branch.info" 2>/dev/null | tr -d ' \r\n')
    [ -n "$_want" ] || return 0
    CACHE_DECIDED=1

    case "$_want" in *.tar) ;; *) _want="$_want.tar" ;; esac
    if ! ffghr_cache_name_ok "$_want"; then
        log "cache: the job asked for '$_want', which is not a usable entry name; not archiving"
        return 0
    fi

    if ffghr_cache_with_lock ffghr_cache_should_archive "$_want" "$SLOT"; then
        CACHE_CLAIM=$_want
        : > "$STAGE/cache.request" 2>/dev/null \
            && log "cache: $_want is due; asked the job to archive it" \
            || log "cache: could not write the request into $STAGE"
    else
        log "cache: $_want is fresh or claimed by another slot; not archiving this run"
    fi
}

DEADLINE=$(( $(date +%s) + WATCHDOG_MINUTES * 60 ))
KILLED=0

# WHETHER THIS CONTAINER HAS TAKEN A JOB, and the reason this loop is worth waking up for while
# nothing is wrong. Until it flips, this container is the pool's idle runner and no other slot
# will start one; the moment it flips, the marker goes down and the next waiting slot brings a
# replacement up within its poll interval. Nobody else can see this: docker top is the only
# signal, and it is this supervisor's container.
BUSY=0

while [ "$(docker inspect -f '{{.State.Running}}' "$CNAME" 2>/dev/null)" = true ]; do
    if [ "$BUSY" = 0 ] && ffghr_container_busy "$CNAME"; then
        BUSY=1
        if ffghr_mark_busy "$CNAME"; then
            log "job started; the pool is short an idle runner and will start one"
        else
            # Not fatal, and the failure is bounded: the pool over-counts this container as idle,
            # so it runs one runner short until the job ends. Worth a line, not worth dying for.
            log "WARNING: could not write the busy marker in $FFGHR_STATE_DIR; the pool will count this slot as idle"
        fi
    fi
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
    decide_cache_archive
    # The job asks for the commit it needs before its restore step, which takes about forty
    # seconds, so this poll has slack and the answer is normally waiting by the time the checkout
    # runs. Never fatal: while github.com is still allowlisted a job that gets no answer just
    # fetches from GitHub as before.
    if [ -n "${STAGE:-}" ]; then
        ffghr_mirror_serve_request "$STAGE" 2>&1 \
            | while IFS= read -r _line; do log "mirror: $_line"; done || true
    fi

    # THE ARTIFACT UPLOAD, AND IT HAS TO BE HERE RATHER THAN IN TEARDOWN.
    #
    # The first version of this ran beside the check-run relay after the container exited, which
    # cannot work and fails with a message that says so exactly:
    #
    #     CreateArtifact failed: HTTP 403 {"code":"permission_denied","msg":"job is completed"}
    #
    # The Actions service will not create an artifact for a job that has finished, so the upload
    # has to happen while the job is still live -- which means from this loop, with the job
    # WAITING on artifact.done, exactly as it already waits on fetch.done. The job holds itself
    # open for us; that is the whole reason this is not in teardown.
    #
    # Up to one poll interval of job time, so 15s, plus the transfer. Measured artifact: 54 kB.
    #
    # artifact.done IS WRITTEN EITHER WAY, success or failure, so a job never waits out its whole
    # budget on an upload that was never going to happen.
    if [ -n "${STAGE:-}" ] && [ -f "$STAGE/artifact.request" ] && [ ! -f "$STAGE/artifact.done" ]; then
        python3 "$HERE/lib/artifact-upload.py" "$STAGE" \
            --allow-repository-ids "$ARTIFACT_REPO_IDS" 2>&1 \
            | while IFS= read -r _line; do log "artifact: $_line"; done || true
        printf 'done\n' > "$STAGE/artifact.done" 2>/dev/null || true
    fi
    # FIFTEEN SECONDS ONCE THERE IS A JOB, NOT FIVE. From then on this loop only has to notice two
    # things: a container that has exited, and a branch.info the job wrote near its start. The job
    # then runs for tens of minutes before it needs the answer, so the extra latency is invisible,
    # and several slots each waking twelve times a minute to run `docker inspect` is work nobody
    # asked for. The watchdog deadline is measured in hours; 15s of granularity on it means nothing.
    #
    # BEFORE THERE IS A JOB IT IS THE POOL POLL, because then this loop is the thing that notices
    # a job arriving, and everything waiting to start a replacement runner is waiting on it.
    if [ "$BUSY" = 1 ]; then
        sleep 15
    else
        sleep "$POOL_POLL_SECONDS"
    fi
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
