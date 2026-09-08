#!/bin/sh
# test_pool.sh — offline tests for the pool arithmetic and the machine id in lib/config.sh.
#
#   sh ffbox/runners/test_pool.sh
#
# NO DAEMON AND NO GITHUB. `docker` is a stub on PATH that prints whatever the case under test
# says the daemon holds, and the config directory is a temporary one. That is the whole point:
# admission is three lines of arithmetic that decide how many runners exist, and getting it wrong
# is invisible until an idle machine is carrying six registrations or a busy one is carrying none.
#
# What is NOT covered here, because it needs a real daemon: ffghr_container_busy, which reads
# `docker top`. Its contract is checked live instead — see the pool section of README.md. Nor is
# the machine id actually being WRITTEN, which happens as root inside the container; what is
# checked here is that the value handed to it is stable per slot and refused when malformed.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

PASS=0
FAIL=0

ok()   { PASS=$((PASS + 1)); printf '  ok   %s\n' "$*"; }
bad()  { FAIL=$((FAIL + 1)); printf '  FAIL %s\n' "$*"; }
is()   { # is <got> <want> <what>
    if [ "$1" = "$2" ]; then ok "$3"; else bad "$3: got '$1', want '$2'"; fi
}

# The stub daemon. CONTAINERS is a space-separated list of names it should report as running.
mkdir -p "$TMP/bin"
cat > "$TMP/bin/docker" <<'EOF'
#!/bin/sh
# Only the one call the pool makes: docker ps --filter label=ffghr.slot --format '{{.Names}}'
case "$1" in
    ps) for c in ${CONTAINERS:-}; do printf '%s\n' "$c"; done ;;
    *)  exit 1 ;;
esac
EOF
chmod +x "$TMP/bin/docker"
PATH="$TMP/bin:$PATH"
export PATH

# A config directory of our own, so nothing here reads or writes the machine's real one.
#
# FFBOX_CONFIG_DIR IS THE ONE THAT MATTERS NOW. The runners' settings became a section of the
# box's single config.json on 2026-09-01, so FFGITHUBRUNNERS_CONFIG_DIR no longer decides where
# they are read from -- it still names the directory holding this lane's secrets and flags, and
# is set for that. Without the line below, this file wrote a config nothing read and then
# asserted against the REAL MACHINE's numbers, which is exactly how it failed when the shape
# changed: "got '3', want '6'", 3 being this box's actual ceiling.
FFGITHUBRUNNERS_CONFIG_DIR="$TMP/config"
export FFGITHUBRUNNERS_CONFIG_DIR
mkdir -p "$FFGITHUBRUNNERS_CONFIG_DIR"
FFBOX_CONFIG_DIR="$TMP/config"
export FFBOX_CONFIG_DIR

# max and idle, in the "pool" object both lanes use. max_concurrent_runs rides along because a
# negative max is read as the box ceiling, and a test for that needs the box to have one.
write_config() {
    printf '{ "max_concurrent_runs": 6, "githubrunner": { "pool": { "max": %s, "idle": %s } } }\n' \
        "$1" "$2" > "$FFBOX_CONFIG_DIR/config.json"
}

write_config 6 1
. "$HERE/lib/config.sh"

printf '\nthe knobs\n'
is "$SLOTS" 6 "slots comes from config.json"
is "$IDLE_POOL" 1 "idle_pool comes from config.json"

printf '\ncounting\n'
CONTAINERS=""; export CONTAINERS
is "$(ffghr_pool_counts)" "0 0" "an empty daemon is 0 total, 0 idle"

CONTAINERS="ffghr-h-1-aa ffghr-h-2-bb"
is "$(ffghr_pool_counts)" "2 2" "two containers with no marker are both idle"

ffghr_mark_busy ffghr-h-1-aa
is "$(ffghr_pool_counts)" "2 1" "a busy marker takes one out of the idle count"

ffghr_clear_busy ffghr-h-1-aa
is "$(ffghr_pool_counts)" "2 2" "clearing it puts it back"

# THE MARKER IS ONLY TRUSTED FOR A LIVE CONTAINER. This is what keeps a marker left by a SIGKILLed
# supervisor from holding a place in the pool forever.
ffghr_mark_busy ffghr-h-9-zz
is "$(ffghr_pool_counts)" "2 2" "a marker for a container that is gone counts for nothing"
ffghr_clear_busy ffghr-h-9-zz

