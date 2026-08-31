#!/bin/sh
# test_pool.sh — offline tests for the pool arithmetic in lib/config.sh.
#
#   sh ffbox/runners/test_pool.sh
#
# NO DAEMON AND NO GITHUB. `docker` is a stub on PATH that prints whatever the case under test
# says the daemon holds, and the config directory is a temporary one. That is the whole point:
# admission is three lines of arithmetic that decide how many runners exist, and getting it wrong
# is invisible until an idle machine is carrying six registrations or a busy one is carrying none.
#
# What is NOT covered here, because it needs a real daemon: ffghr_container_busy, which reads
# `docker top`. Its contract is checked live instead — see the pool section of README.md.

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
FFGITHUBRUNNERS_CONFIG_DIR="$TMP/config"
export FFGITHUBRUNNERS_CONFIG_DIR
mkdir -p "$FFGITHUBRUNNERS_CONFIG_DIR"

write_config() { printf '{ "slots": %s, "idle_pool": %s }\n' "$1" "$2" > "$FFGITHUBRUNNERS_CONFIG_DIR/config.json"; }

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

printf '{ "slots": "six" }\n' > "$FFGITHUBRUNNERS_CONFIG_DIR/config.json"
ffghr_reload_limits
is "$SLOTS" 1 "a non-numeric slots falls back to the default rather than killing the supervisor"
is "$IDLE_POOL" 1 "a key that has gone away falls back to the default"

printf '{ not json\n' > "$FFGITHUBRUNNERS_CONFIG_DIR/config.json"
ffghr_reload_limits 2>/dev/null
is "$SLOTS" 1 "an unreadable config.json leaves the current values alone"

# The environment layer still wins over the file, which is how a one-off override works.
FFGITHUBRUNNERS_IDLE_POOL=5 ; export FFGITHUBRUNNERS_IDLE_POOL
write_config 6 1
ffghr_reload_limits
is "$IDLE_POOL" 5 "FFGITHUBRUNNERS_IDLE_POOL beats config.json"
unset FFGITHUBRUNNERS_IDLE_POOL

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
