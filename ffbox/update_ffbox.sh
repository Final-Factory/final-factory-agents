#!/bin/sh
# update_ffbox.sh — fetch, fast-forward and restart ffbox into the new code.
#
#   sudo systemctl start ffbox-update.service    the trigger (what the timer also does)
#   sh ffbox/update_ffbox.sh                     the same thing, by hand — as the checkout's
#                                                owner, NOT under sudo
#   sh ffbox/update_ffbox.sh --dry-run           say what would happen; change nothing
#
# Design: design/self_update_design.txt. The parts that are not obvious from the code:
#
# WHY THIS EXISTS. The units run this checkout directly, so new code on disk is live at the
# next process start and NOT before. On 2026-08-22 the build server was found running ffwatch
# from a checkout twelve hours older than HEAD, and a guard committed at 16:46 was not live at
# 20:41. Editing a file is not deploying it.
#
# AND THE CONFIG IS A FILE. ~/.config/ffbox/config.json is read once per process, in ffwatch's
# main(); ~/.config/ffbox/secrets.env is read once per START, by systemd, as the EnvironmentFile
# of all three units. So an edit to either is exactly as undeployed as an edit to a .py file —
# and neither is in git, so until 2026-09-02 the SHA comparison below saw nothing and the box
# kept the old settings until the next commit happened along. There are two triggers now: new
# commits, and a watched file whose hash no longer matches the one the running processes
# started on.
#
# WHY IT IS NOT PART OF ffbox.target. A bad commit that stops ffwatch from starting is exactly
# when an update matters. Nothing here may depend on ffbox being healthy: the drain is an
# optimisation over a hard stop, and every way it can fail — timeout, crash, a broken
# ffwatch.py that cannot even parse — falls through to stop-update-start.
#
# WHY IT DRAINS FIRST. ffbox bind-mounts the container's task script and ffverify from this
# checkout, read-only but LIVE, for the whole run. A merge while a container is running really
# does change the script underneath it.
#
# NO ROLLBACK, by the owner's call. A commit that breaks ffbox takes the box down until the
# next good commit lands, and the independence above is what makes that recoverable without
# touching the machine.
#
# IT RUNS UNPRIVILEGED. This process fetches code off the internet and then executes it, which
# makes it the last thing on the box that should hold root. It holds none. The single exception
# is stopping and starting the services whose code it is replacing: sudo_systemctl below, backed
# by the narrow FFBOX_UNITS alias 02-zfsSetup.sh writes into /etc/sudoers.d/ffbox. Installing a
# unit needs a human — see WHAT IT WILL NOT DO, at step 5.
#
# POSIX sh, like its siblings.
set -eu

# ------------------------------------------------------------------------------------------
# re-exec from a copy of ourselves
# ------------------------------------------------------------------------------------------
# `sh` reads a script incrementally, by byte offset. The merge below rewrites this file, and a
# shell that then reads the next line out of different text does something nobody wrote. The
# copy is what survives; the checkout is free to change underneath it.
if [ "${FFBOX_UPDATE_REEXEC:-0}" != 1 ]; then
    # The checkout has to be resolved HERE, while $0 is still this file. After the re-exec $0
    # is the temp copy in /tmp, and deriving the repo from it would silently walk to / —
    # found by running it.
    _here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
    FFBOX_UPDATE_REPO=${FFBOX_UPDATE_REPO:-$(CDPATH= cd -- "$_here/.." && pwd)}
    _self=$(mktemp) || { echo "update_ffbox: cannot make a temp copy" >&2; exit 1; }
    cat "$0" > "$_self"
    FFBOX_UPDATE_REEXEC=1
    export FFBOX_UPDATE_REEXEC FFBOX_UPDATE_REPO
    sh "$_self" "$@"
    _rc=$?
    rm -f "$_self"
    exit "$_rc"
fi