printf '\nre-reading config.json\n'
write_config 4 3
ffghr_reload_limits
is "$SLOTS" 4 "a raised ceiling is picked up without a restart"
is "$IDLE_POOL" 3 "a raised idle_pool is picked up without a restart"

printf '{ "githubrunner": { "pool": { "max": "six" } } }\n' > "$FFBOX_CONFIG_DIR/config.json"
ffghr_reload_limits
is "$SLOTS" 1 "a non-numeric slots falls back to the default rather than killing the supervisor"
is "$IDLE_POOL" 1 "a key that has gone away falls back to the default"

printf '{ not json\n' > "$FFBOX_CONFIG_DIR/config.json"
ffghr_reload_limits 2>/dev/null
is "$SLOTS" 1 "an unreadable config.json leaves the current values alone"

# The environment layer still wins over the file, which is how a one-off override works.
FFGITHUBRUNNERS_IDLE_POOL=5 ; export FFGITHUBRUNNERS_IDLE_POOL
write_config 6 1
ffghr_reload_limits
is "$IDLE_POOL" 5 "FFGITHUBRUNNERS_IDLE_POOL beats config.json"
unset FFGITHUBRUNNERS_IDLE_POOL

printf '\nthe Unity machine id\n'
write_config 6 1
ffghr_reload_limits

MACHINE_ID=per-slot
_m1=$(ffghr_machine_id 1)
_m2=$(ffghr_machine_id 2)
is "$(printf '%s' "$_m1" | wc -c)" 32 "an id is 32 characters"
printf '%s' "$_m1" | grep -qE '^[0-9a-f]{32}$' && ok "and 32 HEX characters" || bad "not hex: $_m1"
is "$(ffghr_machine_id 1)" "$_m1" "the same slot gets the same id every time"
[ "$_m1" != "$_m2" ] && ok "different slots get different ids" || bad "slot 1 and slot 2 collided"

# THE POINT OF PER-SLOT. A leaked Unity seat is reclaimed by the next job on that slot, which only
# works if the id survives the container that leaked it — so this must NOT be random.
is "$(ffghr_machine_id 1)" "$_m1" "an id does not change between containers"

MACHINE_ID=image
ffghr_machine_id 1 >/dev/null 2>&1 && bad "machine_id=image must override nothing" || ok "machine_id=image leaves the image's id alone"

MACHINE_ID=0123456789abcdef0123456789abcdef
is "$(ffghr_machine_id 1)" "$MACHINE_ID" "an explicit 32-hex id is used verbatim"

MACHINE_ID=not-a-machine-id
ffghr_machine_id 1 >/dev/null 2>&1 && bad "a malformed id must be refused" || ok "a malformed id is refused rather than written"
MACHINE_ID=per-slot

# --- the two clocks -----------------------------------------------------------------------------
#
# THE BUG THIS IS THE REGRESSION TEST FOR. Until 2026-09-02 slot.sh set one deadline at container
# launch and never reset it, so a job landing on a runner that had been registered and waiting for
# 118 minutes had two minutes to finish before `docker stop -t 90`. The comment above the loop
# asserted the opposite. What is exercised here is the arithmetic, in the same place and the same
# way the supervisor does it; the loop itself needs a daemon and is not covered.
printf '\nthe two clocks\n'

WATCHDOG_MINUTES=120
IDLE_MINUTES=120
CNAME=ffghr-h-1-clock

# slot.sh's own two functions, copied rather than sourced: slot.sh takes a slot number, mints a
# JIT config and talks to a daemon before it defines them. If either changes there, change it here
# — the point of this file is the arithmetic, and a copy that has drifted fails loudly.
container_started_at() { printf '%s\n' "${STUB_STARTED_AT:-}"; }
work_deadline() {
    _at=$(ffbox_clock_start "$(ffghr_busy_marker "$CNAME")" 2>/dev/null || :)
    [ -n "$_at" ] || _at=$(container_started_at || :)
    [ -n "$_at" ] || _at=$(date +%s)
    echo $(( _at + WATCHDOG_MINUTES * 60 ))
}

