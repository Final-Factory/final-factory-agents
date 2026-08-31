#!/bin/sh
# test_pin.sh — offline tests for image-update.sh's --pin-only path.
#
#   sh ffbox/runners/test_pin.sh
#
# NO DAEMON, NO GITHUB, NO NETWORK. It builds a throwaway checkout with a fake ffbox/Dockerfile
# and a real BARE repository as its origin, so the push is a real push and a rejected push is a
# real rejection. `--pin-only` exists so this can exercise the commit path without a Unity base
# image and a forty-minute build.
#
# THE CASES THAT MATTER ARE THE REFUSALS. Writing the version down is the easy half; what has to
# be right is that this never leaves the checkout in a state that stops the self-updater —
# a dirty tree and an unpushed commit are both reasons update_ffbox.sh does nothing, so a failed
# push has to roll back to exactly where it started.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  ok   %s\n' "$*"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL %s\n' "$*"; }
is()  { if [ "$1" = "$2" ]; then ok "$3"; else bad "$3: got '$1', want '$2'"; fi; }

# Nothing here may touch the real config or the real daemon.
export FFGITHUBRUNNERS_CONFIG_DIR="$TMP/config"
export FFBOX_CONFIG_DIR="$TMP/config"
mkdir -p "$FFBOX_CONFIG_DIR"

git_() { git -C "$TMP/work" -c user.name=test -c user.email=test@test "$@"; }

pin_of() { sed -n 's/^ARG RUNNER_VERSION=//p' "$TMP/work/ffbox/Dockerfile" | head -1; }

# A checkout that looks like this one: ffbox/Dockerfile with the ARG, and the scripts under
# ffbox/runners/ so $HERE/.. resolves to the fake ffbox/.
build_checkout() {
    rm -rf "$TMP/work" "$TMP/origin"
    git init --quiet --bare "$TMP/origin"
    mkdir -p "$TMP/work/ffbox/runners/lib"
    cp "$HERE/image-update.sh" "$TMP/work/ffbox/runners/"
    cp "$HERE/lib/config.sh"   "$TMP/work/ffbox/runners/lib/"
    printf 'ARG UNITY_IMAGE=unityci/editor:test\nARG RUNNER_VERSION=2.337.0\nARG GH_VERSION=2.98.0\n' \
        > "$TMP/work/ffbox/Dockerfile"
    git init --quiet -b master "$TMP/work"
    git_ add -A
    git_ commit --quiet -m "initial"
    git_ remote add origin "$TMP/origin"
    git_ push --quiet -u origin master
}

pin() { sh "$TMP/work/ffbox/runners/image-update.sh" --pin-only "$1" 2>&1; }

printf '\nrecording a new version\n'
build_checkout
out=$(pin 2.338.0)
is "$(pin_of)" "2.338.0" "the Dockerfile now pins the new version"
printf '%s' "$out" | grep -q "recorded runner 2.338.0" && ok "it says what it did" || bad "no confirmation line: $out"
is "$(git_ log --oneline -1 --format=%s)" "ffghr: runner 2.337.0 -> 2.338.0" "the commit says which version to which"
is "$(git_ status --porcelain)" "" "the working tree is left clean"
is "$(git_ rev-parse HEAD)" "$(git_ rev-parse origin/master)" "and pushed, so HEAD is not ahead of origin"
git -C "$TMP/origin" show master:ffbox/Dockerfile | grep -q 'ARG RUNNER_VERSION=2.338.0' \
    && ok "origin has the new pin" || bad "origin does not have the new pin"

printf '\nnothing to do\n'
out=$(pin 2.338.0)
printf '%s' "$out" | grep -q "already pins 2.338.0" && ok "a version that is already pinned is a no-op" || bad "expected an already-pinned line: $out"
is "$(git_ rev-list --count HEAD)" 2 "and it does not make an empty commit"

printf '\nthe refusals\n'
# A DIRTY TREE STOPS THE SELF-UPDATER, so this must never add to one.
build_checkout
printf 'scratch\n' > "$TMP/work/ffbox/scratch.txt"
out=$(pin 2.338.0)
printf '%s' "$out" | grep -q "working tree is dirty" && ok "a dirty tree is refused" || bad "expected a dirty-tree refusal: $out"
is "$(pin_of)" "2.337.0" "and the Dockerfile is untouched"
rm -f "$TMP/work/ffbox/scratch.txt"

# BEHIND OR AHEAD OF ORIGIN. Committing here either invents a merge or stacks a second unpushed
# commit on a failed push, and an unpushed commit is itself a reason the updater does nothing.
build_checkout
git_ commit --quiet --allow-empty -m "unpushed local work"
out=$(pin 2.338.0)
printf '%s' "$out" | grep -q "HEAD and origin/master differ" && ok "a checkout that is ahead of origin is refused" || bad "expected a HEAD/origin refusal: $out"
is "$(pin_of)" "2.337.0" "and the Dockerfile is untouched"

printf '\nsomebody else pushed first\n'
# The common race, and it is caught BEFORE the commit: origin moved, so HEAD is no longer the
# remote and there is nothing safe to commit on top of.
build_checkout
before=$(git_ rev-parse HEAD)
git clone --quiet "$TMP/origin" "$TMP/other"
git -C "$TMP/other" -c user.name=other -c user.email=o@o commit --quiet --allow-empty -m "somebody else"
git -C "$TMP/other" push --quiet origin master
out=$(pin 2.338.0 || true)
printf '%s' "$out" | grep -q "HEAD and origin/master differ" && ok "a moved origin is caught before committing" || bad "expected a HEAD/origin refusal: $out"
is "$(git_ rev-parse HEAD)" "$before" "nothing was committed"
is "$(pin_of)" "2.337.0" "and the Dockerfile is untouched"

printf '\na push that fails after the commit\n'
# The narrow window the guards cannot close: everything checked out, the commit was made, and THEN
# the push was refused. A hook forces it here; in the wild it is a push landing in the same second
# or a credential that has expired. Both halves of the rollback matter — an unpushed commit and a
# dirty tree are each a reason update_ffbox.sh does nothing, so this must leave neither.
build_checkout
before=$(git_ rev-parse HEAD)
printf '#!/bin/sh\nexit 1\n' > "$TMP/origin/hooks/pre-receive"
chmod +x "$TMP/origin/hooks/pre-receive"
out=$(pin 2.338.0 || true)
printf '%s' "$out" | grep -q "push failed" && ok "the rejection is reported" || bad "expected a push-failure line: $out"
is "$(git_ rev-parse HEAD)" "$before" "HEAD is rolled back to where it started"
is "$(pin_of)" "2.337.0" "the Dockerfile is back to the old pin"
is "$(git_ status --porcelain)" "" "and the tree is clean, so the self-updater still runs"

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
