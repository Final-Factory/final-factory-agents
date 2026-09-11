#!/usr/bin/env bash
#
# ffstatus.sh — what is running on this box right now, and what the pools are trying to hold.
#
# A read-only operator view. It answers the two questions you ask when something looks wrong:
# WHICH containers hold a workspace (both lanes -- agent runs, staged spares, CI jobs), and IS
# EACH POOL AT THE SIZE IT WAS CONFIGURED FOR (idle, max, and the box-wide ceiling above both).
#
#   ffbox/ffstatus.sh            the tables
#   ffbox/ffstatus.sh --watch    refresh every 5s until ^C
#   ffbox/ffstatus.sh --json     the same reading as one JSON document
#
# AND WHAT THE BOX ITSELF HAS LEFT, because every number below is a count of containers and a
# container is not the unit that runs out. RAM is. A workspace is a tmpfs, so it is resident
# memory rather than disk -- Shmem in /proc/meminfo, reported here as `in workspaces` -- and the
# ceiling is set on the assumption of roughly 22 GiB per container. A box at four of ten
# containers and out of memory is a box whose ceiling is wrong, and that is only visible if the
# two are on the same screen.
#
# TWO SOURCES, AND NEITHER IS BOOKKEEPING. Live state comes from `docker ps` on the ffbox daemon
# for the same reason lib-workloads.sh counts there: a supervisor killed with SIGKILL leaves its
# container running and its records stale, and the container is what still holds the RAM. Wanted
# state comes from ~/.config/ffbox/config.json, read with the same coercions ffwatch's load_config
# applies (pool.idle/pool.max, a negative max meaning "no ceiling of my own" -> max_concurrent_runs)
# so this cannot report a target the daemon is not actually working towards.
#
# A DISPATCHED SPARE STILL CARRIES ffbox.workload=pool -- labels are fixed when a container is
# created and dispatch only renames it -- so the lane here is read from the label AND the name:
# `*-pool-*` is a spare waiting, anything else with that label is a turn that started warm.
#
# --json EXISTS SO THERE IS ONE READING OF THE BOX AND NOT TWO. ffweb's /status page runs this
# script rather than growing its own docker parsing beside it: the two would agree on the day
# they were written and drift the first time a label moved, and the version an operator trusts
# would be whichever one they happened to be looking at. Everything below gathers once and then
# renders twice, so the page and the terminal cannot disagree by construction.
set -uo pipefail

DOCKER_HOST=${DOCKER_HOST:-unix://${FFBOX_DOCKER_SOCK:-/run/ffbox-container/docker.sock}}
export DOCKER_HOST
DOCKER=${FFBOX_DOCKER:-docker}
CONFIG=${FFBOX_CONFIG_JSON:-${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}/config.json}
POOL_DIR=${FFBOX_POOL_DIR:-$HOME/ffbox-state/pool}
# WHY A POOL IS SHORT, WHEN THE KEEPER KNOWS. Written by ffwatch's keep_pool (POOL_HOLD_FILE in
# ffwatch.py) beside the spool directories, because the answer lives in that daemon's memory and
# every reading of this box comes through this script instead. `docker ps` can say a pool is below
# its target; only the keeper knows whether that is a missing credential, a ceiling, a memory
# squeeze or a staging that failed -- and until this file existed, finding out meant logging into
# the box and reading the journal.
POOL_HOLD=${FFBOX_POOL_HOLD:-$(dirname -- "$POOL_DIR")/pool-hold.json}
# PAST THIS MANY SECONDS a recorded reason is reported as stale rather than as the answer, because
# a keeper that has stopped looking is itself the likeliest reason a pool is empty. Mirrors
# POOL_HOLD_STALE_SECS in ffwatch.py, which is the copy that decides how often the file is
# refreshed; ffweb.py carries the same number for the same reason.
POOL_HOLD_STALE_SECS=${FFBOX_POOL_HOLD_STALE_SECS:-300}
# WHERE THE CI LANE SAYS A RUNNER IS BUSY. ffwatch mints a CI container only when the pool
# needs one -- pool.idle runners registered and waiting, plus one per job in flight -- so an
# idle CI runner is a running container in exactly the way an agent spare is, and `docker ps`
# alone cannot tell the two apart. The marker is what does: written by the daemon's CI pass
# when a container's runner takes a job. Trusted only for a container that is still running,
# which is automatic here because the names come from `docker ps` -- a leftover marker names
# nothing we listed.
CONFIG_HOME=${FFBOX_CONFIG_DIR:-$HOME/.config/ffbox}
FFGHR_STATE=${FFGITHUBRUNNERS_CONFIG_DIR:-$CONFIG_HOME/githubrunners}/state
# THE CI LANE'S DRAIN FLAG, hardcoded relative to the config dir the way update_ffbox.sh
# hardcodes it. The agent lane's is configurable (ffwatch's drain_switch) and comes out of the
# config below; this one has no setting to read.
FFGHR_DRAIN=${FFGITHUBRUNNERS_CONFIG_DIR:-$CONFIG_HOME/githubrunners}/drain
# THE FLAG UPDATE_FFBOX.SH WRITES WHEN AN UPDATE IS ACTUALLY LANDING, hardcoded relative to the
# config dir the way that script hardcodes it. See read_maintenance for why the unit being active
# is not the same question.
FFBOX_APPLYING=$CONFIG_HOME/update.applying
# AND WHEN ONE LAST DID, written by that script's section 6 as `<epoch> <sha>`. The flag above
# says whether the box is changing right now; this says when it last changed, which is the
# question you ask when it is not. The stamp only exists once an update has landed since it was
# invented, which is why every consumer below has an "unknown" case rather than a default.
UPDATE_STAMP=$CONFIG_HOME/update.last-applied
# AND THE FLAG FFWATCH WRITES WHEN ITS CONFIG FAILSAFE IS ON, hardcoded relative to the config
# dir because a setting that says where it lives would be inside the file that does not parse.
# The parse check below is what catches a broken file, and it needs nothing from any daemon; this
# flag carries the half only ffwatch knows -- that it CAME UP on a broken file, is running on
# built-in defaults, and is still refusing to launch after somebody repaired the file, because
# nothing but a restart can make this process read it.
FFWATCH_FAILSAFE=$CONFIG_HOME/config.invalid
# The unit that does the looking. Only its schedule is read here -- `systemctl show` on a timer
# takes no lock and starts nothing, unlike the update lock read_maintenance deliberately avoids.
UPDATE_TIMER=${FFBOX_UPDATE_TIMER:-ffbox-update.timer}

# US, THE UNIT SEPARATOR, RATHER THAN A PIPE. Every field here is a name somebody else chose --
# a container name, a git ref off a label -- and a ref may legally contain most punctuation. A
# separator that cannot appear in the data is one class of mangling that simply cannot happen,
# and it costs one variable.
SEP=$'\x1f'

# THE CLOCK HELPERS, SHARED WITH THE LANES THAT WRITE THE FILES. This script used to parse
# out/staged itself, with a sed per key and a `date -d`, and the CI arm had no parser at all --
# which is how the two lanes' readings start to disagree. Same reason `--json` exists: one reading
# of the box, not two. A checkout without it degrades to a blank TTL column, which is what every
# CI row showed until 2026-09-02 anyway.
FFBOX_LIB_WORKLOADS=${FFBOX_LIB_WORKLOADS:-$(dirname -- "$0")/lib-workloads.sh}
if [ -r "$FFBOX_LIB_WORKLOADS" ]; then
    . "$FFBOX_LIB_WORKLOADS"
else
    ffbox_clock_left() { return 1; }
fi

WATCH=0
INTERVAL=5
JSON=0
while [ $# -gt 0 ]; do
    case "$1" in
        -w|--watch) WATCH=1; shift; case "${1:-}" in ''|-*) ;; *) INTERVAL=$1; shift ;; esac ;;
        -j|--json)  JSON=1; shift ;;
        -h|--help)
            sed -n '3,11p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "ffstatus: unknown option $1" >&2; exit 2 ;;
    esac
