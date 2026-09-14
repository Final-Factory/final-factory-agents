#!/bin/sh
# test_update_fence.sh — update_ffbox.sh re-applies the container fence, quietly and never fatally.
#
#   sh ffbox/test_update_fence.sh
#
# THE BUG THIS EXISTS FOR. Nothing ran `ffbox-egress.sh up` after a machine was set up, so a merged
# change to ffbox/egress/allowlist.txt went unenforced until somebody recreated the proxy by hand.
# update_ffbox.sh now calls apply_fence on every pass. What has to hold: it runs `up` against the
# daemon ffbox uses, it says nothing when the fence was left alone (this runs every five minutes),
# it says what happened when it was not, and a failure never stops the update.
#
# THE REAL FUNCTION, EXTRACTED WITH awk the way test_update_drain.sh extracts its two. No docker:
# ffbox-egress.sh is a stub that records what it was run with.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM
PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  ok   %s\n' "$*"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL %s\n' "$*"; }

SRC=$HERE/update_ffbox.sh
awk '/^apply_fence\(\)/,/^}$/' "$SRC" > "$TMP/fns.sh"
if ! grep -q '^apply_fence()' "$TMP/fns.sh"; then
    printf '  FAIL could not extract apply_fence from update_ffbox.sh; nothing below tests anything\n'
    exit 1
fi

# What the function closes over, as update_ffbox.sh sets it.
REPO=$TMP/repo
mkdir -p "$REPO/ffbox/egress"
FFBOX_DOCKER_SOCK=/run/test-fence/docker.sock
DRY_RUN=0
REC=$TMP/record
log() { printf '[ffbox-update] %s\n' "$*"; }
as_owner() { "$@"; }
# shellcheck disable=SC1090
. "$TMP/fns.sh"

stub() {   # stub <exit code> <output line>
    cat > "$REPO/ffbox/egress/ffbox-egress.sh" <<EOF
#!/bin/sh
printf 'args=%s docker_host=%s\n' "\$*" "\$DOCKER_HOST" >> "$REC"
printf '%s\n' "$2"
exit $1
EOF
}

echo "update: the container fence"

: > "$REC"
stub 0 "==> ffbox-egress is already up with this image, mode and allowlist — leaving it alone"
out=$(apply_fence); rc=$?
grep -q '^args=up docker_host=unix:///run/test-fence/docker.sock$' "$REC" \
    && ok "it runs 'up' against the daemon ffbox uses" \
    || bad "it runs 'up' against the daemon ffbox uses (recorded: $(cat "$REC"))"
[ -z "$out" ] && ok "and says nothing when the fence was left alone" \
    || bad "and says nothing when the fence was left alone (said: $out)"

: > "$REC"
stub 0 "==> the image, mode or allowlist changed; recreating ffbox-egress"
out=$(apply_fence)
case "$out" in
    *"container fence:"*"recreating ffbox-egress"*) ok "a fence it recreated is reported" ;;
    *) bad "a fence it recreated is reported (said: $out)" ;;
esac

: > "$REC"
stub 1 "ffbox-egress.sh: docker not found"
set +e
out=$(apply_fence); rc=$?
set -e
[ "$rc" -eq 0 ] && ok "a failing 'up' never stops the update" \
    || bad "a failing 'up' never stops the update (rc=$rc)"
case "$out" in
    *WARNING*"keeps enforcing"*) ok "and it says the fence keeps its current list" ;;
    *) bad "and it says the fence keeps its current list (said: $out)" ;;
esac

: > "$REC"
DRY_RUN=1
out=$(apply_fence)
DRY_RUN=0
[ ! -s "$REC" ] && ok "a dry run touches nothing" || bad "a dry run touches nothing"
case "$out" in *"would re-apply"*) ok "and says what it would do" ;; *) bad "and says what it would do" ;; esac

rm -f "$REPO/ffbox/egress/ffbox-egress.sh"
set +e
out=$(apply_fence); rc=$?
set -e
[ "$rc" -eq 0 ] && [ -z "$out" ] && ok "a checkout without the fence script is not an error" \
    || bad "a checkout without the fence script is not an error (rc=$rc, said: $out)"

grep -qE '^[[:space:]]+apply_fence$' "$SRC" \
    && [ "$(grep -cE '^[[:space:]]*apply_fence$' "$SRC")" -ge 2 ] \
    && ok "update_ffbox.sh calls it on the no-change pass and inside the update window" \
    || bad "update_ffbox.sh calls it on the no-change pass and inside the update window"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
