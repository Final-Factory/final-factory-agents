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

printf '\nadmission\n'
CONTAINERS=""
ffghr_pool_admit && ok "an empty pool admits" || bad "an empty pool must admit"

CONTAINERS="ffghr-h-1-aa"
ffghr_pool_admit && bad "one idle runner with idle_pool 1 must NOT admit" || ok "one idle runner satisfies idle_pool 1"

# The whole feature in one case: the idle runner takes a job, so the pool is short one and the
# next slot brings a replacement up.
ffghr_mark_busy ffghr-h-1-aa
ffghr_pool_admit && ok "a busy runner makes room for a replacement" || bad "a busy runner must admit a replacement"

# ... and it keeps admitting as jobs arrive, until the ceiling.
CONTAINERS="ffghr-h-1-aa ffghr-h-2-bb ffghr-h-3-cc ffghr-h-4-dd ffghr-h-5-ee"
for c in $CONTAINERS; do ffghr_mark_busy "$c"; done
ffghr_pool_admit && ok "five busy of six admits the sixth" || bad "five busy of six must admit"

CONTAINERS="ffghr-h-1-aa ffghr-h-2-bb ffghr-h-3-cc ffghr-h-4-dd ffghr-h-5-ee ffghr-h-6-ff"
ffghr_mark_busy ffghr-h-6-ff
ffghr_pool_admit && bad "the ceiling must hold at slots=6" || ok "six of six does not admit a seventh"

# A ceiling reached with an idle runner still in it: the ceiling wins, which is the case that
# makes idle_pool a target rather than a guarantee.
write_config 2 2
ffghr_reload_limits
CONTAINERS="ffghr-h-1-aa ffghr-h-2-bb"
ffghr_clear_busy ffghr-h-1-aa; ffghr_clear_busy ffghr-h-2-bb
ffghr_pool_admit && bad "slots=2 with two containers must not admit" || ok "the ceiling beats the idle target"

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

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