# A container minted 118 minutes ago that takes a job NOW.
STUB_STARTED_AT=$(( $(date +%s) - 118 * 60 ))
ffghr_mark_busy "$CNAME"
_left=$(( $(work_deadline) - $(date +%s) ))
[ "$_left" -gt $(( 119 * 60 )) ] \
    && ok "a job on a 118-minute-old container gets the whole watchdog, not two minutes" \
    || bad "the work clock is still measured from launch: ${_left}s left, want ~7200"

# THE SAME DEADLINE AFTER A RESTART. Derived from the marker rather than from the moment the
# supervisor noticed, so systemd restarting a supervisor mid-job does not grant a fresh 120.
_first=$(work_deadline)
sleep 1
is "$(work_deadline)" "$_first" "a restarted supervisor recovers the same deadline"

# NO MARKER FALLS BACK TO THE CONTAINER'S START, WHICH IS THE OLD RULE, and never to "no
# deadline": an unbounded work clock leaves a wedged container holding a slot and a Unity seat.
ffghr_clear_busy "$CNAME"
is "$(work_deadline)" "$(( STUB_STARTED_AT + 120 * 60 ))" \
    "an unreadable marker falls back to the container's start, still bounded"

# An OLD marker, in the bare at= format a supervisor from before this wrote. Same fallback.
printf 'at=%s\n' "$(date -Is)" > "$(ffghr_busy_marker "$CNAME")"
is "$(work_deadline)" "$(( STUB_STARTED_AT + 120 * 60 ))" \
    "a pre-2026-09-02 marker is not a deadline, and the fallback covers the deploy window"
ffghr_clear_busy "$CNAME"

# The idle clock is a separate file and a separate question.
ffghr_mark_idle "$CNAME"
_il=$(ffbox_clock_left "$(ffghr_idle_marker "$CNAME")")
[ "$_il" -gt $(( 119 * 60 )) ] && ok "the idle clock starts at mint" || bad "idle clock: $_il"
ffbox_clock_expired "$(ffghr_idle_marker "$CNAME")" \
    && bad "a fresh idle marker must not be expired" || ok "and is not expired while it is fresh"

printf 'staged_at=%s\nttl_secs=60\n' "$(date -Is -d '-1 hour')" > "$(ffghr_idle_marker "$CNAME")"
ffbox_clock_expired "$(ffghr_idle_marker "$CNAME")" \
    && ok "an old idle marker is expired" || bad "an hour past a 60s ttl must be expired"

# 0 IS "NEVER RECYCLE", not "expire immediately" — the coercion both pools apply to pool.idle.
printf 'staged_at=%s\nttl_secs=0\n' "$(date -Is -d '-1 hour')" > "$(ffghr_idle_marker "$CNAME")"
ffbox_clock_expired "$(ffghr_idle_marker "$CNAME")" \
    && bad "ttl_secs 0 must mean no deadline" || ok "an idle_minutes of 0 means never recycle"

# A missing file is no deadline, and the caller must never read that as expired.
ffghr_clear_idle "$CNAME"
ffbox_clock_left "$(ffghr_idle_marker "$CNAME")" >/dev/null 2>&1 \
    && bad "a missing marker must not answer" || ok "a missing idle marker has no deadline at all"

# The floor under a value small enough to churn registrations against GitHub's API.
FFGITHUBRUNNERS_IDLE_MINUTES=1 . "$HERE/lib/config.sh" 2>/dev/null
is "$IDLE_MINUTES" 5 "an idle_minutes below the floor is raised to it"
FFGITHUBRUNNERS_IDLE_MINUTES=0 . "$HERE/lib/config.sh" 2>/dev/null
is "$IDLE_MINUTES" 0 "and 0 is left alone, because never recycling is a thing somebody may mean"
unset FFGITHUBRUNNERS_IDLE_MINUTES

printf '\nre-reading the config without forking python3 every poll\n'

# Its own writer, since the section that used to define one went with the slot units.
write_units_config() {   # <box ceiling> <pool max>
    printf '{ "max_concurrent_runs": %s, "githubrunner": { "pool": { "max": %s, "idle": 1 } } }\n' \
        "$1" "$2" > "$FFBOX_CONFIG_DIR/config.json"
    ffghr_reload_limits
}

