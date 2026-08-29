#!/bin/sh
# reap.sh — clean up after a supervisor that did not get to finish.
#
# slot.sh tears down on every exit path it can see. What it cannot see is a reboot or a SIGKILL,
# and either leaves a registration on the org and possibly a container on the daemon. This sweeps
# both, every 15 minutes.
#
# THE DAEMON IS SHARED WITH FFBOX, so everything here is name-scoped to ffghr-*. There is no
# `docker system prune` and no sweep of dangling anything: an image or a container this does not
# recognise belongs to ffbox, and the correct action is to leave it alone.
#
# LEAVE ANYTHING YOU CANNOT EXPLAIN, AND SAY SO. A reaper that deletes what it does not understand
# is worse than one that occasionally leaves something behind, because the thing it does not
# understand is sometimes a job that is running.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

DRY=0
QUIET=0
case "${1:-}" in
    --dry-run) DRY=1 ;;
    --quiet)   QUIET=1 ;;
    --help|-h) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    "")        ;;
    *)         echo "reap.sh: unknown option $1" >&2; exit 2 ;;
esac

. "$HERE/lib/config.sh"
. "$HERE/lib/gh.sh"

say()  { [ "$QUIET" = 1 ] || printf '==> %s\n' "$*"; }
skip() { [ "$QUIET" = 1 ] || printf '    %s\n' "$*"; }
act()  { printf '    %s\n' "$*"; }   # always printed: this is what actually changed

docker version >/dev/null 2>&1 || { echo "reap.sh: cannot reach $DOCKER_SOCK" >&2; exit 1; }

HOST=$(hostname -s 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo host)

# Containers this daemon currently has, ffghr-* only, running or not.
CONTAINERS=$(docker ps -a --filter "name=^ffghr-" --format '{{.Names}}' 2>/dev/null || true)

# --- containers ------------------------------------------------------------------------------------
#
# A supervisor always removes its own container, so anything ffghr-* still here either belongs to a
# live supervisor or is an orphan. The container says which: slot.sh labels it with its own pid,
# and a pid whose cmdline is no longer a slot.sh is a supervisor that died without tearing down.
#
# A container with NO label is left alone and reported. It predates this labelling, or something
# else made it, and either way "I cannot explain this" means "do not delete it" — the thing that
# cannot be explained is sometimes a running job.
supervisor_alive() {   # $1 = pid
    [ -n "$1" ] || return 1
    [ -r "/proc/$1/cmdline" ] || return 1
    tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null | grep -q 'slot\.sh'
}

for c in $CONTAINERS; do
    [ "$c" != "$EGRESS_NAME" ] || continue   # the fence is ffghr-* too, and it is not garbage

    pid=$(docker inspect -f '{{index .Config.Labels "ffghr.supervisor.pid"}}' "$c" 2>/dev/null || echo "")
    rid=$(docker inspect -f '{{index .Config.Labels "ffghr.runner.id"}}' "$c" 2>/dev/null || echo "")
    state=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo gone)
    [ "$state" != gone ] || continue

    if [ -z "$pid" ]; then
        act "$c has no supervisor label; leaving it alone (state $state)"
        continue
    fi
    if supervisor_alive "$pid"; then
        skip "$c belongs to live supervisor $pid; leaving it"
        continue
    fi

    if [ "$DRY" = 1 ]; then
        act "would remove orphaned container $c (state $state, dead supervisor $pid)"
        [ -z "$rid" ] || act "would delete its registration $rid"
        continue
    fi
    docker rm -f "$c" >/dev/null 2>&1 \
        && act "removed orphaned container $c (state $state, dead supervisor $pid)" \
        || act "WARNING: could not remove $c"
    # Its registration goes with it. Waiting for the pass below would work only once GitHub marks
    # the runner offline, which takes minutes.
    if [ -n "$rid" ]; then
        gh_delete_runner "$rid" >/dev/null 2>&1 \
            && act "deleted its registration $rid" \
            || act "WARNING: could not delete registration $rid"
    fi
done

