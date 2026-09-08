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
# live supervisor or is an orphan. The container says which, and WHICH QUESTION TO ASK depends on
# what kind of thing owns it -- which is why there is an `ffghr.owner` label as well as a pid.
#
#   ffghr.owner=slot.sh     one supervisor per container, living exactly as long as it. Its pid is
#                           an exact answer and `ffghr.supervisor.pid` carries it.
#   ffghr.owner=ffwatch     one daemon for every container, which RESTARTS on every code update and
#                           every config edit while its containers keep running. A pid here would
#                           go stale on every update and make every adopted container read as an
#                           orphan, which is a reaper deleting live jobs. The question becomes "is
#                           an ffwatch running on this box", and losing precision is the price of
#                           an owner that is allowed to come and go.
#   (no owner label)        a container from before 2026-09-08. Fall back to the pid, which is what
#                           it carries.
#
# A container with NO label of either kind is left alone and reported. It predates both, or
# something else made it, and either way "I cannot explain this" means "do not delete it" — the
# thing that cannot be explained is sometimes a running job.
#
# design/ffbox_ci_in_ffwatch_design.txt section 4b. The ffwatch branch cannot fire until that work
# lands; it is here so that a container started by the daemon is never classified by a pid.
supervisor_alive() {   # $1 = pid
    [ -n "$1" ] || return 1
    [ -r "/proc/$1/cmdline" ] || return 1
    tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null | grep -q 'slot\.sh'
}

# Is ANY ffwatch daemon running as this account? Deliberately not a pid: see above.
ffwatch_alive() {
    for _p in /proc/[0-9]*; do
        [ -r "$_p/cmdline" ] || continue
        case "$(tr '\0' ' ' < "$_p/cmdline" 2>/dev/null)" in
            *ffwatch.py*) return 0 ;;
        esac
    done
    return 1
}

# "live", "orphan" or "unknown", for one container.
owner_state() {   # $1 = owner label, $2 = pid label
    case "${1:-}" in
        ffwatch)
            if ffwatch_alive; then echo live; else echo orphan; fi ;;
        slot.sh|'')
            # slot.sh, or a container from before the owner label existed: the pid is exact.
            if [ -z "${2:-}" ]; then echo unknown
            elif supervisor_alive "$2"; then echo live
            else echo orphan
            fi ;;
        *)
            # An owner this reaper does not know about. NOT an orphan: a newer slot.sh or daemon
            # writing a name this version has never heard of is exactly the case where deleting
            # would be worst, and it happens on every box during an upgrade.
            echo unknown ;;
    esac
}

for c in $CONTAINERS; do
    [ "$c" != "$EGRESS_NAME" ] || continue   # the fence is ffghr-* too, and it is not garbage

    pid=$(docker inspect -f '{{index .Config.Labels "ffghr.supervisor.pid"}}' "$c" 2>/dev/null || echo "")
    owner=$(docker inspect -f '{{index .Config.Labels "ffghr.owner"}}' "$c" 2>/dev/null || echo "")
    rid=$(docker inspect -f '{{index .Config.Labels "ffghr.runner.id"}}' "$c" 2>/dev/null || echo "")
    state=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo gone)
    [ "$state" != gone ] || continue

    case "$(owner_state "$owner" "$pid")" in
        unknown)
            act "$c has no owner this reaper recognises (owner='${owner:-none}'); leaving it alone (state $state)"
            continue ;;
        live)
            skip "$c belongs to a live ${owner:-supervisor}; leaving it"
            continue ;;
    esac

    if [ "$DRY" = 1 ]; then
        act "would remove orphaned container $c (state $state, dead ${owner:-supervisor})"
        [ -z "$rid" ] || act "would delete its registration $rid"
        continue
    fi
    docker rm -f "$c" >/dev/null 2>&1 \
        && act "removed orphaned container $c (state $state, dead ${owner:-supervisor})" \
        || act "WARNING: could not remove $c"
    # Its registration goes with it. Waiting for the pass below would work only once GitHub marks
    # the runner offline, which takes minutes.
    if [ -n "$rid" ]; then
        gh_delete_runner "$rid" >/dev/null 2>&1 \
            && act "deleted its registration $rid" \
            || act "WARNING: could not delete registration $rid"
    fi
done