REPO=${FFBOX_UPDATE_REPO:?the re-exec must pass the checkout path}
BRANCH=${FFBOX_UPDATE_BRANCH:-master}
# THE WINDOW, AND WHAT HAPPENS AT THE END OF IT. Past it the update goes ahead anyway, because a
# box that never updates because it is never quiet is a box running code nobody chose. Forcing is
# still a SOFT stop — see the force block in section 3 — so "forced" means "we stopped waiting",
# never "we threw the work away".
#
# 300, NOT 3600, AND THE MEANING CHANGED WITH THE NUMBER. This used to be how long to wait for
# CONTAINERS to finish, and an hour was the compromise between a box that never updates and a run
# that gets interrupted. Containers survive a restart now -- ffbox detaches, the clock is a file
# and finish_runs picks the run up on the other side -- so the update does not wait for them at
# all. What is left to wait for is the HOST-SIDE TAIL: a turn whose container has already exited
# and whose harvest, push, pull request or reply is in a thread right now. That is seconds of
# work, not minutes, and five minutes of slack is generous for it.
#
# THE OLD NUMBER LIVES ON under STOP_RUNNING below, where waiting for containers is the point.
DRAIN_TIMEOUT=${FFBOX_DRAIN_TIMEOUT:-300}
# WAITING FOR CONTAINERS, WHICH IS NOW A DELIBERATE ACT. A security fix, an image change, a
# commit that must apply to everything running right now: those are the cases where a container
# outliving the update is wrong. A file as well as an environment variable, so a human can arm it
# and let the five-minute timer pick it up rather than having to run the update by hand.
STOP_RUNNING=0
[ -n "${FFBOX_UPDATE_STOP_RUNNING:-}" ] && STOP_RUNNING=1
# A CONTAINER CANNOT BE ADOPTED FOR EVER. Well above any job this is meant to carry -- the
# twenty-hour runs it was built for have a day and a half of headroom -- so reaching it means a
# container nothing else is bounding, and an update is the last thing on the box that would
# notice.
MAX_CONTAINER_AGE=${FFBOX_MAX_CONTAINER_AGE:-172800}
# What each container gets to run its PID-1 trap when the window does expire: the workspace
# harvest and the Unity licence return. ffbox uses the same floor for its own timeout stops.
FORCE_STOP_GRACE=${FFBOX_FORCE_STOP_GRACE:-120}
# AND THE SAME NUMBER FOR A CONTAINER WE ARE MERELY TIDYING AWAY, which is a separate knob only
# because it is a separate decision. An idle staged container has nothing to harvest, but it HAS
# held a Unity seat since 2026-09-01, and the trap that gives one back is an editor launch. This
# stop used to pass 10, so the drain SIGKILLed a container part-way through returning its licence
# on every pass that had something to merge. See ffbox/lib-workloads.sh's FFBOX_LICENCE_STOP_FLOOR.
LICENCE_STOP_GRACE=${FFBOX_LICENCE_STOP_GRACE:-120}
# And what the HOST gets afterwards, to finish publishing the containers we just stopped.
FORCE_SETTLE=${FFBOX_FORCE_SETTLE_SECS:-300}
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

[ -d "$REPO/.git" ] || { echo "update_ffbox: $REPO is not a git checkout" >&2; exit 1; }
# The owner of the CHECKOUT, never SUDO_USER or the caller: those answer "who ran this", and
# what matters is whose credentials the fetch needs and whose ownership the new objects get.
# Root running git here would leave root-owned objects in .git and break every later pull.
OWNER=$(stat -c %U "$REPO/.git")
OWNER_HOME=$(getent passwd "$OWNER" | cut -d: -f6)
OWNER_HOME=${OWNER_HOME%/}
CONFIG_DIR=${FFBOX_CONFIG_DIR:-$OWNER_HOME/.config/ffbox}
KILL_SWITCH=$CONFIG_DIR/update.disabled
DRAIN_SWITCH=$CONFIG_DIR/draining
# The armed form of the knob at the top of this file. Checked here rather than there because
# CONFIG_DIR is not known until the checkout's owner has been resolved.
[ -e "$CONFIG_DIR/update.stop-running" ] && STOP_RUNNING=1
LOCK=$CONFIG_DIR/update.lock
# THE FLAG THAT SAYS AN UPDATE IS ACTUALLY LANDING, as opposed to this script merely running.
# The unit is `activating` for the second or two of every five-minute poll, and a status reader
# that has only that to go on calls all 288 of a day's polls "updating" -- which sends somebody
# looking for the commit that just landed when none did. Written in section 3, once the decision
# to restart the box has been made and not before, so its presence is the decision itself. It
# carries the reason, the way the drain flag does, because "updating" is the question and
# "8a77205 -> 2ad5553" is the answer.
APPLY_FLAG=$CONFIG_DIR/update.applying
# THE FILES THAT ONLY REACH A SERVICE THROUGH A PROCESS START, relative to CONFIG_DIR, and the
# stamp holding the hash each one had when the running services started on it.
#
#   config.json   ffwatch calls load_config() once, in main(), then loops for weeks off that dict
#   secrets.env   EnvironmentFile= in ffwatch, ffweb and ffdiscord-listener; systemd reads it
#                 when it forks the unit and never again
#
# NOT the runners' ~/.config/ffbox/githubrunners/secrets.env, and not by oversight. That one is
# sourced per invocation by the ffgithubrunners CLI rather than held by a daemon, and its slots
# are in ffgithubrunners.target, which this script does not restart — watching it would earn a
# restart of the wrong target.
WATCHED_FILES="config.json secrets.env"
CONFIG_STAMP=$CONFIG_DIR/update.config-sha
# WHEN THIS BOX LAST TOOK NEW CODE — one line, `<epoch> <sha>`, written in section 6 by the
# pass that actually fast-forwarded. NOT when the timer last looked: the timer looks every five
# minutes and finds nothing almost every time, so "last checked" answers a question nobody asks
# while hiding the one they do — is this box running what was pushed an hour ago? ffstatus.sh
# reads it, the terminal and the page both show it, and a box that has taken no code since the
# stamp was invented says so rather than guessing from an mtime that a stray `git` command
# could have moved.
#
# A CONFIG-ONLY RESTART DOES NOT TOUCH IT. That pass drains and restarts, but the checkout is
# on the same commit it was on before, and calling that an update would make the number lie in
# the direction that matters — a box stuck on a two-day-old commit would read as freshly
# updated every time somebody edited config.json.
APPLIED_STAMP=$CONFIG_DIR/update.last-applied

