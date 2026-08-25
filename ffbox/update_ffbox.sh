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
FLAG_LIFTED=0
lift_drain() {
    [ "$FLAG_LIFTED" = 1 ] && return 0
    FLAG_LIFTED=1
    [ "$DRY_RUN" = 1 ] && return 0
    # By hand rather than through ffwatch: this also has to work when the commit we just
    # installed is the reason ffwatch.py will not run.
    rm -f "$DRAIN_SWITCH" 2>/dev/null || :
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
if [ -r "$FFWATCH" ]; then
    log "draining (up to ${DRAIN_TIMEOUT}s) — no new containers, finishing what is running"
    if as_owner python3 "$FFWATCH" drain --wait --timeout "$DRAIN_TIMEOUT"; then
        log "drained: nothing in flight"
    else
        log "WARNING: drain did not finish cleanly — stopping anyway (runs are requeued)"
    fi
else
    log "WARNING: no readable $FFWATCH — skipping the drain"
fi

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
# ONE CALL, NOT A LIST OF TRIGGERS. This used to grep the diff for paths that "mean" something —
# a Dockerfile change means rebuild, a plugins/ change means registerAgents — which is a second,
# hand-maintained model of what setup.sh already knows, and it is wrong the moment a commit
# moves a file or adds a stage. Worse, it could only ever react to what CHANGED IN GIT: a config
# key added by a commit, or a channel somebody added to the watch block by hand, has no diff to
# match and never got applied.
#
# So run the real thing. Every stage is idempotent and no-ops when it is already satisfied:
# Docker and ZFS are one-time provisioning, the image build is a cached docker build, the Unity
# warm skips outright when golden already has a Library/, and stage 5 is setdefault the whole
# way down. On a machine that is already set up this is a few seconds and a lot of "already
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
