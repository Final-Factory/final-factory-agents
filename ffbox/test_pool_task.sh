#!/bin/sh
# test_pool_task.sh — offline tests for the staged container's own failsafe.
#
#   sh ffbox/test_pool_task.sh
#
# NO DOCKER, NO UNITY, NO NETWORK. pool-task.sh is run directly, against a scratch git workspace,
# a stub unity-license.sh and a TTL measured in seconds instead of hours.
#
# WHAT IS UNDER TEST IS THE ONE FAILURE MODE THAT LEAVES A CONTAINER RUNNING FOR EVER. The host
# became the enforcer of the idle clock on 2026-09-02, and it retires a spare by claiming
# out/owner and then stopping it. A keeper that dies between those two -- or whose `docker stop`
# fails -- leaves a claim that never becomes a dispatch. Until the same day this loop answered
# that by pushing its own deadline 900 seconds and re-attempting a create that could never
# succeed, so it waited and pushed and waited for as long as the container lived, holding 22 GiB
# and a Unity seat. Its own comment claimed the opposite. Now the push is taken once.
#
# The dispatch path is NOT covered here: it goes on to resync the workspace and exec the turn
# task, which needs the mirror and the rest of a container.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  ok   %s\n' "$*"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL %s\n' "$*"; }

# A workspace with a HEAD, which is all pool-task.sh asks of it before it goes idle.
WS=$TMP/ws
mkdir -p "$WS"
git -C "$WS" init -q
git -C "$WS" -c user.email=t@t -c user.name=t commit -q --allow-empty -m staged

# The licence, stubbed: a seat this test neither takes nor returns.
cat > "$TMP/unity-license.sh" <<'EOF'
try_unity_license() { return 0; }
return_license() { return 0; }
EOF

# run_pool <name> <ttl> <margin> -> exit code in RC, log in $TMP/<name>.log, seconds in SECS
run_pool() {
    _n=$1; _ttl=$2; _margin=$3
    rm -rf "$TMP/$_n"; mkdir -p "$TMP/$_n/out" "$TMP/$_n/in"
    _t0=$(date +%s)
    set +e
    FFBOX_WORKSPACE="$WS" \
    FFBOX_OUT="$TMP/$_n/out" \
    FFBOX_IN="$TMP/$_n/in" \
    FFBOX_UNITY_LICENSE="$TMP/unity-license.sh" \
    FFBOX_IDLE_TTL_SECS="$_ttl" \
    FFBOX_IDLE_FAILSAFE_MARGIN_SECS="$_margin" \
    FFBOX_POOL_POLL_SECS=1 \
        timeout 60 bash "$HERE/pool-task.sh" > "$TMP/$_n.log" 2>&1
    RC=$?
    set -e
    SECS=$(( $(date +%s) - _t0 ))
    unset _n _ttl _margin _t0
}

printf '\nthe staged container writes its deadline down\n'
run_pool clock 2 1
grep -q '^staged_at=' "$TMP/clock/out/staged" && ok "out/staged carries staged_at" \
    || bad "no staged_at in out/staged"
grep -q '^ttl_secs=2$' "$TMP/clock/out/staged" && ok "and the ttl it was staged under" \
    || bad "no ttl_secs=2 in out/staged"

printf '\nunclaimed, it retires itself\n'
run_pool retire 2 1
[ "$RC" = 0 ] && ok "an unclaimed container exits 0" || bad "unclaimed exit was $RC"
[ -e "$TMP/retire/out/owner" ] && ok "and claims owner on the way out, so the host sees it" \
    || bad "no owner file after a self-retirement"
[ "$SECS" -ge 3 ] && ok "after its ttl plus the failsafe margin" || bad "retired after only ${SECS}s"

printf '\nclaimed and then abandoned, it still retires\n'
# THE CASE THAT USED TO HANG FOR EVER. The host claims and never dispatches.
rm -rf "$TMP/orphan"; mkdir -p "$TMP/orphan/out" "$TMP/orphan/in"
: > "$TMP/orphan/out/owner"
_t0=$(date +%s)
set +e
FFBOX_WORKSPACE="$WS" FFBOX_OUT="$TMP/orphan/out" FFBOX_IN="$TMP/orphan/in" \
FFBOX_UNITY_LICENSE="$TMP/unity-license.sh" FFBOX_IDLE_TTL_SECS=2 \
FFBOX_IDLE_FAILSAFE_MARGIN_SECS=2 FFBOX_POOL_POLL_SECS=1 \
    timeout 40 bash "$HERE/pool-task.sh" > "$TMP/orphan.log" 2>&1
RC=$?
set -e
SECS=$(( $(date +%s) - _t0 ))
[ "$RC" = 0 ] && ok "a claim that never becomes a dispatch ends in an exit, not a wait" \
    || bad "orphaned claim exited $RC after ${SECS}s (124 is the timeout: it hung)"
grep -q 'never dispatched' "$TMP/orphan.log" \
    && ok "and it says the host claimed it and did not come back" \
    || bad "no explanation in the log"
[ "$SECS" -lt 30 ] && ok "within one margin of the deadline, not for ever" \
    || bad "took ${SECS}s"

printf '\nthe push is taken once, so a real dispatch is never cut off\n'
# The host claims, then dispatches a moment later — the case the push exists for.
rm -rf "$TMP/late"; mkdir -p "$TMP/late/out" "$TMP/late/in"
: > "$TMP/late/out/owner"
( sleep 4; printf 'x\n' > "$TMP/late/in/job.json"; : > "$TMP/late/in/dispatch" ) &
_t0=$(date +%s)
set +e
FFBOX_WORKSPACE="$WS" FFBOX_OUT="$TMP/late/out" FFBOX_IN="$TMP/late/in" \
FFBOX_UNITY_LICENSE="$TMP/unity-license.sh" FFBOX_IDLE_TTL_SECS=1 \
FFBOX_IDLE_FAILSAFE_MARGIN_SECS=10 FFBOX_POOL_POLL_SECS=1 \
FFBOX_TURN_TASK=/nonexistent-turn-task \
    timeout 40 bash "$HERE/pool-task.sh" > "$TMP/late.log" 2>&1
set -e
wait 2>/dev/null || true
grep -q 'dispatched after' "$TMP/late.log" \
    && ok "a dispatch arriving inside the margin is served, not walked out on" \
    || bad "the container left before the dispatch landed"

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