log() { printf '[ffbox-update] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

# Normally a no-op: the unit sets User= to this account, so we ARE the owner and this just
# pins HOME. It keeps the runuser branch for the one case that still reaches here as root —
# somebody running the script by hand under sudo out of habit — because git reading root's
# config would miss the owner's ~/.git-credentials and leave root-owned objects in .git.
as_owner() {
    if [ "$(id -un)" = "$OWNER" ]; then
        env HOME="$OWNER_HOME" "$@"
    else
        runuser -u "$OWNER" -- env HOME="$OWNER_HOME" "$@"
    fi
}
git_() { as_owner git -C "$REPO" "$@"; }

# THE ONLY ELEVATION IN THIS SCRIPT, and -n so it can never sit waiting on a password prompt
# that nothing will ever answer. A machine whose sudoers rule is missing gets a clear line and
# a still-running old version, which is a better failure than a timer that hangs for 8100s.
sudo_systemctl() {
    if [ "$(id -u)" = 0 ]; then
        systemctl "$@"
    elif sudo -n systemctl "$@" 2>/dev/null; then
        :
    else
        log "WARNING: 'sudo -n systemctl $*' was refused. Re-run 02-zfsSetup.sh to install the"
        log "         FFBOX_UNITS sudoers rule, or run 'sudo systemctl $*' by hand."
        return 1
    fi
}

# A HASH, NOT AN MTIME. setup.sh runs on every update pass and its config stage is setdefault
# the whole way down, so config.json is opened and rewritten routinely; a touch that changes no
# byte must not cost the box a drain and a restart.
#
# ONE LINE PER FILE, `name hash`, rather than a single hash over all of them. It costs nothing
# and it is what lets the journal say WHICH file changed, which is the first thing an operator
# reading that line wants to know. It also makes adding a file to the set a non-event: an entry
# the stamp has never carried is recorded rather than treated as a change (see section 2).
#
# A missing or unhashable file answers with a CONSTANT rather than an empty string. The stamp is
# compared for inequality, and an empty answer would differ from every stored value forever —
# a machine with no config.json restarting itself every five minutes. The hashes stay out of the
# log: secrets.env's is a fingerprint of a secret, and a journal is not where that goes.
config_fingerprint() {
    for _f in $WATCHED_FILES; do
        if [ -r "$CONFIG_DIR/$_f" ]; then
            _h=$(sha256sum "$CONFIG_DIR/$_f" 2>/dev/null | cut -c1-64)
            printf '%s %s\n' "$_f" "${_h:-unhashable}"
        else
            printf '%s %s\n' "$_f" "absent"
        fi
    done
    unset _f _h
}

# One file's hash out of a fingerprint, or "" when that fingerprint has no line for it.
fingerprint_of() { printf '%s\n' "$2" | awk -v f="$1" '$1 == f { print $2 }'; }

# ------------------------------------------------------------------------------------------
# one at a time
# ------------------------------------------------------------------------------------------
# A drain can take an hour. A trigger arriving during one exits rather than queueing behind it:
# two updaters would fight over the same checkout, and the second's `resume` would land inside
# the first's drain.
mkdir -p "$CONFIG_DIR"
if command -v flock >/dev/null 2>&1 && [ "${FFBOX_UPDATE_LOCKED:-0}" != 1 ]; then
    FFBOX_UPDATE_LOCKED=1; export FFBOX_UPDATE_LOCKED
    # NOT `exec flock ... || fallback`: exec REPLACES this shell, so the fallback never runs and
    # a trigger arriving during a drain exits with flock's 1 — a unit systemd reports as failed
    # every five minutes for doing exactly the right thing. Found by running it. -E gives the
    # could-not-acquire case its own status so it can be told apart from the script failing.
    set +e
    flock -n -E 199 "$LOCK" sh "$0" "$@"
    rc=$?
    set -e
    if [ "$rc" = 199 ]; then
        log "another update is already running — nothing to do"
        exit 0
    fi
    exit "$rc"
fi

FFWATCH=$REPO/ffbox/ffwatch.py
FFGHR=$REPO/ffbox/runners/ffgithubrunners

# WHICH DAEMON, SET HERE RATHER THAN INHERITED, and for exactly the reason ffbox's own header
# gives: `docker` with no DOCKER_HOST falls back to the current CONTEXT, which on this account is
# still `rootless` -> /run/user/1015/docker.sock. That daemon holds none of the containers this
# script has to look at, so an inherited context would report a quiet box and sail into the stop
# with six jobs running on the other one.
FFBOX_DOCKER_SOCK=${FFBOX_DOCKER_SOCK:-/run/ffbox-container/docker.sock}
docker_() { as_owner env DOCKER_HOST="unix://$FFBOX_DOCKER_SOCK" docker "$@"; }
FLAG_LIFTED=0
lift_drain() {
    [ "$FLAG_LIFTED" = 1 ] && return 0
    FLAG_LIFTED=1
    [ "$DRY_RUN" = 1 ] && return 0
    # By hand rather than through ffwatch: this also has to work when the commit we just
    # installed is the reason ffwatch.py will not run.
    rm -f "$DRAIN_SWITCH" 2>/dev/null || :
    # THE CI LANE TOO, and by hand for the same reason. ffgithubrunners' drain is a flag file
    # under its own config dir; `resume` is the CLI for it and this is what that CLI writes.
    rm -f "$CONFIG_DIR/githubrunners/drain" 2>/dev/null || :
}
# SEPARATE FROM lift_drain, AND NOT FOLDED INTO IT, because the two end at different moments.
# The drain is lifted in section 6, deliberately a line BEFORE `systemctl start ffbox.target`,
# so nothing observes the window; the update is not over until this process is. Folded together,
# the flag would come off there too and the last minutes of an update -- the start, and the unit
# check after it, which is where a start that fails is found -- would read as `checking`.
clear_applying() {
    [ "$DRY_RUN" = 1 ] && return 0
    rm -f "$APPLY_FLAG" 2>/dev/null || :
}
# A crash, or systemd's TimeoutStartSec, must not leave the machine drained and silent -- nor
# leave a flag claiming an update that is no longer running.
trap 'lift_drain; clear_applying' EXIT HUP INT TERM

# ------------------------------------------------------------------------------------------
# 1. lift a flag stranded by a previous run
# ------------------------------------------------------------------------------------------
# Unconditional, and safe only because of the flock above.
if [ -e "$DRAIN_SWITCH" ] && [ "$DRY_RUN" = 0 ]; then
    log "clearing a drain flag left by an earlier run: $DRAIN_SWITCH"
    rm -f "$DRAIN_SWITCH"
fi
if [ -e "$CONFIG_DIR/githubrunners/drain" ] && [ "$DRY_RUN" = 0 ]; then
    log "clearing a CI drain flag left by an earlier run"
    rm -f "$CONFIG_DIR/githubrunners/drain"
fi
# And the flag that claims an update is landing. Only a SIGKILL gets past the EXIT trap, but the
# whole point of the flag is that a status page believes it, so a stale one has to go the same
# way the drain flags do -- and it is safe here for the same reason they are: the flock above
# means the only update that could own this flag is this one.
if [ -e "$APPLY_FLAG" ] && [ "$DRY_RUN" = 0 ]; then
    log "clearing an update-in-progress flag left by an earlier run: $APPLY_FLAG"
    rm -f "$APPLY_FLAG"
fi

# ------------------------------------------------------------------------------------------
# 2. is there anything to do — new commits, a changed config, or neither
# ------------------------------------------------------------------------------------------
if [ -e "$KILL_SWITCH" ]; then
    log "kill switch present ($KILL_SWITCH) — not updating"
    exit 0
fi
if [ -n "$(git_ status --porcelain 2>/dev/null)" ]; then
    # Never stashed, never reset. The working copy is someone's workspace, and the updater has
    # no business deciding that uncommitted work is expendable.
    log "working tree is dirty — not updating. Commit or stash it:"
    git_ status --short | sed 's/^/    /'
    exit 0
fi

log "fetching origin/$BRANCH"
git_ fetch --prune --quiet origin "$BRANCH" || die "fetch failed"
OLD_SHA=$(git_ rev-parse HEAD)
NEW_SHA=$(git_ rev-parse FETCH_HEAD)
CODE_UPDATE=1
if [ "$OLD_SHA" = "$NEW_SHA" ]; then
    CODE_UPDATE=0
else
    BASE=$(git_ merge-base "$OLD_SHA" "$NEW_SHA")
    if [ "$BASE" = "$NEW_SHA" ]; then
        # HEAD contains the remote: someone committed here and has not pushed yet. That is not a
        # divergence and not an error — there is simply nothing upstream to take. Found by
        # running this on a box with an unpushed commit, where the divergence branch below fired
        # instead and reported a failed unit every five minutes.
        log "local is ahead of origin/$BRANCH by $(git_ rev-list --count "$NEW_SHA..$OLD_SHA") commit(s) — nothing to take"
        CODE_UPDATE=0
    elif [ "$BASE" != "$OLD_SHA" ]; then
        # Genuinely diverged: both sides have commits the other lacks. A human problem, and this
        # is the one place where being clever would mean auto-executing code nobody reviewed.
        # Fatal for the config trigger too: a checkout nobody has untangled is not a checkout to
        # restart the box on, whatever the config says.
        die "origin/$BRANCH has diverged from HEAD — refusing to merge. Fix by hand."
    fi
fi

# THE SECOND TRIGGER. Compared against what the RUNNING processes started on, not against the
# last time this script looked, which is why the stamp is written down in section 6 next to the
# start rather than here.
CONFIG_NOW=$(config_fingerprint)
CONFIG_WAS=$(cat "$CONFIG_STAMP" 2>/dev/null || echo "")
CONFIG_CHANGED=0
CONFIG_UNSTAMPED=0
CHANGED_LIST=
for _f in $WATCHED_FILES; do
    _was=$(fingerprint_of "$_f" "$CONFIG_WAS")
    if [ -z "$_was" ]; then
        # NEVER STAMPED IS NOT A CHANGE. It is a fresh machine, a deleted stamp, a file just
        # added to WATCHED_FILES, or the single-hash stamp this script wrote before secrets.env
        # joined the set. None of those is somebody editing something, and treating them as one
        # spends a whole drain-and-restart on every box for a file nobody touched.
        CONFIG_UNSTAMPED=1
    elif [ "$_was" != "$(fingerprint_of "$_f" "$CONFIG_NOW")" ]; then
        CONFIG_CHANGED=1
        CHANGED_LIST="${CHANGED_LIST:+$CHANGED_LIST and }$_f"
    fi
done
unset _f _was
if [ "$CONFIG_UNSTAMPED" = 1 ]; then
    # Recorded HERE as well as in section 6, because a pass that stops at "nothing to do" never
    # reaches section 6 — and a file that is never stamped is a file whose edits never trigger.
    if [ "$DRY_RUN" = 1 ]; then
        log "would record the current fingerprints; no restart is owed for them"
    else
        log "recording the current fingerprints; no restart is owed for them"
        printf '%s\n' "$CONFIG_NOW" > "$CONFIG_STAMP"
    fi
fi

if [ "$CODE_UPDATE" = 0 ] && [ "$CONFIG_CHANGED" = 0 ]; then
    log "already current at $(printf %.12s "$OLD_SHA"), watched files unchanged — nothing to do"
    exit 0
fi
if [ "$CODE_UPDATE" = 1 ]; then
    log "update available: $(printf %.12s "$OLD_SHA") -> $(printf %.12s "$NEW_SHA")"
    git_ log --oneline "$OLD_SHA..$NEW_SHA" | sed 's/^/    /'
fi
if [ "$CONFIG_CHANGED" = 1 ]; then
    log "$CHANGED_LIST changed in $CONFIG_DIR since the services started — restarting to pick it up"
fi

if [ "$DRY_RUN" = 1 ]; then
    log "--dry-run: stopping here. Would drain, stop, merge anything new, re-run setup and restart."
    exit 0
fi

# ------------------------------------------------------------------------------------------
# 3. drain, then stop
# ------------------------------------------------------------------------------------------
# SAY SO FIRST, before the drain and before anything else observable happens. Every exit above
# this line is a pass that changed nothing, and every line below it is an update in progress;
# the flag is exactly that boundary, written where it is so a reader cannot see a drained box
# or a stopped target without also seeing the reason for it.
#
# Never fatal. An unwritable config dir is a real state on a broken box, and the update matters
# more than the label on it -- the cost of failing here is a status page that says `checking`
# through an update, which is what it said before this flag existed.
{
    printf 'started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    # ONE LINE, and short, because a status reader puts it on a page beside the word `updating`
    # and truncates what will not fit. Both triggers can fire on the same pass.
    if [ "$CODE_UPDATE" = 1 ] && [ "$CONFIG_CHANGED" = 1 ]; then
        printf 'reason=%.12s -> %.12s, and %s changed\n' "$OLD_SHA" "$NEW_SHA" "$CHANGED_LIST"
    elif [ "$CODE_UPDATE" = 1 ]; then
        printf 'reason=%.12s -> %.12s\n' "$OLD_SHA" "$NEW_SHA"
    else
        printf 'reason=%s changed since the services started\n' "$CHANGED_LIST"
    fi
} 2>/dev/null > "$APPLY_FLAG" \
    || log "WARNING: could not write $APPLY_FLAG; this update will not be visible to ffstatus"

# Never fatal. A commit that breaks ffwatch.py also breaks `ffwatch drain`, and an updater that
# treats that as fatal can never install the fix.
# BOTH LANES, AND AN IDLE CONTAINER IS NOT WORK. Until 2026-08-31 this drained ffbox only:
# ffgithubrunners was never told, so a CI job could be mid-Unity-import while the merge replaced
# the task script bind-mounted under it. The two flags are independent and both are lifted by
# lift_drain, including on a crash.
#
# The rule the rest of this section implements:
#
#   * a container that is merely WAITING is destroyed immediately. A staged agent container and an
#     idle CI runner hold a workspace and no work; they cost 22 GiB each to keep and nothing to
#     recreate, and keeping one across a merge is how a container ends up serving a turn through
#     the OLD task script -- its mounts point at inodes the merge replaced.
#   * a container that has been ASKED TO DO SOMETHING is never killed. It gets the window, and
#     so does the HOST-SIDE work behind it -- the harvest, the branch push, the pull request,
#     the reply. Those run in an ffwatch thread after the container exits and do not survive a
#     `systemctl stop`, so "the containers are down" is not "safe to stop".
#   * at the end of the window the update GOES AHEAD, and it does it with `docker stop`, giving
#     every straggler its full grace to harvest and hand its Unity seat back, then giving the
#     host a bounded window to publish what those stops just released. Until 2026-09-01 the
#     update stood down instead and left the box on old code for as long as it stayed busy.
if [ -r "$FFWATCH" ]; then
    log "draining the agent lane — no new containers"
    as_owner python3 "$FFWATCH" drain || log "WARNING: could not set the agent drain flag"
else
    log "WARNING: no readable $FFWATCH — skipping the agent drain"
fi
if [ -x "$FFGHR" ]; then
    log "draining the CI lane — running jobs finish, no slot takes new work"
    as_owner "$FFGHR" drain >/dev/null 2>&1 || log "WARNING: could not set the CI drain flag"
else
    log "WARNING: no executable $FFGHR — skipping the CI drain"
fi

# The waiting ones go now. Both are cheap to recreate and neither is doing anything.
#
# NOTHING HERE DROPS THE AGENT POOL, because `ffwatch drain` above already did: it destroys every
# IDLE staged container as part of draining and says so ("draining: destroyed N idle staged
# container(s)"). This used to call `ffwatch pool drop` as well, which found nothing every time
# -- one line of output in the journal claiming a job the previous line had already done. One
# place, not two.
#
# IDLE, not every one of them. A dispatched pool container keeps its `ffbox.pool` label, so a
# sweep by label takes the container serving a turn as well; on 2026-09-01 that deleted a live
# run's spool directory and the harness reported a verified, finished turn as "the run failed".
# ffwatch decides by `out/owner` now. Do not add a by-label sweep back in here.
for _c in $(docker_ ps --filter label=ffghr.slot --format '{{.Names}}' 2>/dev/null); do
    # `docker top | grep Runner.Worker` is the same test slot.sh's own reaper uses, and it reads
    # the container rather than a marker file a SIGKILLed supervisor may have left behind.
    if docker_ top "$_c" -o pid,comm 2>/dev/null | grep -q 'Runner\.Worker'; then
        log "$_c is running a job — leaving it alone"
    else
        log "destroying idle runner $_c; it holds a workspace and no job"
        docker_ rm -f "$_c" >/dev/null 2>&1 || log "WARNING: could not remove $_c"
    fi
done
unset _c

# WAIT FOR THE HOST, NOT FOR THE CONTAINERS.
#
# WHAT CHANGED, AND WHY THE LOOP GOT SO MUCH SMALLER. This used to count busy containers and wait
# for them, up to an hour, and then force-stop whatever was left. It waited because a container
# did not survive a restart: ffbox was a child of ffwatch, in its cgroup, so `systemctl stop`
# signalled it and its trap stopped the container. That is fixed -- ffbox detaches, the ceilings
# are a file, and finish_runs picks the run up on the other side -- so a container is simply not
# this script's business any more. A twenty-hour job neither blocks an update nor is interrupted
# by one.
#
# WHAT IS STILL WORTH WAITING FOR is the HOST-SIDE TAIL: a turn whose container has already
# exited and whose harvest, push, pull request or reply is in a thread right now. A thread does
# not survive a stop, so landing in the middle of one loses a push that was seconds from
# finishing. `ffwatch quiet --host-only` is exactly that question, and it is normally answered
# immediately.
#
# STOP_RUNNING PUTS THE OLD BEHAVIOUR BACK for one pass. A security fix, an image change, a
# commit that has to apply to what is running right now: for those, waiting and then stopping is
# the correct thing, and it is a deliberate act rather than the default.
_deadline=$(( $(date +%s) + DRAIN_TIMEOUT ))
_forced=0
while :; do
    _busy=0
    if [ "$STOP_RUNNING" = 1 ]; then
        # THE OLD RULE, ARMED ON PURPOSE. Count what is working and wait for it. A CI container
        # with no Runner.Worker is idle and goes now; an agent container is counted busy, because
        # the idle staged ones are already gone and a drained ffwatch stages no more.
        for _c in $(docker_ ps --filter label=ffbox.workload --format '{{.Names}}' 2>/dev/null); do
            case "$_c" in
                ffghr-*)
                    if docker_ top "$_c" -o pid,comm 2>/dev/null | grep -q 'Runner\.Worker'; then
                        _busy=$((_busy + 1))
                    else
                        log "destroying idle runner $_c that appeared after the sweep"
                        docker_ rm -f "$_c" >/dev/null 2>&1 || :
                    fi ;;
                *)  _busy=$((_busy + 1)) ;;
            esac
        done
    fi
    if [ "$_busy" -gt 0 ]; then
        log "stop-running is armed: waiting for $_busy working container(s) to finish"
    elif [ ! -r "$FFWATCH" ]; then
        # No ffwatch to ask. Same reasoning as the skipped drain above: a broken ffwatch.py is
        # exactly when an update has to land.
        break
    elif _left=$(as_owner python3 "$FFWATCH" quiet --host-only 2>/dev/null); then
        log "the host has finished publishing; containers are not waited on"
        break
    else
        log "waiting for the host: ${_left:-work still in flight}"
    fi
    if [ "$(date +%s)" -ge "$_deadline" ]; then
        log "still not quiet after ${DRAIN_TIMEOUT}s — going ahead."
        _forced=1
        if [ "$STOP_RUNNING" = 1 ]; then
            # SOFT, EVEN WHEN FORCING. Every container here is PID 1 running a task whose trap
            # harvests the workspace out of a tmpfs and hands the Unity licence seat back.
            # `rm -f` would run neither, and the tmpfs is the only copy of the work.
            for _c in $(docker_ ps --filter label=ffbox.workload --format '{{.Names}}' 2>/dev/null); do
                log "stopping $_c — up to ${FORCE_STOP_GRACE}s for its harvest and licence return"
                docker_ stop --timeout "$FORCE_STOP_GRACE" "$_c" >/dev/null 2>&1 \
                    || log "WARNING: could not stop $_c"
            done
            _settle=$(( $(date +%s) + FORCE_SETTLE ))
            while [ -r "$FFWATCH" ] && [ "$(date +%s)" -lt "$_settle" ]; do
                if _left=$(as_owner python3 "$FFWATCH" quiet --host-only 2>/dev/null); then
                    log "the host settled after the forced stop"
                    break
                fi
                log "settling: ${_left:-work still in flight}"
                sleep 5
            done
        fi
        break
    fi
    sleep 5