done
# A document is a document; there is nothing to redraw. Said rather than silently ignored,
# because a caller that asked for both wanted something this cannot give them.
[ "$JSON" -eq 1 ] && WATCH=0

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "$JSON" -eq 0 ]; then
    B=$'\033[1m'; DIM=$'\033[2m'; GRN=$'\033[32m'; YEL=$'\033[33m'; RED=$'\033[31m'; N=$'\033[0m'
else
    B=; DIM=; GRN=; YEL=; RED=; N=
fi

# --- wanted state -------------------------------------------------------------------------------
#
# The defaults here are ffwatch.py's DEFAULTS and lib-workloads.sh's FFBOX_WORKLOAD_DEFAULT_MAX.
# A box with no config file must still show the numbers it is actually running under.
read_config() {
    python3 - "$CONFIG" <<'PY' 2>/dev/null
import json, os, sys

# WHY THE FILE SAID NOTHING, when the reason is that it could not be read. A config that does
# not parse is {} to every reader on this box -- this one, ffwatch, ffbox, the runners -- so
# every number below would be a built-in default reported as though it were the machine's
# setting. That is the one state this script must not render as an ordinary idle box: nothing
# launches while it lasts (ffbox refuses in its preflight, ffwatch's failsafe refuses in
# schedule), and read_maintenance turns this line into the word on the header.
#
# A MISSING FILE IS NOT AN ERROR. `ffwatch init` seeds one and a box part-way through setup runs
# on the defaults on purpose; only a file that is THERE and unreadable is a fault.
cfg = {}
config_error = ""
try:
    with open(sys.argv[1]) as fh:
        cfg = json.load(fh)
    if not isinstance(cfg, dict):
        config_error = "holds a %s, not a JSON object of settings" % type(cfg).__name__
        cfg = {}
except FileNotFoundError:
    pass
except OSError as exc:
    config_error = "cannot be read: %s" % (exc.strerror or exc)
except ValueError as exc:
    # str() on a JSONDecodeError carries the line and column, which is what an operator needs to
    # go and fix it. Flattened and capped because it is read back through a `key=value` line.
    config_error = "is not valid JSON: %s" % exc
if config_error:
    print("config_error=%s" % " ".join(config_error.split())[:200])

def num(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default

box = max(1, num(cfg.get("max_concurrent_runs"), 6))
print("box_max=%d" % box)

# WHERE A POOL'S BLOCK LIVES: one block per class inside "pools", the same place ffwatch's
# _pool_section reads.
pools = cfg.get("pools")
if not isinstance(pools, dict):
    pools = {}

# (class, default idle, default max, default network) -- ffwatch's per-class DEFAULTS, written
# out rather than derived, for the same reason they are written out there: the classes exist to
# diverge.
for cls, d_idle, d_max, d_net in (("ffagent", 1, -1, "limited"), ("ffdev", 1, 3, "full")):
    block = pools.get(cls)
    if not isinstance(block, dict):
        block = {}
    pool = block.get("pool") or {}
    idle = max(0, num(pool.get("idle"), d_idle))
    cap = num(pool.get("max"), d_max)
    print("%s_idle=%d" % (cls, idle))
    # A negative max means "no ceiling of my own" and is read as max_concurrent_runs, exactly as
    # ffwatch's load_config coerces it -- so the number printed is the one actually enforced.
    print("%s_max=%d" % (cls, box if cap < 0 else cap))
    print("%s_ref=%s" % (cls, block.get("pool_ref") or block.get("base_ref") or "master"))
    # THE POLICY WORD, not the docker network: "limited" is the egress fence and "full" is the
    # open bridge. Anything else falls back to this class's default, exactly as ffwatch's
    # resolve_network_mode does, so what is printed is what a run would actually get.
    net = block.get("network")
    print("%s_net=%s" % (cls, net if net in ("limited", "full") else d_net))

# WHERE THE AGENT LANE'S DRAIN FLAG LIVES. Configurable, so it is read rather than assumed:
# ffwatch's own DEFAULTS carry this path and a box may have moved it.
#
# PRINTED ONLY WHEN THE CONFIG SETS IT. The fallback belongs in the shell, which knows what
# $FFBOX_CONFIG_DIR was pointed at; a default of "~/.config/ffbox/draining" written here looked
# right and sent every lookup to the real home directory even when the caller had moved the
# config dir somewhere else, so a drained agent lane read as running.
_drain = cfg.get("drain_switch")
if _drain:
    print("drain_switch=%s" % os.path.expanduser(_drain))

ci = (cfg.get("githubrunner") or {}).get("pool") or {}
print("ci_idle=%d" % max(0, num(ci.get("idle"), 1)))
print("ci_max=%d" % max(0, num(ci.get("max"), 1)))
PY
}

declare -A CFG=()
while IFS='=' read -r _k _v; do
    [ -n "$_k" ] && CFG["$_k"]=$_v
done < <(read_config)
# An unreadable config is not a reason to print nothing: fall back to the same built-ins.
: "${CFG[box_max]:=6}"
for _c in ffagent ffdev; do
    : "${CFG[${_c}_idle]:=1}"; : "${CFG[${_c}_max]:=${CFG[box_max]}}"
    : "${CFG[${_c}_ref]:=master}"
done
: "${CFG[ci_idle]:=1}"; : "${CFG[ci_max]:=1}"
: "${CFG[drain_switch]:=$CONFIG_HOME/draining}"

# GiB with one decimal, the way `free -h` says it. Integer arithmetic on purpose: this runs on
# every refresh of a --watch, and there is no reason to start awk for a division.
# ROUNDED, NOT TRUNCATED, and the tenth is the reason this is spelled out rather than being a
# division. ffweb renders the same numbers through Python, whose formatting rounds; a shell that
# truncated printed 262.8G beside the page's 262.9G, which is exactly the kind of small
# disagreement that makes an operator stop trusting both readings. Tenths first so the carry at
# .95 lands in the whole number instead of printing a tenth of 10.
human_kb() {
    local kb=${1:-0} tenths
    if [ "$kb" -ge 1048576 ]; then
        tenths=$(( (kb * 10 + 524288) / 1048576 ))
        printf '%d.%01dG' $((tenths / 10)) $((tenths % 10))
    elif [ "$kb" -ge 1024 ]; then
        printf '%dM' $((kb / 1024))
    else
        printf '%dK' "$kb"
    fi
}

# --- why a pool is short ------------------------------------------------------------------------
#
# INTO AN ASSOCIATIVE ARRAY, keyed `<class>.key`, `<class>.reason` and `<class>.since`, plus one
# `checked_at` for the file as a whole. The python does the parsing and the flattening for the
# same reason render_json hands it the quoting: a reason is a sentence somebody else wrote, and a
# newline in one would break the `key=value` loop below into records this script would then read
# as class names.
#
# A MISSING FILE IS AN ORDINARY STATE, not an error. A box whose ffwatch predates this, or whose
# keeper has not finished a pass yet, has no reasons to show -- and every consumer below then
# renders exactly what it rendered before this file existed.
declare -A HOLD=()

read_pool_holds() {
    HOLD=()
    [ -r "$POOL_HOLD" ] || return 0
    while IFS='=' read -r _k _v; do
        [ -n "$_k" ] && HOLD["$_k"]=$_v
    done < <(python3 - "$POOL_HOLD" <<'PY' 2>/dev/null
import json, re, sys

try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        doc = json.load(fh)
except (OSError, ValueError):
    raise SystemExit(0)
if not isinstance(doc, dict):
    raise SystemExit(0)

def flat(value, limit=300):
    return " ".join(str(value).split())[:limit]

checked = doc.get("checked_at")
if isinstance(checked, (int, float)):
    print("checked_at=%d" % int(checked))
pools = doc.get("pools")
if isinstance(pools, dict):
    for cls, hold in pools.items():
        # THE CLASS NAME BECOMES A SHELL ARRAY KEY, so it is checked rather than trusted. Nothing
        # but ffwatch writes this file, and that is an argument for it being well formed -- not
        # an argument for this script being where a file that is not gets to say anything it
        # likes.
        if not isinstance(hold, dict) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", str(cls)):
            continue
        print("%s.key=%s" % (cls, flat(hold.get("key") or "", 40)))
        print("%s.reason=%s" % (cls, flat(hold.get("reason") or "")))
        since = hold.get("since")
        if isinstance(since, (int, float)):
            print("%s.since=%d" % (cls, int(since)))
PY
)
}

# --- what the machine itself has left -----------------------------------------------------------
#
# STRAIGHT OUT OF /proc, with no tool in between. `free` and `uptime` parse differently across
# distributions and neither is present in every container this might be copied into; the files
# they read have had the same format for twenty years.
#
# USED IS TOTAL MINUS AVAILABLE, not total minus free. Free excludes the page cache, which the
# kernel hands back on demand, so it reads as a machine in trouble whenever it is merely warm.
# MemAvailable is the kernel's own answer to "what could a new process actually get", and it
# already accounts for the part of the cache that is pinned.
#
# SHMEM IS THE INTERESTING NUMBER HERE and it is why this section exists at all. Every workspace
# is a tmpfs on /dev/shm, so a staged container's 22 GiB is resident memory that no amount of
# cache pressure will reclaim -- it is not disk, and it is not counted anywhere else on this
# screen.
LOAD1= LOAD5= LOAD15= CORES= MEM_TOTAL_KB= MEM_AVAIL_KB= MEM_USED_KB= SHMEM_KB=

read_machine() {
    LOAD1= LOAD5= LOAD15= CORES= MEM_TOTAL_KB= MEM_AVAIL_KB= MEM_USED_KB= SHMEM_KB=
    if [ -r /proc/loadavg ]; then
        read -r LOAD1 LOAD5 LOAD15 _ < /proc/loadavg
    fi
    CORES=$(nproc 2>/dev/null) || CORES=$(grep -c '^processor' /proc/cpuinfo 2>/dev/null) || CORES=
    if [ -r /proc/meminfo ]; then
        local key value
        while read -r key value _; do
            case "$key" in
                MemTotal:)     MEM_TOTAL_KB=$value ;;
                MemAvailable:) MEM_AVAIL_KB=$value ;;
                Shmem:)        SHMEM_KB=$value ;;
            esac
        done < /proc/meminfo
        [ -n "$MEM_TOTAL_KB" ] && [ -n "$MEM_AVAIL_KB" ] &&
            MEM_USED_KB=$(( MEM_TOTAL_KB - MEM_AVAIL_KB ))
    fi
}