# THE GUARD THAT MAKES THE HEADROOM AFFORDABLE. A waiting supervisor called ffghr_reload_limits
# once per POOL_POLL_SECONDS and each call forked a python3 to re-parse a file that changes about
# twice a month: measured 2026-09-08 at 4.3s of CPU per 293s elapsed per waiting slot, about 1.5%
# of a core, of which the parse is about half. Sizing the units to the box ceiling multiplies that
# by the headroom, so the guard lands with it.
write_units_config 12 5
_stamp_before=$_FFGHR_CFG_STAMP
ffghr_reload_limits
is "$_FFGHR_CFG_STAMP" "$_stamp_before" "an unchanged config is not re-read"

# AND THE CASE THAT KILLED THE FIRST VERSION OF THE GUARD. It stamped whole-second mtime and size,
# and `max 5` -> `max 6` is the same number of bytes: two edits inside one second were
# indistinguishable and the second was silently ignored. The inode is what catches it, since every
# writer here renames a temporary file into place.
write_units_config 12 6
is "$SLOTS" 6 "a same-second, same-size edit is still picked up"

printf '\nhow long a job waits on the host\n'

# THE TWO HANDSHAKES A CI JOB BLOCKS ON, and the host's half of both. The job asks for a commit
# and waits for `fetch.done`; it asks for an artifact upload and holds itself open for
# `artifact.done`. Its own defaults are 120s and 180s. They are raised here because the answering
# process is about to become ffwatch, which restarts on every update and is gone for minutes --
# and a job that reaches its fetch step in that window would fail its checkout.
# design/ffbox_ci_in_ffwatch_design.txt section 5c.
write_waits() {   # <mirror_wait_secs JSON literal> <artifact_wait_secs JSON literal>
    printf '{ "max_concurrent_runs": 6, "githubrunner": { "pool": { "max": 6, "idle": 1 },
              "mirror_wait_secs": %s, "artifact_wait_secs": %s } }\n' "$1" "$2" \
        > "$FFBOX_CONFIG_DIR/config.json"
}

write_config 6 1
. "$HERE/lib/config.sh"
is "$MIRROR_WAIT_SECS" 600 "the mirror wait defaults to 600s, not the workflow's 120"
is "$ARTIFACT_WAIT_SECS" 600 "the artifact wait defaults to 600s, not the action's 180"

write_waits 900 300
. "$HERE/lib/config.sh"
is "$MIRROR_WAIT_SECS" 900 "config.json sets the mirror wait"
is "$ARTIFACT_WAIT_SECS" 300 "config.json sets the artifact wait"

# BOTH REACH A `sleep` LOOP INSIDE SOMEBODY ELSE'S CONTAINER, where a non-numeric value is a job
# that waits zero seconds or hangs, and neither failure names this file. So they are coerced here.
write_waits '"ten minutes"' 0
. "$HERE/lib/config.sh"
is "$MIRROR_WAIT_SECS" 600 "a wait that is not a number falls back to the default"
is "$ARTIFACT_WAIT_SECS" 600 "and so does zero, which would be a job that never waits at all"

write_config 6 1
. "$HERE/lib/config.sh"

# THE TWO WAIT BUDGETS REACH THE CONTAINER FROM ci_lane NOW. This used to grep slot.sh's docker
# run for the two -e flags; slot.sh is gone and test_ci_lane.py renders ci_lane's argument list and
# asserts on it instead, which is the same check against the code that actually runs.

printf '\nidentity that survives a supervisor change\n'

# THE DROP BOX BELONGS TO THE CONTAINER, NOT TO A SLOT NUMBER. Once the unit instances were sized
# to the box ceiling, which slot a container lands on became arbitrary, so a slot number stopped
# being able to find anything. A process that did not start the container must still be able to
# derive its staging path, and `docker ps` is all it has.
# design/ffbox_ci_in_ffwatch_design.txt section 4a.
CACHE_DIR=$TMP/cache
FFGHR_CACHE_STAGING=$CACHE_DIR/staging
is "$(ffghr_cache_stage_dir ffghr-h-7-abc123)" "$FFGHR_CACHE_STAGING/ffghr-h-7-abc123" \
   "the staging path is derived from the container name"