# --- registrations ------------------------------------------------------------------------------------
#
# Delete org runners that are OURS, OFFLINE, and have no container here. Three conditions, and all
# three matter:
#
#   ours      the ffgithubrunners label and this host's name in the nonce. Another machine's
#             runners, and the four hand-made Loth2400-N ones, are never in scope.
#   offline   an online runner is either working or waiting for work. Never delete one.
#   no container   a registration whose container is still here belongs to a live slot.
RUNNERS=$(gh_list_runners) || { echo "reap.sh: could not list runners" >&2; exit 1; }

printf '%s\n' "$RUNNERS" | while IFS=' ' read -r id status name labels; do
    [ -n "${id:-}" ] || continue

    case ",$labels," in
        *",ffgithubrunners,"*) ;;
        *) continue ;;
    esac
    case "$name" in
        "ffghr-$HOST-"*) ;;
        *) skip "$name carries our label but not this host's name; leaving it"; continue ;;
    esac
    [ "$status" = offline ] || { skip "$name is $status; leaving it"; continue; }

    if docker inspect "$name" >/dev/null 2>&1; then
        skip "$name is offline but its container is still here; leaving it"
        continue
    fi

    if [ "$DRY" = 1 ]; then
        act "would delete registration $id ($name)"
    elif gh_delete_runner "$id"; then
        act "deleted registration $id ($name)"
    else
        act "WARNING: could not delete registration $id ($name)"
    fi
done

# --- the workspace cache -------------------------------------------------------------------------
#
# Two jobs, and only two. design/ffcache_design.txt sections 8 and 9.
#
# THIS DOES NOT PROMOTE. A staging directory left by a supervisor that was SIGKILLed may well hold
# a perfectly good archive, and promoting it would be a small win. It is still the wrong thing for
# a reaper to do: this file's rule is that it collects garbage and never creates state, and
# promoting on behalf of a job whose teardown never ran is creating state from something nobody
# watched finish. slot.sh promotes; reap.sh sweeps.
#
# What it does do is bound the cache when slots stop exiting cleanly, which is the failure the
# fifteen-minute timer exists for.

# A staging directory belongs to a slot number, and the supervisor for that slot is a `slot.sh N`
# in the process table. Same shape as supervisor_alive above, matching the slot rather than a pid,
# because a staging directory carries no label to record one.
slot_supervisor_alive() {   # $1 = slot number
    for _p in /proc/[0-9]*; do
        [ -r "$_p/cmdline" ] || continue
        case "$(tr '\0' ' ' < "$_p/cmdline" 2>/dev/null)" in
            *"slot.sh $1 "*) return 0 ;;
        esac
    done
    return 1
}

if ! ffghr_cache_ready; then
    skip "workspace cache not provisioned or disabled; nothing to sweep"
else
    say "workspace cache"
    for d in "$FFGHR_CACHE_STAGING"/slot-*; do
        [ -d "$d" ] || continue
        n=${d##*/slot-}
        case "$n" in
            ''|*[!0-9]*) act "$d is not a slot staging directory; leaving it alone"; continue ;;
        esac
        if slot_supervisor_alive "$n"; then
            skip "staging for slot $n belongs to a live supervisor; leaving it"
            continue
        fi
        if [ "$DRY" = 1 ]; then
            act "would clear stale staging $d (no live supervisor for slot $n)"
            continue
        fi
        rm -rf "$d" && act "cleared stale staging for slot $n" \
                    || act "WARNING: could not clear $d"
    done

    _before=$(find "$FFGHR_CACHE_ENTRIES" -maxdepth 1 -type f -name '*@*.tar' 2>/dev/null | wc -l)
    if [ "$DRY" = 1 ]; then
        [ "$_before" -le "${CACHE_KEEP:-10}" ] \
            && skip "$_before entries, keep is ${CACHE_KEEP:-10}; nothing to prune" \
            || act "would prune $((_before - ${CACHE_KEEP:-10})) of $_before entries"
    else
        ffghr_cache_with_lock ffghr_cache_prune 2>&1 \
            | while IFS= read -r _line; do act "$_line"; done || true
        skip "$(find "$FFGHR_CACHE_ENTRIES" -maxdepth 1 -type f -name '*@*.tar' 2>/dev/null | wc -l) entries, $(du -sh "$FFGHR_CACHE_ENTRIES" 2>/dev/null | cut -f1) (keep ${CACHE_KEEP:-10})"
    fi
fi

say "sweep complete"
