#!/bin/sh
# test_update_drain.sh — whose drain flag is it, and who may lift it.
#
#   sh ffbox/test_update_drain.sh
#
# THE BUG THIS EXISTS FOR. A drain flag is a file, and `ffwatch drain`, `ffgithubrunners drain`
# and update_ffbox.sh all created the same file with no mark on it. So "stranded by an updater
# that crashed" and "set by a person two minutes ago" were indistinguishable, and the updater
# cleared both on every five-minute pass. The comment defending that said it was "safe only
# because of the flock", which is not what the flock proves: it guarantees one updater at a time
# and says nothing about whether an updater made the flag.
#
# Hit for real on 2026-09-08, draining the CI lane by hand for the ffwatch cut-over: the drain was
# lifted by an update pass that a config edit had triggered, and the only trace was one line in
# the journal.
#
# THE REAL FUNCTIONS, EXTRACTED, NOT A COPY. update_ffbox.sh cannot be sourced -- it runs top to
# bottom and updates the box -- so the two functions are pulled out with awk and driven here. An
# earlier version of a sibling test copied the logic under test into itself and would have gone on
# passing with the real thing deleted; that is the mistake this avoids.

set -u

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  ok   %s\n' "$*"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL %s\n' "$*"; }

SRC=$HERE/update_ffbox.sh
[ -r "$SRC" ] || { printf '  FAIL cannot read %s\n' "$SRC"; exit 1; }

{
    awk '/^clear_stranded_drains\(\)/,/^}$/' "$SRC"
    awk '/^lift_drain\(\)/,/^}$/' "$SRC"
} > "$TMP/fns.sh"
# A GUARD ON THE EXTRACTION ITSELF. An awk range that stops matching -- a rename, a brace moved --
# silently yields an empty file, and every case below would then pass against nothing at all.
for _fn in clear_stranded_drains lift_drain; do
    grep -q "^$_fn()" "$TMP/fns.sh" || {
        printf '  FAIL could not extract %s from update_ffbox.sh; nothing below tests anything\n' "$_fn"
        exit 1
    }
done
sh -n "$TMP/fns.sh" || { printf '  FAIL the extracted functions are not valid shell\n'; exit 1; }

D=$TMP/config
mkdir -p "$D/githubrunners"

# The variables the two functions close over, exactly as update_ffbox.sh sets them.
harness() {
    cat > "$TMP/run.sh" <<EOF
CONFIG_DIR=$D
DRAIN_SWITCH=\$CONFIG_DIR/draining
DRAIN_OWNED=\$CONFIG_DIR/update.drain-owned
DRY_RUN=0
FLAG_LIFTED=0
log() { printf '    | %s\n' "\$*"; }
. $TMP/fns.sh
$1
EOF
    sh "$TMP/run.sh"
}

reset()   { rm -f "$D/draining" "$D/githubrunners/drain" "$D/update.drain-owned"; }
agent()   { printf 'by hand\n' > "$D/draining"; }
ci()      { printf 'by hand\n' > "$D/githubrunners/drain"; }
claim()   { printf 'owned\n'   > "$D/update.drain-owned"; }
gone()    { [ ! -e "$1" ]; }

printf '\nan operator drain is not the updater'"'"'s to lift\n'

reset; ci
harness 'clear_stranded_drains; lift_drain' >/dev/null
gone "$D/githubrunners/drain" && bad "a CI drain set by a person must survive an update pass" \
                             || ok "a CI drain set by a person survives an update pass"

reset; agent
harness 'clear_stranded_drains; lift_drain' >/dev/null
gone "$D/draining" && bad "an agent drain set by a person must survive too" \
                   || ok "and so does an agent-lane one"

# THE PASS STILL RUNS. A drained box should still take code; what it must not do is decide the
# drain is over. So the only thing asserted above is that the flags are still there afterwards.
reset; ci
out=$(harness 'clear_stranded_drains; lift_drain')
case "$out" in
    *"did not set it"*) ok "and it says so, rather than leaving an operator to infer it" ;;
    *)                  bad "the pass must say it is leaving somebody else's drain alone" ;;
esac

printf '\na drain the updater stranded IS its to clear\n'

reset; ci; agent; claim
harness 'clear_stranded_drains' >/dev/null
gone "$D/githubrunners/drain" && ok "a CI drain with the marker beside it is cleared" \
                              || bad "a stranded CI drain must be cleared"
gone "$D/draining" && ok "and the agent one with it" || bad "a stranded agent drain must be cleared"
gone "$D/update.drain-owned" && ok "and the marker goes, so the next pass does not repeat this" \
                             || bad "the marker must be consumed"

printf '\nand its own drain, in an ordinary pass\n'

reset
harness 'clear_stranded_drains; claim_and_drain() { printf owned > "$DRAIN_OWNED"; printf x > "$CONFIG_DIR/githubrunners/drain"; }; claim_and_drain; lift_drain' >/dev/null
gone "$D/githubrunners/drain" && ok "a drain this run set is lifted at the end" \
                              || bad "the updater must lift its own drain"
gone "$D/update.drain-owned" && ok "along with the marker" || bad "the marker must be removed"

# THE ORDER THAT MAKES THE STRANDED CASE RECOVERABLE. The marker is written BEFORE the flags, so a
# crash between the two leaves a marker and no flags -- recoverable -- rather than flags nobody
# owns, which is the state this whole mechanism exists to get out of.
printf '\nthe crash window\n'
reset; claim
harness 'clear_stranded_drains' >/dev/null
gone "$D/update.drain-owned" && ok "a marker with no flags is cleaned up, not left to accumulate" \
                             || bad "a lone marker must be cleared"

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
