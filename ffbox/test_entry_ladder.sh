#!/bin/sh
# test_entry_ladder.sh — offline tests for WHICH cache entry a run restores from.
#
#   sh ffbox/test_entry_ladder.sh
#
# NO DOCKER, NO UNITY, NO NETWORK. `docker` is a stub on PATH, the cache entries are empty files
# with the right names, and the mirror is a real little git repository with a master, a develop
# ahead of it, and branches off each. ffbox itself is the real script, taken as far as the line
# that names the entry it chose.
#
# WHY THIS IS WORTH A SUITE. The ladder is four lines that cost minutes. A branch has no entry of
# its own until CI writes one, and until 2026-09-11 the next rung was master — so every
# develop-based ffbox/* branch restored master's tar and then reset the worktree across everything
# develop had changed since (4,094 files that day), which Unity re-imports before it compiles a
# line. Nothing failed; runs were just slower than the entry sitting unread beside the one they
# took. That is exactly the kind of regression a suite catches and a person does not.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  ok   %s\n' "$*"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL %s\n' "$*"; }

# --- the stubs ------------------------------------------------------------------------------
mkdir -p "$TMP/bin"
cat > "$TMP/bin/docker" <<'STUB'
#!/bin/sh
case "$1 $2" in
    "image inspect")   exit 0 ;;
    "network inspect") exit 0 ;;
    "inspect -f")      echo true; exit 0 ;;
    "run -d")          echo deadbeefcafe0123; exit 0 ;;
esac
exit 0
STUB
chmod +x "$TMP/bin/docker"

# --- the mirror -------------------------------------------------------------------------------
#
# THE SHAPE THE BOX ACTUALLY HAS: develop carries master's head plus its own commits, and work
# branches off one or the other. The tie case is the one worth building deliberately — a branch
# off master forks develop at the SAME commit it forks master at, because develop has master
# behind it, and only the tie-break says which name that means.
SRC=$TMP/src
mkdir -p "$SRC/ProjectSettings"
echo "m_EditorVersion: 6000.3.19f1" > "$SRC/ProjectSettings/ProjectVersion.txt"
g() { git -C "$SRC" -c user.email=t@t -c user.name=t "$@"; }
git -C "$SRC" init -q -b master
g add -A
g commit -qm "master 1"
g checkout -q -b develop
echo one > "$SRC/one.txt"; g add -A; g commit -qm "develop 1"
echo two > "$SRC/two.txt"; g add -A; g commit -qm "develop 2"
g checkout -q -b ffbox/off-develop
echo work > "$SRC/work.txt"; g add -A; g commit -qm "work on develop"
g checkout -q master
g checkout -q -b ffbox/off-master
echo other > "$SRC/other.txt"; g add -A; g commit -qm "work on master"
g checkout -q master
mkdir -p "$TMP/cache"
git clone -q --bare "$SRC" "$TMP/cache/mirror/FinalFactory.git"

# --- the entries ------------------------------------------------------------------------------
# Names only: ffbox never opens one, it only picks it.
mkdir -p "$TMP/cache/entries"
entries() {
    rm -f "$TMP/cache/entries"/*.tar
    for _e in "$@"; do : > "$TMP/cache/entries/$_e@6000.3.19f1.tar"; done
    unset _e
}

printf 'CLAUDE_CODE_OAUTH_TOKEN=stub\n' > "$TMP/secrets.env"
chmod 600 "$TMP/secrets.env"
echo '{"pools": {"ffdev": {}}}' > "$TMP/config.json"

# chose <ref> [--base-refs "A B"] -> the basename of the entry ffbox picked, or "" if it refused
chose() {
    _r=$1; shift
    mkdir -p "$TMP/pool"
    set +e
    PATH="$TMP/bin:$PATH" \
    FFBOX_SECRETS="$TMP/secrets.env" \
    FFBOX_CONFIG_JSON="$TMP/config.json" \
    FFBOX_CACHE_DIR="$TMP/cache" \
        timeout 120 bash "$HERE/ffbox" --stage-pool ladder --pool-dir "$TMP/pool" \
            --agent-class ffdev --network bridge --ref "$_r" "$@" > "$TMP/log" 2>&1
    RC=$?
    set -e
    unset _r
    sed -n 's/.*\[ffbox\] workspace: .*from \(.*\)$/\1/p' "$TMP/log" | tail -1
}

# took <expected> <label> ... -- reads CHOSE, which the call before it set. Reporting what was
# actually picked matters more than it looks: every wrong answer here is a tar that exists and
# restores fine, so a failure that printed only "FAIL" would send somebody to the wrong file.
took() {
    _want=$1; shift
    if [ "$CHOSE" = "$_want@6000.3.19f1.tar" ]; then
        ok "$*"
    else
        bad "$* (chose ${CHOSE:-nothing}, wanted $_want@6000.3.19f1.tar)"
    fi
    unset _want
}

echo "cache entry ladder: which tar a ref restores from"

# --- rung one: the branch's own entry ----------------------------------------------------------
entries master develop ffbox-off-develop
CHOSE=$(chose ffbox/off-develop --base-refs "master develop")
took ffbox-off-develop "a branch with its own entry takes it"

# --- rung two: the base it descends from -------------------------------------------------------
#
# THE ONE THIS SUITE EXISTS FOR. No entry for the branch, and master's is right there being the
# wrong answer.
entries master develop
CHOSE=$(chose ffbox/off-develop --base-refs "master develop")
took develop "a develop-based branch with no entry takes develop's, not master's"

# A branch off master forks develop at the same commit, because develop carries master's head, so
# nothing about ancestry separates the two names and the distance does: develop has run on since
# that commit and master has not.
CHOSE=$(chose ffbox/off-master --base-refs "master develop")
took master "a master-based branch keeps master on the tie"

# THE SAME CASE WITH THE LIST THE OTHER WAY UP, which is not hypothetical: ffwatch moves an
# operator's requested base to the front of --base-refs, so "develop master" is the ordinary
# shape of a conversation that asked for develop. A tie-break that read "first listed wins" would
# hand every master-based branch develop's tar, which is the FARTHER one.
CHOSE=$(chose ffbox/off-master --base-refs "develop master")
took master "and keeps it even when develop is listed first"

# --base-refs is a statement about publishing; which tar is closest is not a policy question, so a
# hand-run ffbox that passes none still gets the near entry.
CHOSE=$(chose ffbox/off-develop)
took develop "and with no --base-refs at all the default pair still finds develop"

# --- rung three and four: nothing to descend from ----------------------------------------------
#
# IT ONLY EVER NARROWS. A ref the mirror has never heard of used to land on master and still does:
# every base candidate fails, and the ladder is the one it was before this rung existed.
entries master develop
CHOSE=$(chose 0000000000000000000000000000000000000000 --base-refs "master develop")
took master "a ref the mirror cannot resolve falls through to master"

# With neither the branch's entry nor its base's, the newest tar at this editor version is better
# than refusing to start.
entries ffbox-somebody-elses
CHOSE=$(chose ffbox/off-develop --base-refs "master develop")
took ffbox-somebody-elses "with no base entry either, the most recent tar is taken"

# --- the base rung never reaches past the cache ------------------------------------------------
#
# develop is a name in the mirror whether or not anybody has ever built it. Choosing it when no
# such tar exists would skip master's, which does, and start the run cold.
entries master
CHOSE=$(chose ffbox/off-develop --base-refs "master develop")
took master "a base with no entry of its own does not shadow master's"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
