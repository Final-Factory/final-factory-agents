#!/usr/bin/env bash
#
# harvest-workspace.sh — turn what the run did into inert files, from inside the container.
#
# The workspace is a tmpfs the host cannot see, so the harvest has to happen in here. It writes
# everything the host needs into /ffbox/out and touches nothing else:
#
#   status.txt          porcelain status at exit
#   head.txt            the commit the run ended on
#   branch.txt          the branch the work should publish as
#   publish_base.txt    the named branch it descends from, when there is one
#   publish_base_sha    the commit the range starts at
#   changed_files.txt   the range's changed paths
#   changes.patch       the range as a diff
#   work.bundle         the range as a bundle
#   harvest_error.txt   why there is nothing to publish, when that is the answer
#
# WHAT THIS IS NOT. The checks below are the same ones the host used to run and they are not a
# security boundary — ffbox/ffbox has always said so, and the containment is that this container
# holds no credential. They catch a range that has stopped meaning what the host assumes. The
# host re-derives every one of them from the bundle before publishing, because a run that skipped
# them would otherwise be taken at its word.
set -euo pipefail

WORKSPACE=${FFBOX_WORKSPACE:-/opt/actions-runner/_work/FinalFactory/FinalFactory}
OUT=${FFBOX_OUT:-/ffbox/out}
BRANCH=${FFBOX_BRANCH:-}
BRANCH_PREFIX=${FFBOX_BRANCH_PREFIX:-}
BASE_REFS=${FFBOX_BASE_REFS:-}
# WHERE THE PUBLISHED RANGE STARTS, when the answer is not "the base this work descends from".
# See the block below the base scan.
RANGE_FROM_START=${FFBOX_RANGE_FROM_START:-0}
# FROM THE FILE, NOT JUST THE ENVIRONMENT. restore-workspace.sh records base_sha.txt at the moment
# it finishes preparing the tree -- which is the only time anyone knows it. The host cannot pass it
# in: it launches the container before the workspace exists, so there is no sha to name yet.
#
# Missing it is not cosmetic. Without a base there is no range to bundle, and the run reports "the
# work descends neither from any known branch nor from the commit this run started at" -- which
# reads like the agent did something odd rather than like a value never got wired through. Found on
# the first real run; the component tests passed FFBOX_BASE_SHA by hand and never noticed.
BASE_SHA=${FFBOX_BASE_SHA:-}
# `|| true` INSIDE the substitution, and it is load-bearing. This runs under `set -euo
# pipefail`, so when base_sha.txt is absent head exits 1, pipefail carries that out of the
# pipeline, and the assignment on the right of `||` makes the whole compound non-zero — which
# under `set -e` ends the script HERE, before a single file has been harvested, with an empty
# stderr. The caller logs "harvest failed" and the run's work goes with the tmpfs.
#
# An absent base_sha.txt is not an error worth dying on: restore-workspace.sh writes it
# best-effort, and the block below is written to work without one (it falls back to the base
# refs, and refuses honestly if it can find nothing). Found by pointing the branch-derivation
# test at this script instead of at a fragment cut out of ffbox.
[ -n "$BASE_SHA" ] \
    || BASE_SHA=$( (head -1 "${FFBOX_OUT:-/ffbox/out}/base_sha.txt" 2>/dev/null || true) | tr -d ' \r\n')
RUN_ID=${FFBOX_RUN_ID:-unknown}
GIT_NAME=${FFBOX_GIT_NAME:-ffbox}
GIT_EMAIL=${FFBOX_GIT_EMAIL:-ffbox@final-factory.invalid}
PROTECTED=${FFBOX_PROTECTED_BRANCHES:-develop master main}

log() { printf '[harvest] %s\n' "$*"; }
g()   { git -C "$WORKSPACE" "$@"; }

# GROUP-WRITABLE, because the host rewrites some of these. /ffbox/out is setgid ffbox-container and
# the host account is in that group, but files this container creates default to 0644 -- so the
# host's own `>` onto changed_files.txt failed with Permission denied, and it silently kept reading
# the copy this container wrote. That defeats the entire point of re-deriving from the bundle.
umask 002

mkdir -p "$OUT"
[ -d "$WORKSPACE/.git" ] || { log "no .git in the workspace; nothing to harvest"; exit 0; }

export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0="$WORKSPACE"

harvest_failed() {
    printf '%s\n' "$1" > "$OUT/harvest_error.txt"
    rm -f "$OUT/work.bundle" "$OUT/branch.txt" "$OUT/changes.patch"
    log "NOT PUBLISHING: $1"
}

g status --porcelain > "$OUT/status.txt" 2>/dev/null || true
g rev-parse HEAD > "$OUT/head.txt" 2>/dev/null || true