done
unset _busy _c _deadline _left _settle
if [ "$_forced" = 1 ]; then
    log "proceeding with the update without waiting further"
fi

# ------------------------------------------------------------------------------------------
# 3a. what this box is carrying across the update
# ------------------------------------------------------------------------------------------
# AN OPERATOR READING AN UPDATE LOG HAS TO BE ABLE TO SEE WHAT SURVIVED IT. A container that runs
# through a restart is the intended behaviour and it is also the thing most likely to be blamed
# for anything odd afterwards, so it is named here rather than left to be discovered in
# `docker ps`.
#
# AND ONE CANNOT BE CARRIED FOR EVER. A container older than MAX_CONTAINER_AGE has outlived every
# ceiling that could legitimately apply to it, which means nothing else is bounding it; an update
# is the last thing on the box that would notice. Stopped softly, like everything else here.
for _c in $(docker_ ps --filter label=ffbox.workload --format '{{.Names}}' 2>/dev/null); do
    _started=$(docker_ inspect -f '{{.State.StartedAt}}' "$_c" 2>/dev/null || echo "")
    _age=0
    if [ -n "$_started" ]; then
        _epoch=$(date -d "$_started" +%s 2>/dev/null || echo "")
        [ -n "$_epoch" ] && _age=$(( $(date +%s) - _epoch ))
    fi
    if [ "$_age" -gt "$MAX_CONTAINER_AGE" ]; then
        log "$_c has been up ${_age}s, past the ${MAX_CONTAINER_AGE}s ceiling — stopping it;"
        log "  nothing else is bounding it, so it is not carried across another update"
        docker_ stop --timeout "$FORCE_STOP_GRACE" "$_c" >/dev/null 2>&1 \
            || log "WARNING: could not stop $_c"
    else
        log "leaving $_c running (up ${_age}s); it keeps working across this update"
    fi