human_secs() {
    local s=${1:-0}
    if [ "$s" -lt 0 ]; then printf 'expired'; return; fi
    if [ "$s" -ge 3600 ]; then printf '%dh%02dm' $((s / 3600)) $(((s % 3600) / 60))
    elif [ "$s" -ge 60 ]; then printf '%dm' $((s / 60))
    else printf '%ds' "$s"; fi
}

# --- the self-update clock ----------------------------------------------------------------------
#
# TWO NUMBERS, AND THEY ARE NOT THE SAME NUMBER. The timer fires every five minutes and finds
# nothing almost every time, so "last checked" is a clock that ticks whatever the box is running:
# it reads five minutes old on a machine three days behind master. What an operator wants is when
# the checkout last MOVED, which is what update_ffbox.sh stamps, plus how long until the next
# look -- because "this box is two commits behind" and "and it will notice in forty seconds" is a
# problem you wait out, while the same line with no second half sends somebody to systemctl.
#
# THE SCHEDULE COMES FROM SYSTEMD, not from the interval in the .timer file. The unit carries
# OnUnitActiveSec plus a randomised delay, it catches up after a machine was off, and a hand-run
# `systemctl start` moves the whole schedule -- so the only answer that is not a guess is the one
# the thing holding the schedule gives.
UPDATE_AT= UPDATE_SHA= UPDATE_NEXT_SECS=

# A systemd timespan -- "1w 2d 13h 25min 57.286040s", "4min 3s", "250ms" -- as whole seconds, or
# nothing when it is not one. Some builds print these properties as a raw microsecond count
# instead, so a bare integer is taken as usec; that is the one ambiguity, and systemd never
# prints a unitless timespan.
systemd_timespan_secs() {
    case "${1:-}" in
        ''|infinity|n/a) return ;;
        *[!0-9]*) ;;
        # USEC_INFINITY is UINT64_MAX, which is what a disabled or unschedulable timer answers
        # in the raw form, and it is also the one integer that overflows the arithmetic below
        # into a negative "seconds from now". Anything wider than a plausible timespan is
        # treated as no answer.
        ??????????????????*) return ;;
        *) printf '%d\n' $(( $1 / 1000000 )); return ;;
    esac
    printf '%s\n' "$1" | awk '
        {
            total = 0; ok = 0
            n = split($0, tok, /[ \t]+/)
            for (i = 1; i <= n; i++) {
                if (match(tok[i], /^[0-9]+(\.[0-9]+)?/) == 0) continue
                v = substr(tok[i], 1, RLENGTH) + 0
                u = substr(tok[i], RLENGTH + 1)
                if      (u == "y")               m = 31557600
                else if (u == "month")           m = 2629800
                else if (u == "w")               m = 604800
                else if (u == "d")               m = 86400
                else if (u == "h")               m = 3600
                else if (u == "min" || u == "m") m = 60
                else if (u == "s" || u == "")    m = 1
                else if (u == "ms")              m = 0.001
                else if (u == "us")              m = 0.000001
                else continue
                total += v * m; ok = 1
            }
            if (ok) printf "%d\n", total
        }'
}