if [ -z "$BRANCH" ]; then
    # Patch-only mode, as `ffbox` without --branch has always been.
    g add -A -- . ':(exclude).github' 2>/dev/null || true
    g diff --cached --binary ${BASE_SHA:+"$BASE_SHA"} > "$OUT/changes.patch" 2>/dev/null || true
    g reset >/dev/null 2>&1 || true
    [ -s "$OUT/changes.patch" ] || rm -f "$OUT/changes.patch"
    log "patch-only harvest complete"
    exit 0
fi

# WHICH BRANCH THIS WORK IS FOR, read off HEAD before anything moves a ref.
#
# THE FORK POINT, NOT THE BASE'S HEAD. This used to require `origin/<name>` itself to be an
# ancestor of HEAD, which asks whether the branch is still a fast-forward of the base as the
# container sees it. A first turn is; a turn continuing a branch that has fallen behind is not,
# and every candidate then failed and the work was published with NO name at all — which the
# host could only paper over with its configured default. Branches fall behind here as a matter
# of course, because the box merges its own pull requests, so this was the ordinary state of a
# continuation rather than an edge of one.
#
# `git merge-base` answers the question that was actually being asked — where did this work
# leave that branch — and it has an answer whenever the two share any history at all, which a
# clone of the same repo always does. It also agrees with the host: ffwatch's pr_base() verifies
# the name against fork points too, and the answer the agent is given has to be the answer the
# pull request ends up targeting.
PUBLISH_BASE= PUBLISH_BASE_SHA= PUBLISH_BASE_DIST=
for _name in $BASE_REFS; do
    _sha=$(g rev-parse --verify --quiet "origin/${_name}^{commit}" 2>/dev/null) \
      || _sha=$(g rev-parse --verify --quiet "${_name}^{commit}" 2>/dev/null) || continue
    _fork=$(g merge-base "$_sha" HEAD 2>/dev/null) || continue
    [ -n "$_fork" ] || continue
    # HOW FAR THAT BASE HAS RUN ON since the work left it. Nothing but a tie-break, and it
    # matters because with fork points the ties are the COMMON case rather than the rare one:
    # work off master has the same fork point with develop as it has with master, since develop
    # carries master's head too. The old head-ancestry scan got that difference for free by
    # skipping develop outright, and reading "first listed wins" onto it would have answered
    # develop for every master-based branch on the box.
    _dist=$(g rev-list --count "${_fork}..${_sha}" 2>/dev/null) || _dist=0
    [ -n "$_dist" ] || _dist=0
    # THE MOST SPECIFIC BASE THE WORK DESCENDS FROM, and on a tie the FIRST one listed. A
    # branch off develop has master behind it as well, so develop's fork point is the descendant
    # of the two and the more specific answer; a branch off master forks both at the same commit
    # and is settled by the distance above.
    #
    # STRICTLY a descendant, which is the half that was wrong. `is-ancestor X X` is true, so an
    # equality test let every later candidate replace the one before it and the LAST listed won
    # — the exact opposite of the documented rule, on the one occasion it matters: the moment
    # after a release merge, when master and develop are the same commit and publish_bases
    # leads with master to say which of them a tie should mean.
    _better=0
    if [ -z "$PUBLISH_BASE_SHA" ]; then
        _better=1
    elif [ "$_fork" != "$PUBLISH_BASE_SHA" ] \
         && g merge-base --is-ancestor "$PUBLISH_BASE_SHA" "$_fork" 2>/dev/null; then
        _better=1
    elif [ "$_fork" = "$PUBLISH_BASE_SHA" ] && [ "$_dist" -lt "$PUBLISH_BASE_DIST" ]; then
        _better=1
    fi
    if [ "$_better" = 1 ]; then
        PUBLISH_BASE=$_name; PUBLISH_BASE_SHA=$_fork; PUBLISH_BASE_DIST=$_dist
    fi
done
if [ -z "$PUBLISH_BASE_SHA" ] && [ -n "$BASE_SHA" ] \
   && g merge-base --is-ancestor "$BASE_SHA" HEAD 2>/dev/null; then
    PUBLISH_BASE_SHA=$BASE_SHA
fi
[ -z "$PUBLISH_BASE" ] || log "this work is based on $PUBLISH_BASE"

