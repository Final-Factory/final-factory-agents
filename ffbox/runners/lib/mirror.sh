# The local git mirror: how a job gets the repository without reaching github.com.
#
# THE SHAPE. A job restores its workspace from an ffcache tarball that already carries .git, so all
# it needs from GitHub is the commits pushed since that tarball was made -- measured at a 1 second
# fetch for a 40-commit delta against 34 seconds for the whole repository. Serving that from a
# read-only mirror on ffghr-net removes the NEED for github.com rather than filtering the reach:
# there is no repository but ours at the other end, so "restricted to our repo" is a property of
# what exists rather than a rule someone maintains.
#
# WHY ON DEMAND. A slot launches its container BEFORE GitHub hands it a job, so at launch we do not
# know the branch -- the same constraint that forced the cache decision onto branch.info. Worse, a
# push triggers CI within seconds, so a mirror refreshed on a timer is behind exactly when it
# matters. So the job asks: it writes fetch.request naming the commit it needs, the supervisor
# fetches, and writes fetch.done. The job writes it before the restore step, which takes about
# forty seconds, so the 15s watchdog has slack and nothing usually waits at all.
#
# TWO HOPS, deliberately. The mirror fetches from golden and golden fetches from GitHub, so the
# credentials stay where they already are instead of being copied to a third place.

FFGHR_MIRROR_FETCH_TIMEOUT=${FFGHR_MIRROR_FETCH_TIMEOUT:-180}

# ffghr_mirror_ready -- is there a mirror to serve at all?
ffghr_mirror_ready() {
    [ -n "${MIRROR_DIR:-}" ] && [ -d "$MIRROR_DIR/$MIRROR_REPO" ] || return 1
    return 0
}

# ffghr_mirror_fetch WANT -- bring the mirror up to at least WANT, if it is not there already.
#
# NEVER FATAL, and the reason matters: while github.com is still on the egress allowlist a job that
# cannot get its commit here simply fetches it from GitHub as it always did. This is additive until
# that entry is removed, so every failure path is "leave it to GitHub" rather than "fail the job".
ffghr_mirror_fetch() {
    _want=${1:-}
    ffghr_mirror_ready || { echo "no mirror at ${MIRROR_DIR:-<unset>}"; return 1; }
    _repo="$MIRROR_DIR/$MIRROR_REPO"

    # Already have it? A job on a branch nobody has pushed to since the last fetch is the common
    # case, and re-fetching 1.3 GB of nothing on every job would be the whole cost of this feature.
    if [ -n "$_want" ] && git -C "$_repo" cat-file -e "${_want}^{commit}" 2>/dev/null; then
        echo "mirror already has ${_want%${_want#???????}}"
        return 0
    fi

    # golden first, because it is the one holding credentials for GitHub.
    if [ -n "${GOLDEN_MNT:-}" ] && [ -d "$GOLDEN_MNT/.git" ]; then
        timeout "$FFGHR_MIRROR_FETCH_TIMEOUT" \
            git -C "$GOLDEN_MNT" fetch --quiet --prune origin 2>/dev/null \
            || echo "WARNING: golden fetch failed; the mirror may be behind"
    fi
    timeout "$FFGHR_MIRROR_FETCH_TIMEOUT" \
        git -C "$_repo" fetch --quiet --prune origin '+refs/heads/*:refs/heads/*' 2>/dev/null \
        || { echo "mirror fetch failed"; return 1; }

    # LFS TOO, and this is what makes github.com removable rather than merely unused.
    #
    # The mirror serves golden's LFS object store. Golden materialises LFS for whatever it has
    # checked out, so master is covered -- but a feature branch that adds an image has objects
    # golden has never fetched, and without this the first commit touching a PNG would fail a job
    # with no way to recover. `git lfs fetch` for a commit that adds nothing is a cheap no-op.
    if [ -n "$_want" ] && [ -n "${GOLDEN_MNT:-}" ] && [ -d "$GOLDEN_MNT/.git" ]; then
        timeout "$FFGHR_MIRROR_FETCH_TIMEOUT" \
            git -C "$GOLDEN_MNT" lfs fetch origin "$_want" >/dev/null 2>&1 \
            || echo "WARNING: LFS fetch for ${_want%${_want#???????}} failed; new binaries may be missing"
    fi

    if [ -n "$_want" ] && ! git -C "$_repo" cat-file -e "${_want}^{commit}" 2>/dev/null; then
        echo "fetched, but ${_want%${_want#???????}} is still not in the mirror"
        return 1
    fi
    echo "mirror updated$([ -n "$_want" ] && printf ' to include %s' "${_want%${_want#???????}}")"
    return 0
}

# ffghr_mirror_serve_request STAGE -- answer a job's fetch.request, once.
#
# The job writes one line: the 40-hex commit it needs. Anything else is refused rather than passed
# to git, because this string reaches a command line on the host.
ffghr_mirror_serve_request() {
    _stage=${1:-}
    [ -n "$_stage" ] && [ -f "$_stage/fetch.request" ] || return 1
    [ -f "$_stage/fetch.done" ] && return 1

    _want=$(head -1 "$_stage/fetch.request" 2>/dev/null | tr -d ' \r\n')
    case "$_want" in
        [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*)
            [ "${#_want}" = 40 ] || { echo "fetch.request is not a 40-hex commit; ignoring"; _want="" ;} ;;
        "") ;;
        *) echo "fetch.request is not a commit id; ignoring"; _want="" ;;
    esac

    if ffghr_mirror_fetch "$_want"; then
        printf 'ok\n' > "$_stage/fetch.done" 2>/dev/null || true
    else
        # Tell the job so it stops waiting and goes to GitHub, rather than burning its wait budget.
        printf 'failed\n' > "$_stage/fetch.done" 2>/dev/null || true
    fi
    return 0
}
