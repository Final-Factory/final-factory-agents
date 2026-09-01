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
DRAIN_TIMEOUT=${FFBOX_DRAIN_TIMEOUT:-7200}
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
LOCK=$CONFIG_DIR/update.lock

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
# A crash, or systemd's TimeoutStartSec, must not leave the machine drained and silent.
trap 'lift_drain' EXIT HUP INT TERM

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

# ------------------------------------------------------------------------------------------
# 2. the three reasons to do nothing
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
if [ "$OLD_SHA" = "$NEW_SHA" ]; then
    log "already current at $(printf %.12s "$OLD_SHA") — nothing to do"
    exit 0
fi
BASE=$(git_ merge-base "$OLD_SHA" "$NEW_SHA")
if [ "$BASE" = "$NEW_SHA" ]; then
    # HEAD contains the remote: someone committed here and has not pushed yet. That is not a
    # divergence and not an error — there is simply nothing upstream to take. Found by running
    # this on a box with an unpushed commit, where the divergence branch below fired instead
    # and reported a failed unit every five minutes.
    log "local is ahead of origin/$BRANCH by $(git_ rev-list --count "$NEW_SHA..$OLD_SHA") commit(s) — nothing to take"
    exit 0
fi
if [ "$BASE" != "$OLD_SHA" ]; then
    # Genuinely diverged: both sides have commits the other lacks. A human problem, and this is
    # the one place where being clever would mean auto-executing code nobody reviewed.
    die "origin/$BRANCH has diverged from HEAD — refusing to merge. Fix by hand."
fi
log "update available: $(printf %.12s "$OLD_SHA") -> $(printf %.12s "$NEW_SHA")"
git_ log --oneline "$OLD_SHA..$NEW_SHA" | sed 's/^/    /'

if [ "$DRY_RUN" = 1 ]; then
    log "--dry-run: stopping here. Would drain, stop, merge, act on the diff and restart."
    exit 0
fi

# ------------------------------------------------------------------------------------------
# 3. drain, then stop
# ------------------------------------------------------------------------------------------
# Never fatal. A commit that breaks ffwatch.py also breaks `ffwatch drain`, and an updater that
# treats that as fatal can never install the fix.
# BOTH LANES, AND AN IDLE CONTAINER IS NOT WORK. Until 2026-08-31 this drained ffbox only:
# ffgithubrunners was never told, so a CI job could be mid-Unity-import while the merge replaced
# the task script bind-mounted under it. The two flags are independent and both are lifted by
# lift_drain, including on a crash.
#
# The rule the rest of this section implements:
#
#   * a container that has been ASKED TO DO SOMETHING is never killed. It finishes, and if it has
#     not finished by the end of the window the UPDATE gives way, not the run.
#   * a container that is merely WAITING is destroyed immediately. A staged agent container and an
#     idle CI runner hold a workspace and no work; they cost 22 GiB each to keep and nothing to
#     recreate, and keeping one across a merge is how a container ends up serving a turn through
#     the OLD task script -- its mounts point at inodes the merge replaced.
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
# staged container as part of draining and says so ("draining: destroyed N staged container(s)").
# This used to call `ffwatch pool drop` as well, which found nothing every time -- one line of
# output in the journal claiming a job the previous line had already done. One place, not two.
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

# WAIT FOR WORK, NOT FOR EVERYTHING. What is left after the sweep above is containers with a job
# in them. They are given the whole window, and if they are still going at the end of it the
# update stands down: the timer comes back in five minutes and nothing was interrupted.
_deadline=$(( $(date +%s) + DRAIN_TIMEOUT ))
while :; do
    _busy=0
    for _c in $(docker_ ps --filter label=ffbox.workload --format '{{.Names}}' 2>/dev/null); do
        _busy=$((_busy + 1))
    done
    if [ "$_busy" -eq 0 ]; then
        break
    fi
    if [ "$(date +%s)" -ge "$_deadline" ]; then
        log "$_busy container(s) are still working after ${DRAIN_TIMEOUT}s."
        log "STANDING DOWN rather than killing them; the next trigger will try again."
        exit 0
    fi
    log "waiting for $_busy working container(s) to finish"
    sleep 15
done
unset _busy _c _deadline
log "nothing is running; safe to stop"

log "stopping ffbox.target"
sudo_systemctl stop ffbox.target || log "WARNING: stop reported a failure; continuing"

# ------------------------------------------------------------------------------------------
# 4. the merge
# ------------------------------------------------------------------------------------------
git_ merge --ff-only --quiet "$NEW_SHA" || die "fast-forward merge failed"
log "checkout is now at $(printf %.12s "$(git_ rev-parse HEAD)")"

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
log "updated $(printf %.12s "$OLD_SHA") -> $(printf %.12s "$NEW_SHA")"
[ "$rc" = 0 ] || log "ERROR: ffwatch did not come back. The timer keeps running: the next good commit will land on its own."
exit "$rc"