done
unset _c _started _age _epoch

log "stopping ffbox.target"
sudo_systemctl stop ffbox.target || log "WARNING: stop reported a failure; continuing"

# ------------------------------------------------------------------------------------------
# 4. the merge
# ------------------------------------------------------------------------------------------
# Skipped outright on a config-only pass: there is nothing upstream to take, and the rest of
# this script — setup, restart — is the same work either way.
if [ "$CODE_UPDATE" = 1 ]; then
    git_ merge --ff-only --quiet "$NEW_SHA" || die "fast-forward merge failed"
    log "checkout is now at $(printf %.12s "$(git_ rev-parse HEAD)")"
else
    log "no new commits; the checkout stays at $(printf %.12s "$OLD_SHA")"
fi

# ------------------------------------------------------------------------------------------
# 5. re-run setup
# ------------------------------------------------------------------------------------------
# TWO CALLS, NOT A LIST OF TRIGGERS. This used to grep the diff for paths that "mean" something —
# a Dockerfile change means rebuild, a plugins/ change means registerAgents — which is a second,
# hand-maintained model of what setup.sh already knows, and it is wrong the moment a commit
# moves a file or adds a stage. Worse, it could only ever react to what CHANGED IN GIT: a config
# key added by a commit, or a channel somebody added to the watch block by hand, has no diff to
# match and never got applied.
#
# So run the real thing. Every stage is idempotent and no-ops when it is already satisfied:
# Docker and ZFS are one-time provisioning, the image build is a cached docker build, the warm
# step extracts CI's Library/ and skips when golden's is already newer, and stage 5 is setdefault
# the whole way down.
#
# THAT CLAIM USED TO BE FALSE and it is worth recording why. It said the warm "skips outright when
# golden already has a Library/". 04-warmLibrary.sh logged "already present ... re-importing to
# pick up the changes just pulled" and fell through with no exit, so every commit opened the
# editor: ~/ffbox-runs held twelve warm-* directories between 2026-08-16 and 2026-08-28. Since the
# warm became an extract there is no editor to open and the skip is a real one. On a machine that is already set up this is a few seconds and a lot of "already
# exists"; on one that is behind, it is exactly the commands a human would have run.
#
# WHAT IT WILL NOT DO. --non-interactive makes setup.sh skip the stages that need root — Docker,
# ZFS, and installing the units into /etc/systemd/system — rather than sit on a sudo prompt with
# nobody there. It prints what it skipped, and that goes to the journal. So a commit that changes
# a unit template is fetched, merged and running everywhere except the units, until somebody runs
# `sudo sh ffbox/06-services.sh --install`. That is the deliberate cost of the updater not
# holding root: the alternative is a sudoers rule for writing /etc/systemd/system, which is root.
#
# Non-fatal in every direction. A setup stage that fails must not stop the restart below — the
# machine running slightly stale supporting state beats the machine not running.
log "re-running setup (idempotent; root-only stages are skipped)"
_setup_out=$(mktemp)
if sh "$REPO/ffbox/setup.sh" --non-interactive > "$_setup_out" 2>&1; then
    sed 's/^/    /' "$_setup_out"