# THE RANGE STARTS WHERE THE RUN DID, when the host asks for it -- which it does for a run
# continuing a branch it did not create.
#
# The two questions the scan above answers get separated here. WHICH NAMED BRANCH THIS WORK IS
# FOR stays as it is: PUBLISH_BASE is untouched, publish_base.txt still names master or develop,
# and the pull request still targets it. WHERE THE PUBLISHED RANGE BEGINS moves to the commit
# restore-workspace.sh left the workspace on.
#
# Without this a run on somebody else's branch bundles origin/develop..HEAD, which carries every
# commit they put on it: the identity check below then refuses the whole publication for
# "commits claim an identity this run does not own", and the host's changed-file ceiling counts
# their files against this run. Both are correct about the range and wrong about the question --
# what either is meant to bound is what THIS RUN did.
#
# AN ANCESTRY TEST AND NO FALLBACK. If the run's start commit is not behind HEAD, something
# rewrote history underneath the run, and the honest answer is to refuse here rather than
# quietly bundle from the base ref and produce the identity refusal three steps later with a
# message about the wrong thing.
if [ "$RANGE_FROM_START" = "1" ]; then
    if [ -z "$BASE_SHA" ]; then
        harvest_failed "the harness asked for the range to start where the run did, but no start commit was recorded"
        exit 0
    fi
    if ! g merge-base --is-ancestor "$BASE_SHA" HEAD 2>/dev/null; then
        harvest_failed "the work does not descend from the commit this run started at ($BASE_SHA)"
        exit 0
    fi
    PUBLISH_BASE_SHA=$BASE_SHA
    log "the range starts at the commit this run began on ($BASE_SHA)"
fi

g add -A -- . ':(exclude).github' 2>/dev/null || true
if ! g diff --cached --quiet 2>/dev/null; then
    if [ "$(g rev-list --count "${PUBLISH_BASE_SHA}..HEAD" 2>/dev/null || echo 0)" = "0" ]; then
        MSG="ffbox ${RUN_ID}: agent work"
    else
        MSG="ffbox ${RUN_ID}: uncommitted work at exit"
    fi
    g -c user.name="$GIT_NAME" -c user.email="$GIT_EMAIL" \
      commit --quiet --no-verify -m "$MSG" 2>/dev/null || true
fi

OK=1
CURRENT=$(g symbolic-ref --short -q HEAD 2>/dev/null || echo "")
for p in $PROTECTED; do
    [ "$CURRENT" = "$p" ] || continue
    harvest_failed "the run ended on $p instead of on a branch of its own"; OK=0; break
done

if [ "$OK" = 1 ] && [ -n "$BRANCH_PREFIX" ] && [ -n "$CURRENT" ] && [ "$CURRENT" != "$BRANCH" ]; then
    NAME=$(printf '%s' "${CURRENT#"$BRANCH_PREFIX"}" | tr -c 'A-Za-z0-9._/-' '-' \
           | sed -e 's|//*|/|g' -e 's/--*/-/g' | cut -c1-80 | sed -e 's|^[-./]*||' -e 's|[-./]*$||')
    RENAMED="${BRANCH_PREFIX}${NAME}-${RUN_ID}"
    if [ -n "$NAME" ] && g check-ref-format --branch "$RENAMED" >/dev/null 2>&1; then
        log "the agent worked on $CURRENT; publishing it as $RENAMED"; BRANCH=$RENAMED
    fi
fi
if [ "$OK" = 1 ] && [ "$CURRENT" != "$BRANCH" ]; then
    g branch -f "$BRANCH" HEAD >/dev/null 2>&1 || { harvest_failed "the run's work could not be named $BRANCH"; OK=0; }
fi
if [ "$OK" = 1 ] && [ -z "$PUBLISH_BASE_SHA" ]; then
    harvest_failed "the work descends neither from ${BASE_REFS:-any known branch} nor from the commit this run started at (${BASE_SHA:-none recorded}), so it cannot be bundled"; OK=0
fi
if [ "$OK" = 1 ]; then
    FOREIGN=$(g log --format='%ae%n%ce' "${PUBLISH_BASE_SHA}..${BRANCH}" 2>/dev/null | sort -u | grep -Fxv "$GIT_EMAIL" || true)
    [ -z "$FOREIGN" ] || { harvest_failed "commits claim an identity this run does not own: $(printf '%s' "$FOREIGN" | tr '\n' ' ')"; OK=0; }
fi

if [ "$OK" = 1 ]; then
    g diff --name-only "${PUBLISH_BASE_SHA}..${BRANCH}" > "$OUT/changed_files.txt" 2>/dev/null || true
    if [ -s "$OUT/changed_files.txt" ]; then
        printf '%s\n' "$BRANCH" > "$OUT/branch.txt"
        [ -z "$PUBLISH_BASE" ] || printf '%s\n' "$PUBLISH_BASE" > "$OUT/publish_base.txt"
        printf '%s\n' "$PUBLISH_BASE_SHA" > "$OUT/publish_base_sha.txt"
        g diff --binary "${PUBLISH_BASE_SHA}..${BRANCH}" > "$OUT/changes.patch" 2>/dev/null || true
        # The RANGE, not the branch: a full bundle carries the project's whole history.
        g bundle create "$OUT/work.bundle" "${PUBLISH_BASE_SHA}..${BRANCH}" >/dev/null 2>&1 \
            && log "bundled $(wc -l < "$OUT/changed_files.txt") file(s) on $BRANCH" \
            || { harvest_failed "the range could not be bundled"; }
    else
        log "no changes in the range"
    fi
fi
log "done"