read_update() {
    UPDATE_AT= UPDATE_SHA= UPDATE_NEXT_SECS=

    if [ -r "$UPDATE_STAMP" ]; then
        local epoch sha rest
        read -r epoch sha rest < "$UPDATE_STAMP" || true
        case "${epoch:-}" in
            ''|*[!0-9]*) ;;
            *) UPDATE_AT=$epoch; UPDATE_SHA=${sha:-} ;;
        esac
    fi

    command -v systemctl >/dev/null 2>&1 || return 0
    # A monotonic elapse first, when there is one. This timer is OnCalendar= and answers in the
    # realtime property below; it was OnBootSec/OnUnitActiveSec until 2026-09-07, a monotonic
    # timer has no realtime elapse to show, and either form may be in place on a box whose units
    # have not been reinstalled yet -- so both are tried and neither being answerable leaves the
    # column blank.
    #
    # POSITIVE, NOT MERELY PRESENT, and that word is the whole bug fix. A calendar timer does not
    # leave NextElapseUSecMonotonic empty: it answers 0, which is a bare integer, which
    # systemd_timespan_secs reads as a microsecond count and returns as a perfectly good "0".
    # `-n` therefore passed, this branch won, and the countdown became 0 - uptime -- a growing
    # negative that ffstatus and ffweb both render as "next check due now", forever, on a timer
    # that was firing every five minutes exactly as it should. Zero here means "this timer does
    # not schedule that way", so fall through and ask the clock instead.
    local mono now_up rt next
    mono=$(systemd_timespan_secs "$(systemctl show "$UPDATE_TIMER" \
        -p NextElapseUSecMonotonic --value 2>/dev/null)")
    if [ -n "$mono" ] && [ "$mono" -gt 0 ] && [ -r /proc/uptime ]; then
        read -r now_up _ < /proc/uptime
        UPDATE_NEXT_SECS=$(( mono - ${now_up%.*} ))
        return 0
    fi
    rt=$(systemctl show "$UPDATE_TIMER" -p NextElapseUSecRealtime --value 2>/dev/null)
    case "${rt:-}" in
        ''|infinity|n/a) return 0 ;;
    esac
    next=$(date -d "$rt" +%s 2>/dev/null) || return 0
    [ -n "$next" ] && UPDATE_NEXT_SECS=$(( next - $(date +%s) ))
}

# --- is the box being worked on? -----------------------------------------------------------------
#
# WHY THIS IS ON THE HEADER LINE. An empty pool and a container count of zero mean two entirely
# different things depending on the answer: a box mid-update is SUPPOSED to look empty, because
# a drain is exactly "finish what you are doing and take nothing new". Without this, the healthy
# middle of an update reads as an outage and somebody goes looking for a fault that is not there.
#
# FOUR STATES, AND THE DIFFERENCE BETWEEN TWO OF THEM IS THE WHOLE POINT. `updating` means an
# update is LANDING -- new code is being merged and the box is being restarted onto it. That is
# what an operator reads it as, so nothing else may claim it.
#
#   updating   update_ffbox.sh has decided there is work and written its flag
#   checking   the updater is running, which every five minutes it is, and has decided nothing
#   drained    a lane is drained with no update behind it -- an image rebuild, or a hand-set flag
#   running    none of the above
#
# WHY `checking` IS NOT `updating`. ffbox-update.timer fires every five minutes and the unit is
# `activating` for the second or two each poll takes, whether or not anything lands: 288 times a
# day this page would say "updating" for a `git fetch` that logged "nothing to do". On 2026-09-02
# one of those ticks was caught on the box page and cost somebody a hunt for the commit that had
# just landed, of which there was none. The unit being up answers "is the updater running", and
# that is a different question from "is my box changing under me".
#
# THE FLAG IS THE ANSWER, and it comes first for that reason. update_ffbox.sh writes
# ~/.config/ffbox/update.applying at the top of its section 3, which is the exact line past
# which every exit is an update that happened; everything above it is a pass that changed
# nothing. So the flag is not a hint about the update, it IS the decision, and it carries the
# reason with it.
#
# AND WHY THE OTHER THREE SIGNALS SURVIVE. They are what says something is going on when the
# flag cannot be trusted or does not exist: the unit and the process check between them cover the
# timer-driven path and a hand-run update, and the drain flags catch a drain with no updater
# behind it at all -- the weekly runner-image rebuild sets one, and so does `ffwatch drain`.
# A drained box is SUPPOSED to look empty, and that still has to be said; it just is not an
# update, and until 2026-09-02 it claimed to be.
#
# THE UPDATE LOCK IS DELIBERATELY NOT ONE OF THEM. `flock -n` on $CONFIG_DIR/update.lock would
# answer the question exactly -- and would also TAKE the lock for the instant it held it, and
# update_ffbox.sh acquires that same lock with -n and exits "another update is already running"
# when it cannot. A status command that can cause a scheduled update to be skipped is not a
# status command.
MAINT_STATE=running MAINT_REASON=

read_maintenance() {
    MAINT_STATE=running MAINT_REASON=

    # FIRST, ABOVE THE UPDATE AND THE DRAIN, because it is the only one of these that nobody
    # chose and the only one that does not end on its own. An update finishes and a drain is
    # lifted; a config file with a stray comma in it sits there launching nothing until a person
    # opens it. It also makes every other reading on this screen provisional -- the pool targets
    # printed below are built-in defaults, not this box's settings -- and that has to be said
    # before them rather than after.
    if [ -n "${CFG[config_error]:-}" ]; then
        MAINT_STATE=misconfigured
        MAINT_REASON="$CONFIG ${CFG[config_error]} -- nothing launches, and the targets below are built-in defaults"
        return
    fi
    # THE FILE PARSES AND FFWATCH IS STILL REFUSING. Its own flag, and the only way to see the
    # latch: the daemon reads the config once at startup, so a box that came up on a broken file
    # is running on defaults and stays that way until it is restarted -- which the updater does
    # by itself within a few minutes of the repair, since config.json is one of the files it
    # watches. Without this the page would say `running` while the box launched nothing.
    if [ -e "$FFWATCH_FAILSAFE" ]; then
        MAINT_STATE=misconfigured
        MAINT_REASON=$(sed -n 's/^reason=//p' "$FFWATCH_FAILSAFE" 2>/dev/null | head -1 | cut -c1-200)
        [ -n "$MAINT_REASON" ] || MAINT_REASON="ffwatch is in its config failsafe and launches nothing"
        return
    fi

    if [ -e "$FFBOX_APPLYING" ]; then
        MAINT_STATE=updating
        # The flag's own words, and a fallback for the one that could not be written -- the
        # updater treats a failed write as non-fatal, so an empty or truncated flag is a real
        # state and must not render as a bare `updating` with nothing after it.
        # CAPPED, because this is a file rather than a string this script composed: the terminal
        # renderer prints the reason raw, and ffweb truncates at 120, so an unbounded read is one
        # stray write away from a screenful. Both renderers now agree on roughly the same limit.
        MAINT_REASON=$(sed -n 's/^reason=//p' "$FFBOX_APPLYING" 2>/dev/null | head -1 | cut -c1-200)
        [ -n "$MAINT_REASON" ] || MAINT_REASON="an update is being applied"
        return
    fi

    local unit
    unit=$(systemctl is-active ffbox-update.service 2>/dev/null)
    case "$unit" in
        # `is-active` exits non-zero for a oneshot that is still ACTIVATING, which is what the
        # updater looks like for its whole run -- so the word is matched rather than the exit
        # status, and --quiet cannot be used here.
        active|activating|reloading)
            MAINT_STATE=checking
            MAINT_REASON="the ffbox-update unit is $unit -- polling origin, nothing landing yet"
            return ;;
    esac
    if pgrep -f '/update_ffbox[.]sh' >/dev/null 2>&1; then
        MAINT_STATE=checking
        MAINT_REASON="update_ffbox.sh is running -- nothing landing yet"
        return
    fi

    local lanes= verb=is
    [ -e "${CFG[drain_switch]}" ] && lanes="the agent lane"
    if [ -e "$FFGHR_DRAIN" ]; then
        [ -n "$lanes" ] && verb=are
        lanes="${lanes:+$lanes and }the CI lane"
    fi
    if [ -n "$lanes" ]; then
        MAINT_STATE=drained; MAINT_REASON="$lanes $verb drained -- launching nothing new"
    fi
}

