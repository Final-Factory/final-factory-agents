#!/bin/sh
# test_container_credential.sh — offline tests for the ONE way a git credential enters a container.
#
#   sh ffbox/test_container_credential.sh
#
# NO DOCKER, NO UNITY, NO NETWORK, NO REAL TOKEN. `docker` is a stub on PATH that records the
# argument list it was handed, the workspace cache is an empty file with the right name, and the
# mirror is a two-file git repository carrying a ProjectVersion.txt. ffbox itself is the real
# script.
#
# WHY THIS IS WORTH A TEST OF ITS OWN. Until 2026-09-04 the container held no git credential at
# all, and "nothing merges, ever" rested on that absence rather than on a deny list -- a pattern
# like Bash(git push*) is a tripwire that `sh -c 'git push'` walks straight through, measured.
# Now one agent class may carry a token. The properties below are what keep that from becoming a
# credential in every container:
#
#   * a class whose pools.<class>.github.container_token is null gets NOTHING, and ffagent -- the
#     lane that runs text written by strangers in a forum -- is that class;
#   * the token's VALUE never reaches argv, because /proc/<pid>/cmdline is world-readable and
#     that is the same reason ffwatch refuses to splice a token into a push url;
#   * the credential git ends up with is offered to github.com and to no other host.
#
# ITS OWN SECRETS FILE, and that line is load-bearing rather than tidiness: ffbox sources
# ~/.config/ffbox/secrets.env itself with `set -a`, so a test that does not override FFBOX_SECRETS
# reads the real one and its "the variable is not set" case silently tests nothing. That is
# exactly what happened while this was being written.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  ok   %s\n' "$*"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL %s\n' "$*"; }

# A token that is obviously not one, and distinctive enough to grep the whole argument list for.
FAKE_TOKEN=ffbox_test_token_MUST_NOT_APPEAR_IN_ARGV

# --- the stubs ------------------------------------------------------------------------------
mkdir -p "$TMP/bin"
cat > "$TMP/bin/docker" <<'STUB'
#!/bin/sh
# Records every argument, NUL-separated so a value carrying spaces or newlines cannot hide a
# match, then answers the four questions ffbox asks before it creates anything.
printf '%s\0' "$@" >> "$FFBOX_TEST_ARGV"
case "$1 $2" in
    "image inspect")   exit 0 ;;
    "network inspect") exit 0 ;;
    "inspect -f")      echo true; exit 0 ;;
    "run -d")          echo deadbeefcafe0123; exit 0 ;;
esac
exit 0
STUB
chmod +x "$TMP/bin/docker"

# The workspace cache: ffbox only needs an entry whose NAME matches <ref>@<unity version>.
mkdir -p "$TMP/cache/entries"
: > "$TMP/cache/entries/master@6000.3.19f1.tar"

# The mirror, which is where ffbox reads the Unity version the cache entry is named for.
mkdir -p "$TMP/src/ProjectSettings"
echo "m_EditorVersion: 6000.3.19f1" > "$TMP/src/ProjectSettings/ProjectVersion.txt"
git -C "$TMP/src" init -q -b master
git -C "$TMP/src" add -A
git -C "$TMP/src" -c user.email=t@t -c user.name=t commit -qm init
git clone -q --bare "$TMP/src" "$TMP/cache/mirror/FinalFactory.git"

# ffagent names nothing and ffdev names a key, which is the shape the split exists for.
cat > "$TMP/config.json" <<'CFG'
{"pools": {
  "ffagent": {"github": {"pr_token": "GH_PR_TOKEN", "container_token": null}},
  "ffdev":   {"github": {"pr_token": "GH_PR_TOKEN", "container_token": "GH_TEST_CONTAINER_TOKEN"}}
}}
CFG

# secrets.env with the token, and a second one without it. Mode 600 or ffbox warns.
printf 'CLAUDE_CODE_OAUTH_TOKEN=stub\nGH_TEST_CONTAINER_TOKEN=%s\n' "$FAKE_TOKEN" > "$TMP/secrets.env"
printf 'CLAUDE_CODE_OAUTH_TOKEN=stub\n' > "$TMP/secrets-notoken.env"
chmod 600 "$TMP/secrets.env" "$TMP/secrets-notoken.env"

# stage <name> <agent class> <network> <secrets file> -> LOG, and ARGV holds the docker argv
stage() {
    _n=$1; _cls=$2; _net=$3; _sec=$4
    ARGV="$TMP/$_n.argv"; LOG="$TMP/$_n.log"
    : > "$ARGV"
    mkdir -p "$TMP/pool"
    set +e
    PATH="$TMP/bin:$PATH" \
    FFBOX_TEST_ARGV="$ARGV" \
    FFBOX_SECRETS="$_sec" \
    FFBOX_CONFIG_JSON="$TMP/config.json" \
    FFBOX_CACHE_DIR="$TMP/cache" \
        timeout 120 bash "$HERE/ffbox" --stage-pool "$_n" --pool-dir "$TMP/pool" \
            --agent-class "$_cls" --network "$_net" --ref master > "$LOG" 2>&1
    RC=$?
    set -e
    unset _n _cls _net _sec
}