if (ffghr_cache_stage_dir >/dev/null 2>&1); then
    bad "a stage dir with no container name must not silently return the staging root"
else
    ok "and a missing name is refused rather than returning the staging root"
fi

# Two containers on the SAME slot number -- which happens every time a slot serves a second job --
# must not share a drop box. This is the property the nonce buys.
[ "$(ffghr_cache_stage_dir ffghr-h-7-abc123)" != "$(ffghr_cache_stage_dir ffghr-h-7-def456)" ] \
    && ok "two containers on one slot get different drop boxes" \
    || bad "two containers on one slot must not share a drop box"

printf '\nwho owns a container\n'

# THE RULE ITSELF LIVES IN reap.sh AND IS TESTED IN test_reap.sh, against the real script with a
# stub daemon. It was briefly tested here instead, by copying `owner_state` into this file and
# asserting against the copy -- which would have gone on passing if the real function were
# deleted. What is left here is the half that belongs here: the label has to actually be written,
# or every container reads as pre-2026-09-08 forever and the rule never fires.

# And the label is actually on the run, or every container reads as pre-2026-09-08 forever.
# THE LABEL ITSELF IS ci_lane's TO WRITE NOW, and test_ci_lane.py asserts it is on the docker run
# argument list. What stays here is the reading rule, which lives in reap.sh and is driven by
# test_reap.sh against the real script.

printf '\nthe staging protocol version\n'

# THE FILES IN A STAGING DIRECTORY ARE A WIRE FORMAT, and today the two halves cannot disagree
# about it: slot.sh launches the container and serves it, so both are the same commit. That ends
# when the supervisor becomes a daemon that restarts mid-job. design section 9e.
_pdir=$TMP/stage-proto
mkdir -p "$_pdir"

ffghr_protocol_write "$_pdir"
is "$(cat "$_pdir/protocol")" "$FFGHR_PROTOCOL_VERSION" "the version is written into the directory"
ffghr_protocol_ok "$_pdir" >/dev/null \
    && ok "and a host speaking that version serves it" \
    || bad "a host must serve a directory carrying its own version"

# A DIRECTORY WITH NO protocol FILE IS ACCEPTED, and this is the case that decides whether the
# upgrade introducing the check fails every job in flight. It means a container launched before
# the file existed, whose exchange is version 1 by definition.
_pold=$TMP/stage-old
mkdir -p "$_pold"
ffghr_protocol_ok "$_pold" >/dev/null \
    && ok "a directory from before the file existed is served, not refused" \
    || bad "refusing an unversioned directory would fail every job across the upgrade"

# The one that has to refuse. A version this host does not know means the files below it may not
# mean what this host thinks, and acting on them promotes an archive under a name somebody else
# chose or fetches a commit for a job that wanted a different one.
printf '99\n' > "$_pdir/protocol"
if ffghr_protocol_ok "$_pdir" >/dev/null; then
    bad "a version this host does not speak must be refused"
else
    ok "a version this host does not speak is refused"
fi
case "$(ffghr_protocol_ok "$_pdir" 2>/dev/null || true)" in
    *"v99"*) ok "and the refusal names the version, so the journal says which" ;;
    *)       bad "the refusal must name the version it could not serve" ;;
esac

# Garbage is refused the same way. It is not a version this host speaks, and guessing is the
# thing this whole mechanism exists to prevent.
printf 'banana\n' > "$_pdir/protocol"
ffghr_protocol_ok "$_pdir" >/dev/null \
    && bad "a protocol file that is not a version must be refused" \
    || ok "a protocol file that is not a version is refused too"

# An older version stays servable once somebody adds it to the accepted list -- that is the whole
# point of the list being separate from the current version.
printf '1\n' > "$_pdir/protocol"
FFGHR_PROTOCOL_ACCEPTS='1 2' FFGHR_PROTOCOL_VERSION=2 ffghr_protocol_ok "$_pdir" >/dev/null \
    && ok "a host on v2 still serves a v1 job when it says it accepts v1" \
    || bad "the accepted list must be what decides, not the current version"

# WRITING AND CHECKING THE PROTOCOL IS ci_lane's, and test_ci_lane.py covers that side. The rules
# themselves are above and are the real functions, sourced from lib/config.sh.

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