# Is the supervisor that owns this CI container still there? `docker inspect` for the label rather
# than a marker file, because the label is set at `docker run` and cannot go stale while the
# container lives. A container with no label predates the label and is left alone, exactly as
# reap.sh leaves it alone.
ci_supervisor_alive() {
    local owner
    # ONE OWNER SINCE 2026-09-08, and reap.sh's owner_state is the definition; this is the same
    # rule, kept in step by hand because ffstatus.sh reads no runner library. An `ffwatch` owner
    # has no per-container pid to check -- the daemon restarts and its containers do not -- so the
    # question is whether a daemon is running at all. The `ffghr.supervisor.pid` branch went with
    # slot.sh; nothing writes that label now.
    #
    # A container with NO owner label is left ALONE rather than called an orphan, exactly as
    # reap.sh leaves it alone: something else made it, and what cannot be explained is sometimes a
    # running job.
    owner=$("$DOCKER" inspect -f '{{index .Config.Labels "ffghr.owner"}}' "${1:?}" 2>/dev/null) || owner=''
    [ -n "$owner" ] || return 0
    [ "$owner" = ffwatch ] || return 0
    pgrep -f ffwatch.py >/dev/null 2>&1
}

# --- gather -------------------------------------------------------------------------------------
#
# ONE PASS OVER THE BOX, into globals both renderers read. A record carries the TTL in seconds
# rather than as "3h47m", because a number is what a renderer can decide how to say -- the
# terminal wants the short form and a JSON consumer wants the number.
declare -a ROWS=() INFRA=()
# SPARES IS THE HELD TIER ONLY, and LOOSE the evictable one. Counting a guess as though it kept
# the promise is what would hide an unfilled held pool behind a warm-branch spare that no turn of
# that class's own branch can ever claim -- the same reason ffwatch's keeper counts them apart.
declare -A SPARES=() LOOSE=() RUNS=()
CI_BUSY=0 CI_WAITING=0 WORKLOADS=0 WIDEST=4 GATHER_ERR=

gather() {
    read_machine
    read_maintenance
    read_update
    read_pool_holds
    ROWS=(); INFRA=(); SPARES=(); LOOSE=(); RUNS=()
    CI_BUSY=0; CI_WAITING=0; WORKLOADS=0; WIDEST=4; GATHER_ERR=

    local fmt="{{.Names}}${SEP}{{.Label \"ffbox.workload\"}}${SEP}{{.Label \"ffbox.agent.class\"}}"
    fmt+="${SEP}{{.Label \"ffbox.pool\"}}${SEP}{{.Label \"ffbox.pool.id\"}}"
    fmt+="${SEP}{{.Label \"ffbox.slot\"}}${SEP}{{.RunningFor}}${SEP}{{.Status}}"
    # THE TIER, LAST, so a container from an older ffbox -- which carries no such label -- still
    # reads correctly: the field arrives empty and `warm` is the right word for it, because held
    # was the one tier there was. design/ffbox_warm_branches_design.txt.
    fmt+="${SEP}{{.Label \"ffbox.pool.tier\"}}"
    # AND THE REF A RUNNING CONTAINER IS ON. `ffbox.pool` answers only for a spare; this one is
    # set on both routes, so an agent row can name its branch instead of showing a blank.
    fmt+="${SEP}{{.Label \"ffbox.ref\"}}"

    local ps
    if ! ps=$("$DOCKER" ps --format "$fmt" 2>/dev/null); then
        GATHER_ERR="could not reach the ffbox daemon at $DOCKER_HOST"
        return 1
    fi

    local name workload class ref poolid slot age status tier runref
    while IFS="$SEP" read -r name workload class ref poolid slot age status tier runref; do
        [ -n "$name" ] || continue
        age=${age% ago}
        if [ -z "$workload" ]; then
            INFRA+=("$name$SEP$status")
            continue
        fi
        WORKLOADS=$((WORKLOADS + 1))
        [ ${#name} -gt "$WIDEST" ] && WIDEST=${#name}

        local lane state ttl
        ttl=''
        case "$workload" in
            ci)
                # WHICH CLOCK FOLLOWS THE STATE, and both files are written by the supervisor that
                # owns the container: `.busy` when its runner takes a job, `.idle` at mint. Before
                # 2026-09-02 neither existed as a deadline -- the number lived in a shell variable
                # inside slot.sh -- which is the whole reason this column was blank for CI rows.
                # THE SAME WORDS THE AGENT LANE USES, since 2026-09-08. This column said `busy`
                # and `waiting` while the agent lane said `running` and `warm` for containers in
                # exactly the same two conditions -- doing work, and provisioned but not yet given
                # any. Two vocabularies for one question is a table an operator has to translate
                # while reading it, and there was never a reason for it beyond the two lanes
                # having been written years apart.
                #
                # `running` IS THE ONE THAT MATTERS. It is what the agent lane calls a container
                # serving a turn, and a CI container with a job is the same thing: work in
                # progress that something is waiting on. `warm` is what a provisioned, unclaimed
                # agent spare says, and an idle registered runner is precisely that -- a container
                # holding a workspace, waiting for work to arrive.
                lane=ci; class=''; ref=''
                if [ -e "$FFGHR_STATE/$name.busy" ]; then
                    state=running; CI_BUSY=$((CI_BUSY + 1))
                    ttl=$(ffbox_clock_left "$FFGHR_STATE/$name.busy" 2>/dev/null) || ttl=''
                else
                    state=warm; CI_WAITING=$((CI_WAITING + 1))
                    ttl=$(ffbox_clock_left "$FFGHR_STATE/$name.idle" 2>/dev/null) || ttl=''
                fi
                # A DEADLINE NOBODY IS ENFORCING IS NOT A DEADLINE. The CI clocks are files the
                # daemon writes and the daemon enforces, so a box with no ffwatch has containers
                # whose files still count down and whose enforcer is gone. Counting down to
                # nothing is worse than saying nothing, so the row says `orphan` instead. Same
                # question reap.sh asks, by the same owner label.
                if [ -n "$ttl" ] && ! ci_supervisor_alive "$name"; then
                    ttl=''; state=orphan
                fi ;;
            pool)
                case "$name" in
                    *-pool-*)
                        # A spare, still waiting. Its own out/ says how far it got: `staged` is
                        # written once the workspace is filled, `owner` once the host has claimed
                        # it (or the container has decided to retire).
                        lane=spare
                        if [ "$tier" = evictable ]; then
                            LOOSE[$class]=$(( ${LOOSE[$class]:-0} + 1 ))
                        else
                            SPARES[$class]=$(( ${SPARES[$class]:-0} + 1 ))
                        fi
                        local out="$POOL_DIR/$poolid/out"
                        if [ -e "$out/staged" ]; then
                            # WHICH KIND OF WARM. A held spare is what this class's `idle` number
                            # asked for and nothing takes it away; an evictable one is a guess
                            # staged onto a recently-used branch out of slack, and the keeper sheds
                            # it as soon as anything else on the box wants the place. A reader
                            # looking at a warm container wants to know which.
                            if [ "$tier" = evictable ]; then
                                state=warm-evictable
                            else
                                state=warm
                            fi
                            ttl=$(ffbox_clock_left "$out/staged" 2>/dev/null) || ttl=''
                        else
                            state=filling
                        fi
                        # OWNER MEANS SPOKEN FOR, AND SINCE 2026-09-02 THAT IS TWO THINGS. A
                        # dispatch claims it, and so does the keeper on its way to retiring a
                        # spare that has aged out; `retiring` is what the keeper leaves to tell
                        # them apart, so a container being stopped does not read as a turn.
                        [ -e "$out/owner" ] && state=claimed
                        [ -e "$out/retiring" ] && { state=retiring; ttl=''; } ;;
                    *)
                        # Renamed by dispatch: a turn that started from a warm workspace.
                        #
                        # ITS BRANCH IS SHOWN, where until 2026-09-06 this blanked it. The label
                        # was right there -- a dispatched container keeps every label it was
                        # staged with -- and the row that most needs naming a branch is the one
                        # doing the work. `runref` rather than `ref` so a container staged before
                        # ffbox.ref existed still answers, from the ffbox.pool label it has.
                        lane=agent; state='running*'; ref=${runref:-$ref}
                        RUNS[$class]=$(( ${RUNS[$class]:-0} + 1 )) ;;
                esac ;;
            agent)
                # A COLD RUN, and it now carries ffbox.ref too. Empty for a container started by
                # an ffbox that predates the label, which reads as the blank this always showed.
                lane=agent; state=running; ref=$runref
                RUNS[$class]=$(( ${RUNS[$class]:-0} + 1 )) ;;
            *)
                lane=$workload; state=running; ref='' ;;
        esac
        ROWS+=("$lane$SEP$class$SEP$name$SEP$slot$SEP$state$SEP$ttl$SEP$ref$SEP$age")
    done <<< "$ps"
    return 0
}