# --- pool markers ---------------------------------------------------------------------------------
#
# A busy marker says "this container has taken a job", and slot.sh removes its own on every exit
# path it gets to run. A supervisor that was SIGKILLed does not, and the admission count would
# then be reading a marker for a container that no longer exists.
#
# HARMLESS UNTIL THE NAME COMES BACK, which it cannot: the container name carries a random nonce.
# So this is tidiness rather than a fix, and it is cheap. The counting itself already ignores a
# marker with no live container, which is what keeps the failure benign in the meantime.
# BOTH SUFFIXES, ONE LOOP. `.idle` joined `.busy` on 2026-09-02 when the CI lane got two clocks,
# and a per-container file that nothing deletes is a directory that grows for the life of the box.
#
# THE `tr` IS LOAD-BEARING AND IS THE WHOLE REASON THIS LOOP IS SAFE. `docker ps` answers one name
# per LINE, and the membership test below is `case " $LIVE " in *" $cname "*`, which asks for a name
# with a SPACE on each side. A quoted expansion does no word splitting, so newline-separated names
# match only when there is exactly ONE of them: the first name has no space after it, the last none
# before it, and a middle one neither. With two or more runners up, every marker read as "gone" and
# was deleted -- for containers that were RUNNING JOBS. That is not the benign direction the note
# above describes: `ffghr_pool_counts` then counts a busy container as idle, `ffghr_pool_admit` sees
# a pool that is already satisfied, and the lane stops minting runners while it sits under its
# ceiling with no idle registration for GitHub to hand a queued job to. lib-workloads.sh:321 and
# 05-services.sh:136 both flatten the same way; this is the site that forgot.
LIVE=$(docker ps --filter label=ffghr.slot --format '{{.Names}}' 2>/dev/null | tr '\n' ' ' || true)
if [ -d "$FFGHR_STATE_DIR" ]; then
    for m in "$FFGHR_STATE_DIR"/*.busy "$FFGHR_STATE_DIR"/*.idle; do
        [ -e "$m" ] || continue
        kind=${m##*.}
        cname=$(basename -- "$m" ".$kind")
        case " $LIVE " in
            *" $cname "*) skip "$cname is running; keeping its $kind marker"; continue ;;
        esac
        if [ "$DRY" = 1 ]; then
            act "would remove the $kind marker for $cname, which is gone"
        else
            rm -f "$m" && act "removed the $kind marker for $cname, which is gone"
        fi
    done
fi

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

# A STAGING DIRECTORY IS NAMED AFTER ITS CONTAINER SINCE 2026-09-08, so the question "is this one
# still in use" is answered by the daemon rather than by the process table.
#
# THIS USED TO SCAN /proc FOR `slot.sh N`, because the directory was `slot-N` and carried nothing
# else to go on. That was a weaker test than it looked: it asked whether SOME supervisor held that
# slot number, not whether the job whose files these are is still running, and the two stopped
# being the same thing when a slot number stopped meaning a place in the pool. Matching a live
# container by name is exact, needs no /proc walk, and uses the listing this file already has.
staging_container_live() {   # $1 = directory basename, which is a container name
    case " $LIVE " in *" ${1:?} "*) return 0 ;; esac
    return 1
}

if ! ffghr_cache_ready; then
    skip "workspace cache not provisioned or disabled; nothing to sweep"
else
    say "workspace cache"
    for d in "$FFGHR_CACHE_STAGING"/*; do
        [ -d "$d" ] || continue
        n=${d##*/}
        # THE OLD SHAPE, SWEPT ONCE AND THEN FORGOTTEN. A `slot-N` directory belongs to no
        # container under the new rule, so nothing will ever claim it and it would sit there for
        # the life of the box holding up to 16G. Its owner cannot be identified any more, which is
        # exactly why it has to go rather than be left alone: the conservative reading -- "I cannot
        # explain this, so do not delete it" -- would keep it forever.
        # DELETE THIS BRANCH once every box has been through one upgrade; it can only ever match a
        # directory made before 2026-09-08.
        case "$n" in
            slot-*)
                if [ "$DRY" = 1 ]; then
                    act "would clear $d, left by the pre-2026-09-08 slot-numbered staging"
                else
                    rm -rf "$d" && act "cleared $d, left by the pre-2026-09-08 slot-numbered staging" \
                                || act "WARNING: could not clear $d"
                fi
                continue ;;
        esac
        if staging_container_live "$n"; then
            skip "staging for $n belongs to a running container; leaving it"
            continue
        fi
        if [ "$DRY" = 1 ]; then
            act "would clear stale staging $d (no container named $n is running)"
            continue
        fi
        rm -rf "$d" && act "cleared stale staging for $n" \
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
