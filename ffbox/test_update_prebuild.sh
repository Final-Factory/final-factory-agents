#!/bin/sh
# test_update_prebuild.sh — update_ffbox.sh's section 2b: the right tree, the right tag, never fatal.
#
#   sh ffbox/test_update_prebuild.sh
#
# WHAT IT PINS. The pre-build exists so that setup.sh's image build, which runs with ffbox stopped,
# is a cache hit. Three things decide whether it is safe and whether it works:
#
#   * it builds the commit ABOUT TO BE DEPLOYED, not whatever the working tree holds;
#   * it builds under the scratch tag, never ffbox:latest -- ffwatch is still starting containers
#     from that tag with the unmerged checkout mounted into them;
#   * it exports the Claude version it resolved, so the build inside the window asks for the same.
#
# And every failure returns 0, because a failed pre-build must degrade to the old in-window build,
# not stop an update.
#
# NO DAEMON, NO NETWORK. A scratch git repository whose ffbox/03-build.sh is a stub that writes down
# what it was handed. The function under test is the REAL one, extracted with awk the way
# test_update_drain.sh does it, and run under `set -eu` like the updater.

set -u

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  ok   %s\n' "$*"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL %s\n' "$*"; }
is()  { if [ "$1" = "$2" ]; then ok "$3"; else bad "$3: got '$1', want '$2'"; fi; }
has() { case "$1" in *"$2"*) ok "$3" ;; *) bad "$3: no '$2' in: $1" ;; esac; }

SRC=$HERE/update_ffbox.sh
awk '/^prebuild_image\(\)/,/^}$/' "$SRC" > "$TMP/fns.sh"
grep -q '^prebuild_image()' "$TMP/fns.sh" || {
    printf '  FAIL could not extract prebuild_image from update_ffbox.sh; nothing below tests anything\n'
    exit 1
}
sh -n "$TMP/fns.sh" || { printf '  FAIL the extracted function is not valid shell\n'; exit 1; }
# Read from the script rather than restated, so a renamed tag is tested as it is.
TAG=$(sed -n 's/^PREBUILD_TAG=//p' "$SRC" | head -1)
[ -n "$TAG" ] || { printf '  FAIL no PREBUILD_TAG= in update_ffbox.sh\n'; exit 1; }
[ "$TAG" != "ffbox:latest" ] && ok "the scratch tag is not ffbox:latest ($TAG)" \
                             || bad "the pre-build must never tag ffbox:latest"

R=$TMP/repo
git_r() { git -C "$R" -c user.name=t -c user.email=t@t "$@"; }
git init --quiet -b master "$R"
mkdir -p "$R/ffbox"

# A commit whose 03-build.sh records what it was handed and exits $2.
commit_build() {   # $1 = marker, $2 = exit code
    cat > "$R/ffbox/03-build.sh" <<EOF
here=\$(CDPATH= cd -- "\$(dirname -- "\$0")" && pwd)
{
    printf 'marker=%s\n' '$1'
    printf 'tag=%s\n' "\${FFBOX_IMAGE:-}"
    printf 'claude=%s\n' "\${FFBOX_CLAUDE_VERSION:-}"
    printf 'mode=%s\n' "\$(stat -c %a "\$here/install-claude.sh")"
    printf 'dir=%s\n' "\$here"
} > "\$REC"
echo "stub build output for $1"
exit $2
EOF
    printf 'printf "%%s\\n" "${STUB_CLAUDE:-9.9.9}"\n' > "$R/ffbox/claude-version.sh"
    printf '#!/bin/sh\n' > "$R/ffbox/install-claude.sh"
    chmod 755 "$R/ffbox/install-claude.sh"
    git_r add -A
    git_r commit --quiet -m "$1"
    git_r rev-parse HEAD
}
C_ONE=$(commit_build one 0)
C_TWO=$(commit_build two 0)
C_FAIL=$(commit_build fail 1)
git_r rm --quiet ffbox/03-build.sh
git_r commit --quiet -m "no build script"
C_NONE=$(git_r rev-parse HEAD)

REC=$TMP/rec
STUB_CLAUDE=9.9.9
export REC STUB_CLAUDE
unset FFBOX_CLAUDE_VERSION

# The updater's own shape: set -eu, umask 0022 (its unit's), log and git_ as it defines them.
# $2 is shell run after the call, in the same process, to see what the function left behind.
run() {
    rm -f "$REC"
    (
        set -eu
        umask 0022
        log() { printf '[ffbox-update] %s\n' "$*"; }
        git_() { git -C "$R" "$@"; }
        PREBUILD_TAG=$TAG
        . "$TMP/fns.sh"
        prebuild_image "$1"
        echo "rc=$?"
        eval "${2:-:}"
    ) 2>&1
}
rec() { sed -n "s/^$1=//p" "$REC" 2>/dev/null; }

printf '\nthe deployed commit, under the scratch tag\n'
out=$(run "$C_TWO" 'printf "exported=%s\n" "${FFBOX_CLAUDE_VERSION:-}"')
has "$out" "rc=0" "it returns 0"
is "$(rec marker)" "two" "it builds the commit it was handed, not the working tree (HEAD has no build script)"
is "$(rec tag)" "$TAG" "and tags it $TAG, never ffbox:latest"
is "$(rec claude)" "9.9.9" "the build is handed the Claude version it looked up"
has "$out" "exported=9.9.9" "and that version stays exported, for setup.sh's build inside the window"
is "$(rec mode)" "755" "the export takes the updater's umask, so COPY modes match the merged checkout"
[ -n "$(rec dir)" ] && [ ! -d "$(rec dir)" ] && ok "the exported tree is removed afterwards" \
                                           || bad "the exported tree was left behind: $(rec dir)"

printf '\nthe Claude version\n'
out=$(STUB_CLAUDE=latest run "$C_ONE" 'printf "exported=%s\n" "${FFBOX_CLAUDE_VERSION:-}"')
is "$(rec claude)" "" "a lookup that yields no concrete version pins nothing"
has "$out" "exported=" "and exports nothing"
case "$out" in *"exported=latest"*) bad "\"latest\" must not be exported: claude-version.sh rejects it" ;; *) ok "\"latest\" in particular is not exported" ;; esac
out=$(FFBOX_CLAUDE_VERSION=1.2.3 run "$C_ONE")
is "$(rec claude)" "1.2.3" "a version already set by an operator wins over the lookup"

printf '\nnever fatal\n'
out=$(run "$C_FAIL" 'echo "still running"')
has "$out" "rc=0" "a failed build returns 0"
has "$out" "still running" "and the updater carries on"
has "$out" "WARNING: the pre-build failed" "it says so"
has "$out" "stub build output for fail" "with the build's own last lines"

out=$(run "$C_NONE" 'echo "still running"')
has "$out" "rc=0" "a commit with no 03-build.sh returns 0"
has "$out" "could not export" "and says it could not pre-build"
[ ! -e "$REC" ] && ok "and builds nothing" || bad "nothing should have been built"

out=$(run "0000000000000000000000000000000000000000" 'echo "still running"')
has "$out" "rc=0" "a commit that does not exist returns 0"
has "$out" "still running" "and the updater carries on"

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