else
    sed 's/^/    /' "$_setup_out"
    log "WARNING: setup.sh exited non-zero; continuing into the restart"
fi
rm -f "$_setup_out"

# THE RUNNERS' SETUP IS A SECOND REAL THING, and it is here for the same reason the first one is:
# ffgithubrunners lives in this tree, its non-root stages are idempotent, and without this call a
# commit that changes the CI egress allowlist, the runner networks or the git mirror is fetched,
# merged, and then not applied to anything until a human remembers. The image itself is already
# covered — 03-build.sh above builds the one image both systems share — so what this adds is the
# fence and the mirror.
#
# --skip-image-build because 03-build.sh above has just built that exact tag from that exact
# Dockerfile; a second cached build changes nothing and costs a minute and a half with ffbox
# stopped. If ffbox's build ever moves off this daemon or off this tag, drop the flag — a missing
# image is not silent, slot.sh's preflight names it.
#
# --skip-github because stage 4 verifies the credential by minting a real JIT config and deleting
# the runner it created. That is the right check when a human is setting a machine up and pointless
# noise on the org's runner list once per commit; the credential does not change with a push.
#
# NOTHING HERE MAY DISTURB A RUNNING JOB. ffgithubrunners is NOT drained above — only ffbox is —
# so a CI job may well be in flight while this runs. That is what the fingerprint guards in
# ffbox-egress.sh and 03-image.sh are for: `up` on an unchanged fence or mirror leaves the
# container alone rather than recreating it under a job that is mid-fetch. If either ever goes
# back to an unconditional recreate, this call has to go with it.
if [ -x "$REPO/ffbox/runners/setup.sh" ] || [ -r "$REPO/ffbox/runners/setup.sh" ]; then
    log "re-running the runners' setup (idempotent; root-only stages are skipped)"
    _rsetup_out=$(mktemp)
    if sh "$REPO/ffbox/runners/setup.sh" --non-interactive --skip-github --skip-image-build \
            > "$_rsetup_out" 2>&1; then
        sed 's/^/    /' "$_rsetup_out"
    else
        sed 's/^/    /' "$_rsetup_out"
        log "WARNING: runners/setup.sh exited non-zero; continuing into the restart"
    fi
    rm -f "$_rsetup_out"