# One pool's reason, dim, under the table -- or nothing at all when it is holding what it was
# asked to, when the keeper recorded no reason, or when this checkout has no such file.
#
# A STALE READING IS SAID AS STALE. The file carries the time of the keeper's last pass rather
# than the time the reason started, precisely so this can tell a standing reason from a daemon
# that has stopped looking -- and the second is a bigger problem than whatever the sentence says.
pool_hold_line() {
    local cls=$1 want have reason age
    case "$cls" in
        ci) want=${CFG[ci_idle]}; have=$CI_WAITING ;;
        *)  want=${CFG[${cls}_idle]}; have=${SPARES[$cls]:-0} ;;
    esac
    [ "$have" -lt "$want" ] || return 0
    reason=${HOLD[$cls.reason]:-}
    [ -n "$reason" ] || return 0
    age=$(( $(date +%s) - ${HOLD[checked_at]:-0} ))
    if [ -n "${HOLD[checked_at]:-}" ] && [ "$age" -gt "$POOL_HOLD_STALE_SECS" ]; then
        reason="$reason  [last looked $(human_secs "$age") ago -- ffwatch may have stopped]"
    fi
    printf '  %s%-10s %s%s\n' "$DIM" "$cls" "$reason" "$N"
}

# --- the terminal reading -------------------------------------------------------------------
render_text() {
    # AMBER FOR THE TWO STATES THAT CHANGE WHAT THE TABLES BELOW MEAN, green for the two that do
    # not. An update or a drain empties the container tables on purpose, and the colour is what
    # stops that reading as an outage; `checking` empties nothing and is the ordinary state of a
    # box between two polls, so colouring it would make the header amber for a couple of seconds
    # every five minutes and teach an operator to ignore the colour.
    local state_mark=$GRN
    case "$MAINT_STATE" in
        updating|drained) state_mark=$YEL ;;
        # RED, WHERE THE OTHER TWO ARE AMBER. An update and a drain are the machine doing as it
        # was told and both end by themselves; a config that does not parse is a fault, it holds
        # every lane on the box, and it ends when a person fixes it.
        misconfigured)    state_mark=$RED ;;
    esac
    printf '\n%sffbox on %s%s  %s%s%s  %s(%s)%s\n' \
        "$B" "$(hostname -s)" "$N" "$DIM" "$(date '+%Y-%m-%d %H:%M:%S')" "$N" \
        "$state_mark" "$MAINT_STATE" "$N"
    # The reason on the next line, because the state word alone sends somebody to the journal to
    # find out which of the things behind it this one is.
    [ -n "$MAINT_REASON" ] && printf '  %s%s%s\n' "$DIM" "$MAINT_REASON" "$N"
    # AND WHEN THIS CHECKOUT LAST MOVED, on the header rather than in a section of its own: it
    # is one line, and the question it answers -- is this box running what was pushed? -- is the
    # one you ask before reading any number below it. The next check is beside it because a box
    # that is behind and about to notice needs no operator at all.
    if [ -n "$UPDATE_AT" ] || [ -n "$UPDATE_NEXT_SECS" ]; then
        local since=unknown
        if [ -n "$UPDATE_AT" ]; then
            since="$(date -d "@$UPDATE_AT" '+%Y-%m-%d %H:%M' 2>/dev/null || printf '%s' "$UPDATE_AT")"
            since="$since ($(human_secs $(( $(date +%s) - UPDATE_AT )) ) ago)"
            [ -n "$UPDATE_SHA" ] && since="$since $(printf %.12s "$UPDATE_SHA")"
        fi
        # A non-positive countdown is a timer that is due and has not fired yet -- during an
        # update, most often, since the unit stays activating for the whole drain. human_secs
        # would call that "expired", which is the right word for a container's TTL and the
        # wrong one for a check that is about to happen.
        local due=
        if [ -n "$UPDATE_NEXT_SECS" ]; then
            if [ "$UPDATE_NEXT_SECS" -gt 0 ]; then
                due=" · next check in $(human_secs "$UPDATE_NEXT_SECS")"
            else
                due=" · next check due now"
            fi
        fi
        printf '  %slast update %s%s%s\n' "$DIM" "$since" "$due" "$N"
    fi

    # --- the machine ------------------------------------------------------------------------
    if [ -n "$LOAD1" ] || [ -n "$MEM_TOTAL_KB" ]; then
        printf '\n%sMACHINE%s\n\n' "$B" "$N"
        if [ -n "$LOAD1" ]; then
            # Amber once the one-minute average passes the core count: past that the queue is
            # longer than the machine is wide. Integer part only -- this is a threshold, not a
            # measurement, and ${x%.*} beats starting awk for it.
            local load_mark=$N
            [ -n "$CORES" ] && [ "${LOAD1%.*}" -ge "$CORES" ] 2>/dev/null && load_mark=$YEL
            printf '  %-9s %s%s %s %s%s' "load" "$load_mark" "$LOAD1" "$LOAD5" "$LOAD15" "$N"
            [ -n "$CORES" ] && printf '  %sacross %s cores%s' "$DIM" "$CORES" "$N"
            printf '\n'
        fi
        if [ -n "$MEM_TOTAL_KB" ] && [ "$MEM_TOTAL_KB" -gt 0 ]; then
            local pct=$(( MEM_USED_KB * 100 / MEM_TOTAL_KB ))
            local mem_mark=$GRN
            [ "$pct" -ge 75 ] && mem_mark=$YEL
            [ "$pct" -ge 90 ] && mem_mark=$RED
            printf '  %-9s %s%s of %s used (%s%%)%s' "memory" "$mem_mark" \
                "$(human_kb "$MEM_USED_KB")" "$(human_kb "$MEM_TOTAL_KB")" "$pct" "$N"
            [ -n "$SHMEM_KB" ] && printf '  %s%s of it in container workspaces%s' \
                "$DIM" "$(human_kb "$SHMEM_KB")" "$N"
            printf '\n'
        fi
    fi

    local box_max=${CFG[box_max]} colour=$GRN
    [ "$WORKLOADS" -ge "$box_max" ] && colour=$RED
    printf '\n%sCONTAINERS%s  %s%d of %d workspace containers%s\n\n' \
        "$B" "$N" "$colour" "$WORKLOADS" "$box_max" "$N"

    if [ ${#ROWS[@]} -eq 0 ]; then
        printf '  %s(none — the box is idle)%s\n' "$DIM" "$N"
    else
        printf "  %s%-6s %-8s %-${WIDEST}s %-5s %-9s %-7s %-7s %s%s\n" \
            "$DIM" LANE CLASS NAME SLOT STATE TTL REF UP "$N"
        # spares last: a run is what you are usually looking for.
        printf '%s\n' "${ROWS[@]}" | sort -t"$SEP" -k1,1 |
        while IFS="$SEP" read -r l c n s st t r a; do
            local mark=$N
            case "$st" in
                warm|waiting)     mark=$GRN ;;
                filling)          mark=$YEL ;;
                claimed|retiring) mark=$YEL ;;
                orphan)           mark=$RED ;;
            esac
            [ -n "$t" ] && t=$(human_secs "$t")
            printf "  %-6s %-8s %-${WIDEST}s %-5s ${mark}%-9s${N} %-7s %-7s %s\n" \
                "$l" "${c:--}" "$n" "${s:--}" "$st" "${t:--}" "${r:--}" "$a"
        done
    fi

    printf '\n%sPOOLS%s\n\n' "$B" "$N"
    # ONE VOCABULARY FOR BOTH LANES, because they hold the same kind of thing under two names:
    # an agent `spare` and an idle CI runner are both a container waiting for work, and both were
    # printed as RUNNING here until 2026-09-02 -- which made a CI pool that was doing exactly what
    # it was configured to do look like it had lost its idle runner.
    # BRANCH is the evictable tier: spares on branches somebody used recently, staged out of
    # slack and shed when the box needs the place. They are not part of IDLE/WAITING because they
    # are not what that number promised, and a column of their own is what keeps both readable.
    printf '  %s%-10s %-6s %-9s %-8s %-6s %s%s\n' "$DIM" CLASS IDLE WAITING BRANCH BUSY MAX "$N"
    local cls
    for cls in ffagent ffdev; do
        local want=${CFG[${cls}_idle]} have=${SPARES[$cls]:-0} busy=${RUNS[$cls]:-0}
        local mark=$GRN
        [ "$have" -lt "$want" ] && mark=$YEL
        printf '  %-10s %-6s %s%-9s%s %-8s %-6s %s\n' \
            "$cls" "$want" "$mark" "$have" "$N" "${LOOSE[$cls]:-0}" "$busy" "${CFG[${cls}_max]}"
    done
    local ci_mark=$GRN
    [ "$CI_WAITING" -lt "${CFG[ci_idle]}" ] && ci_mark=$YEL
    printf '  %-10s %-6s %s%-9s%s %-8s %-6s %s\n' \
        ci "${CFG[ci_idle]}" "$ci_mark" "$CI_WAITING" "$N" "-" "$CI_BUSY" "${CFG[ci_max]}"

    # AND WHY, FOR EVERY ROW THAT IS SHORT. The amber number says a pool is not holding what it
    # was asked to; this says what the keeper is waiting on, which is the question the colour
    # provokes and could not answer. Under the table rather than in a column, because a reason is
    # a sentence and the table is six narrow numbers -- and only for the rows that are short, so
    # a box doing what it should still prints five lines here.
    local hold_cls hold_line hold_said=
    for hold_cls in ffagent ffdev ci; do
        hold_line=$(pool_hold_line "$hold_cls")
        [ -n "$hold_line" ] || continue
        # The blank line only when there is something to separate, so a box with every pool full
        # ends the section exactly where it always did.
        [ -n "$hold_said" ] || printf '\n'
        hold_said=1
        printf '%s\n' "$hold_line"
    done

    if [ ${#INFRA[@]} -gt 0 ]; then
        printf '\n%sINFRASTRUCTURE%s %s(holds no workspace, counts against nothing)%s\n\n' \
            "$B" "$N" "$DIM" "$N"
        printf '%s\n' "${INFRA[@]}" | sort | while IFS="$SEP" read -r n s; do
            printf '  %-28s %s%s%s\n' "$n" "$DIM" "$s" "$N"
        done
    fi
    printf '\n'
}

# One pool's record: the numbers, then what the keeper last said about that class. The three hold
# fields are empty when it said nothing, which is the ordinary state of a pool holding what it was
# asked to -- and the reason goes LAST because it is the only free text in the document, so a
# consumer reading fields positionally cannot be pushed off the end by a long sentence.
pool_record() {
    printf 'P%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s\n' \
        "$SEP" "$1" "$SEP" "$2" "$SEP" "$3" "$SEP" "$4" "$SEP" "$5" "$SEP" "$6" \
        "$SEP" "${HOLD[$1.key]:-}" "$SEP" "${HOLD[$1.since]:-}" \
        "$SEP" "${HOLD[checked_at]:-}" "$SEP" "${HOLD[$1.reason]:-}"
}

# --- the same reading, as a document ----------------------------------------------------------
#
# TAGGED RECORDS INTO PYTHON, which does the quoting. Building JSON in shell means escaping
# strings a stranger named -- a container name, a branch, a docker status line -- and getting
# that subtly wrong is how a page ends up with broken markup or worse. json.dumps is right by
# construction, so the shell's only job is to hand over fields it has already separated.
render_json() {
    {
        printf 'B%s%s%s%s\n' "$SEP" "$WORKLOADS" "$SEP" "${CFG[box_max]}"
        printf 'T%s%s%s%s\n' "$SEP" "$MAINT_STATE" "$SEP" "$MAINT_REASON"
        printf 'U%s%s%s%s%s%s\n' "$SEP" "$UPDATE_AT" "$SEP" "$UPDATE_SHA" \
            "$SEP" "$UPDATE_NEXT_SECS"
        printf 'M%s%s%s%s%s%s%s%s%s%s%s%s%s%s\n' \
            "$SEP" "$LOAD1" "$SEP" "$LOAD5" "$SEP" "$LOAD15" "$SEP" "$CORES" \
            "$SEP" "$MEM_TOTAL_KB" "$SEP" "$MEM_USED_KB" "$SEP" "$SHMEM_KB"
        local cls
        for cls in ffagent ffdev; do
            pool_record "$cls" "${CFG[${cls}_idle]}" "${SPARES[$cls]:-0}" "${RUNS[$cls]:-0}" \
                        "${CFG[${cls}_max]}" "${LOOSE[$cls]:-0}"
        done
        # CI has no such tier, and an empty field is how this record says so -- num() reads it as
        # null, which a page can tell apart from a zero.
        pool_record ci "${CFG[ci_idle]}" "$CI_WAITING" "$CI_BUSY" "${CFG[ci_max]}" ""
        [ ${#ROWS[@]} -gt 0 ] && printf "C$SEP%s\n" "${ROWS[@]}"
        [ ${#INFRA[@]} -gt 0 ] && printf "I$SEP%s\n" "${INFRA[@]}"
        # AND THE BLOCK MUST NOT END ON A TEST. `set -o pipefail` takes a pipeline's status from
        # the rightmost command that failed, and on a box with no infrastructure containers this
        # block ended on a false `[ ... ]` -- so `ffstatus.sh --json` exited 1 while printing a
        # perfectly good document. ffweb reads stdout and never noticed; anything that checked the
        # status read an idle box as a broken one.
        :
    # THE PROGRAM COMES IN AS AN ARGUMENT, NOT ON STDIN. `python3 - <<PY` puts the heredoc on
    # stdin, which is where the interpreter reads the program from -- so the records piped in
    # from the block above were thrown away and this rendered an empty document that looked
    # exactly like an idle box. -c leaves stdin to the pipe, which is the whole point of it here.
    } | python3 -c '
import json, sys

SEP = "\x1f"
doc = {"host": sys.argv[1], "generated_at": sys.argv[2],
       "box": {"used": 0, "max": 0}, "machine": {},
       "maintenance": {"state": "running", "reason": ""},
       "update": {"last_applied_epoch": None, "last_applied_sha": None,
                  "next_check_secs": None},
       "pools": [], "containers": [], "infrastructure": []}

def num(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None

for line in sys.stdin.read().splitlines():
    if not line:
        continue
    tag, _, rest = line.partition(SEP)
    f = rest.split(SEP)
    if tag == "B":
        doc["box"] = {"used": num(f[0]), "max": num(f[1])}
    elif tag == "T":
        doc["maintenance"] = {"state": f[0] or "running", "reason": f[1]}
    elif tag == "U":
        # Epoch and seconds-from-now rather than "2h07m ago" and "in 4m", for the reason every
        # other clock in this document is a number: the terminal wants the short form, a page
        # wants to decide for itself, and a formatted string is a decision neither can undo.
        doc["update"] = {"last_applied_epoch": num(f[0]), "last_applied_sha": f[1] or None,
                         "next_check_secs": num(f[2])}
    elif tag == "M":
        # A load average is the one non-integer on this page. None rather than 0.0 when /proc
        # was unreadable, so a consumer can tell "no answer" from "an idle machine".
        def dec(text):
            try:
                return float(text)
            except (TypeError, ValueError):
                return None
        doc["machine"] = {"load1": dec(f[0]), "load5": dec(f[1]), "load15": dec(f[2]),
                          "cores": num(f[3]), "mem_total_kb": num(f[4]),
                          "mem_used_kb": num(f[5]), "shmem_kb": num(f[6])}
    elif tag == "P":
        # WHY THIS POOL IS SHORT, when ffwatch wrote a reason down -- null when it did not, which
        # is what every pool says on a box whose keeper is satisfied. `checked_at` dates the
        # keeper pass that last confirmed it, NOT the moment the reason began: that is what lets
        # a page tell a standing reason from a daemon that has stopped looking.
        hold = None
        if len(f) > 9 and (f[6] or f[9]):
            hold = {"key": f[6] or None, "since": num(f[7]), "checked_at": num(f[8]),
                    "reason": f[9]}
        doc["pools"].append({"class": f[0], "idle": num(f[1]), "waiting": num(f[2]),
                             "busy": num(f[3]), "max": num(f[4]),
                             "warm_branches": num(f[5]) if len(f) > 5 else None,
                             "hold": hold})
    elif tag == "C":
        doc["containers"].append({
            "lane": f[0], "class": f[1] or None, "name": f[2], "slot": f[3] or None,
            "state": f[4], "ttl_secs": num(f[5]), "ref": f[6] or None, "uptime": f[7]})
    elif tag == "I":
        doc["infrastructure"].append({"name": f[0], "status": f[1]})

json.dump(doc, sys.stdout, indent=2, sort_keys=False)
sys.stdout.write("\n")
' "$(hostname -s)" "$(date -Is)"
}

# --- and what a failure looks like in each ------------------------------------------------------
#
# A CONSUMER MUST NOT HAVE TO GUESS. The terminal gets the sentence on stderr and a non-zero
# status; --json gets a document with an `error` key and the same status, so ffweb can say what
# went wrong on the page rather than rendering an empty table that looks like an idle box.
fail() {
    if [ "$JSON" -eq 1 ]; then
        python3 -c 'import json,sys; json.dump({"error": sys.argv[1]}, sys.stdout); print()' \
            "$GATHER_ERR"
    else
        printf '%sffstatus: %s%s\n' "$RED" "$GATHER_ERR" "$N" >&2
    fi
    exit 1
}

if [ "$WATCH" -eq 1 ]; then
    while :; do
        clear
        gather || fail
        render_text
        sleep "$INTERVAL"
    done
else
    gather || fail
    # if/else rather than `a && b || c`: a render_json that failed would fall through to
    # render_text and print a table after the document.
    if [ "$JSON" -eq 1 ]; then render_json; else render_text; fi
fi