# How many times `-e FFBOX_GH_TOKEN` was handed to docker as a bare name, which is the forwarding
# form: the value comes from ffbox's own environment and never appears on the command line.
forwarded() { tr '\0' '\n' < "$ARGV" | grep -c '^FFBOX_GH_TOKEN$' || true; }

echo "container credential: which pools get one"

stage t1 ffdev bridge "$TMP/secrets.env"
[ "$RC" -eq 0 ] && ok "a pool that names an installed key stages" \
    || bad "a pool that names an installed key stages (rc=$RC): $(tail -3 "$LOG")"
[ "$(forwarded)" = 1 ] && ok "and its container is handed the credential" \
    || bad "and its container is handed the credential (saw $(forwarded))"
# THE ONE THAT MATTERS FOR /proc. A value spliced into argv is readable by every account on the
# box for as long as the process lives, which is why `-e NAME` is used rather than `-e NAME=value`.
if grep -qa "$FAKE_TOKEN" "$ARGV"; then
    bad "and the token's VALUE never reaches argv"
else
    ok "and the token's VALUE never reaches argv"
fi
grep -q 'git credential: ffdev containers carry' "$LOG" \
    && ok "and the launch says so, by variable name" \
    || bad "and the launch says so, by variable name"

stage t2 ffagent bridge "$TMP/secrets.env"
[ "$RC" -eq 0 ] && ok "a pool that names nothing stages" \
    || bad "a pool that names nothing stages (rc=$RC): $(tail -3 "$LOG")"
# THE PROPERTY THE WHOLE DESIGN RESTS ON. ffagent runs text written by strangers, and the token
# is sitting right there in the same secrets file.
[ "$(forwarded)" = 0 ] && ok "and its container is handed NO credential" \
    || bad "and its container is handed NO credential (saw $(forwarded))"
grep -qa "$FAKE_TOKEN" "$ARGV" && bad "and no token reaches its argv either" \
    || ok "and no token reaches its argv either"

stage t3 ffdev bridge "$TMP/secrets-notoken.env"
[ "$RC" -eq 0 ] && ok "naming a key nobody installed is not fatal" \
    || bad "naming a key nobody installed is not fatal (rc=$RC): $(tail -3 "$LOG")"
[ "$(forwarded)" = 0 ] && ok "and forwards nothing" \
    || bad "and forwards nothing (saw $(forwarded))"
# A run that finds out mid-way has no way to report why, so the launch has to say it.
grep -q 'names GH_TEST_CONTAINER_TOKEN as its container token' "$LOG" \
    && ok "and says which variable is missing" \
    || bad "and says which variable is missing"

stage t4 ffdev ffbox-net "$TMP/secrets.env"
# github.com is not in ffbox/egress/allowlist.txt, so on the fenced network the proxy refuses the
# SNI and a perfectly good token looks like a bad one.
grep -q 'not in ffbox/egress/allowlist.txt' "$LOG" \
    && ok "a credential on the fenced network is warned about" \
    || bad "a credential on the fenced network is warned about"
[ "$(forwarded)" = 1 ] && ok "and still passed, because the allowlist may have been edited" \
    || bad "and still passed, because the allowlist may have been edited (saw $(forwarded))"

# --- what the container does with it ---------------------------------------------------------
#
# The staging itself, as entrypoint.sh performs it: a ~/.git-credentials at 600 and a global
# credential.helper. Run here against a scratch HOME rather than inside a container, because what
# is under test is git's matching rather than docker's.
echo "container credential: what git does with it"
CHOME=$TMP/home
mkdir -p "$CHOME"
( umask 077; printf 'https://x-access-token:%s@github.com\n' "$FAKE_TOKEN" > "$CHOME/.git-credentials" )
git config --file "$CHOME/.gitconfig" credential.helper store

[ "$(stat -c '%a' "$CHOME/.git-credentials")" = 600 ] \
    && ok "the credential file is 600" \
    || bad "the credential file is 600 (is $(stat -c '%a' "$CHOME/.git-credentials"))"

_fill() {
    printf 'protocol=https\nhost=%s\n\n' "$1" \
        | env -i HOME="$CHOME" PATH="$PATH" GIT_TERMINAL_PROMPT=0 git credential fill 2>&1
}
_fill github.com | grep -q "password=$FAKE_TOKEN" \
    && ok "git offers it to github.com" \
    || bad "git offers it to github.com"
# MATCHED BY HOST, so a prompt that talks the agent into cloning from somewhere else does not get
# the token handed over with it.
if _fill gitlab.example.com | grep -q "$FAKE_TOKEN"; then
    bad "and to no other host"
else
    ok "and to no other host"
fi
# GIT_TERMINAL_PROMPT=0 is what turns "no credential" into one line that says so, instead of a
# read on a terminal that is not there.
_fill gitlab.example.com | grep -q 'terminal prompts disabled' \
    && ok "and an unauthenticated host fails in one legible line" \
    || bad "and an unauthenticated host fails in one legible line"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