fi

# ------------------------------------------------------------------------------------------
# 6. resume
# ------------------------------------------------------------------------------------------
# Before the start, not after: ffbox is stopped at this moment, so nothing can observe the
# window, and a start that fails still leaves the machine ready to run.
lift_drain
# STAMPED HERE, a moment before the processes that read it start, and not back where we decided
# to restart. The drain can take an hour, and a config edited during that hour is picked up by
# THIS start; stamping the older fingerprint would spend a second full restart on settings that
# are already live. Written before the start rather than after, so a start that fails does not
# leave the box owing a restart it will never be told about.
# Never fatal, and for the usual reason: ffbox is STOPPED at this line, and an unwritable stamp
# must not be what keeps it that way. The cost of failing here is one redundant restart.
config_fingerprint > "$CONFIG_STAMP" \
    || log "WARNING: could not write $CONFIG_STAMP; the next tick will restart again"
# Beside the fingerprint and for the same reason: written while ffbox is stopped, a moment
# before the start, so the stamp and the processes reading the new code date from the same
# moment. Never fatal — an unwritable stamp costs one blank field on a status page, which is
# not a reason to leave the box stopped.
if [ "$CODE_UPDATE" = 1 ]; then
    printf '%s %s\n' "$(date +%s)" "$(git_ rev-parse HEAD)" > "$APPLIED_STAMP" \
        || log "WARNING: could not write $APPLIED_STAMP; ffstatus will not know when this landed"
fi
log "starting ffbox.target"
sudo_systemctl start ffbox.target || log "WARNING: start reported a failure"

# What is ACTUALLY running, not what we asked for: `start` exits 0 for a Wants= member that
# died, and the listener is expected to fail on a machine with no bot token.
rc=0
for u in ffdiscord-listener.service ffwatch.service ffweb.service; do
    state=$(systemctl is-active "$u" 2>/dev/null || echo inactive)
    printf '  %-28s %s\n' "$u" "$state"
    [ "$u" = "ffwatch.service" ] && [ "$state" != active ] && rc=1
done
if [ "$CODE_UPDATE" = 1 ]; then
    log "updated $(printf %.12s "$OLD_SHA") -> $(printf %.12s "$NEW_SHA")"
else
    log "restarted on a config change; still at $(printf %.12s "$OLD_SHA")"
fi
[ "$rc" = 0 ] || log "ERROR: ffwatch did not come back. The timer keeps running: the next good commit will land on its own."
exit "$rc"
