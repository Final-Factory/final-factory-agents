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
# STRAIGHT TO GITHUB, NOT VIA GOLDEN. The first version of this fetched from golden, which quietly
# made golden load-bearing again -- the opposite of retiring it. The mirror IS the git source now:
# it holds every branch and its own LFS objects, authenticates with the host's GitHub App token,
# and nothing here reads /opt/FinalFactory. That is what lets the ZFS snapshot and golden go.
#
# A job restores its workspace from an ffcache tarball and fetches the delta from here. With no
# cache entry it pays one slow full transfer from this mirror instead, which is still local.

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

    # --- git objects: only fetch when the commit is actually missing ---------------------------
    #
    # A job on a branch nobody has pushed to since the last fetch is the common case, and pulling
    # 1.3 GB of nothing every time would be the whole cost of this feature.
    if [ -n "$_want" ] && git -C "$_repo" cat-file -e "${_want}^{commit}" 2>/dev/null; then
        echo "mirror already has ${_want%${_want#???????}}"
    else
        # AUTHENTICATED BY THE HOST'S OWN STORED CREDENTIAL, which is what golden already uses:
        # credential.helper store against ~/.git-credentials, owned by the account the supervisor
        # runs as. The mirror carries that remote from provision time, so nothing is passed on a
        # command line here.
        #
        # NOT the GitHub App token, and I checked rather than assumed: that installation is
        # org-scoped for runner administration and /installation/repositories reports 0
        # repositories, so a fetch with it answers "Repository not found". Granting the App
        # Contents:Read would be a tightening -- short-lived and read-only instead of a long-lived
        # host credential -- and is the obvious next step, but only a repo admin can make it.
        #
        # EVERY BRANCH. Worth stating because the version that fetched from golden got it wrong:
        # golden is a working checkout with exactly ONE local branch, master, and 157 others under
        # refs/remotes/origin -- so refs/heads/* mirrored master alone and every job on develop or
        # a feature branch quietly fell back to github.com. It showed up in the git daemon log as
        # "not our ref e03e807...", which was develop HEAD, while the jobs still passed.
        timeout "$FFGHR_MIRROR_FETCH_TIMEOUT" \
            git -C "$_repo" fetch --quiet --prune origin '+refs/heads/*:refs/heads/*' 2>/dev/null \
            || { echo "mirror fetch failed"; return 1; }

        if [ -n "$_want" ] && ! git -C "$_repo" cat-file -e "${_want}^{commit}" 2>/dev/null; then
            echo "fetched, but ${_want%${_want#???????}} is still not in the mirror"
            return 1
        fi
        echo "mirror updated$([ -n "$_want" ] && printf ' to include %s' "${_want%${_want#???????}}")"
    fi

    # --- LFS objects: ALWAYS, and the ordering here is the whole point ---------------------------
    #
    # This used to sit after the early return above, which made it nearly dead code. The git fetch
    # pulls EVERY branch, so it drags in far more commits than the one asked for; the next job to
    # name any of those found its commit already present, returned at the top, and never fetched
    # LFS at all. The store only ever updated for the rare commit that happened to trigger a ref
    # miss -- so the first PNG on a branch would have failed a job with no fallback, exactly the
    # case this server was built for.
    #
    # Measured at about 4.6s against a 3043-object store when nothing is missing, which is why it
    # can run unconditionally: the job asks before its restore step, which takes some forty
    # seconds, so this finishes inside slack that already exists.
    if [ -n "$_want" ]; then
        timeout "$FFGHR_MIRROR_FETCH_TIMEOUT" \
            git -C "$_repo" lfs fetch origin "$_want" >/dev/null 2>&1 \
            || echo "WARNING: LFS fetch for ${_want%${_want#???????}} failed; new binaries may be missing"
    fi
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
