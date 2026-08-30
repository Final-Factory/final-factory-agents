# lib-cache.sh — what the host needs to hand a cached workspace to a container. SOURCED.
#
# The agent path takes its workspace from the same ffcache entries CI writes, instead of from a
# ZFS clone. The host does every network operation, because the container reaches neither GitHub
# nor a credential, and passes the result in as data.
# shellcheck shell=sh

FFCACHE_DIR=${FFCACHE_DIR:-/opt/ffcache}
FFCACHE_ENTRIES="$FFCACHE_DIR/entries"

# ffcache_entry_for <branch> <scope> -> path, or empty
ffcache_entry_for() {
    _b=$(printf '%s' "$1" | sed 's/[^a-zA-Z0-9._-]/-/g')
    _e="$FFCACHE_ENTRIES/$_b@$2.tar"
    [ -r "$_e" ] && printf '%s' "$_e"
}

# ffcache_entry_sha <entry> -> the commit the archive is at, read FROM THE ARCHIVE.
#
# Authoritative rather than a label: it is what the tar actually contains, not a claim written
# beside it that could drift. Costs about five seconds — .git/HEAD sits late in the member order
# but tar stops once it has what it was asked for, measured at 4s against a 22 GB entry.
#
# HEAD may be a symref or already a sha, and the ref may be loose or packed. All three shapes
# appear in real archives, so all three are handled.
ffcache_entry_sha() {
    _entry=$1
    _head=$(tar -xOf "$_entry" ./.git/HEAD 2>/dev/null | tr -d ' \r\n')
    [ -n "$_head" ] || return 1
    case "$_head" in
        ref:*) _ref=${_head#ref:} ;;
        *)     printf '%s' "$_head"; return 0 ;;    # detached: HEAD is the sha
    esac
    _sha=$(tar -xOf "$_entry" "./.git/$_ref" 2>/dev/null | tr -d ' \r\n')
    if [ -z "$_sha" ]; then
        _sha=$(tar -xOf "$_entry" ./.git/packed-refs 2>/dev/null \
               | awk -v r="$_ref" '$2 == r { print $1; exit }' | tr -d ' \r\n')
    fi
    [ -n "$_sha" ] || return 1
    printf '%s' "$_sha"
}

# ffcache_make_delta <golden> <from sha> <to rev> <out bundle> -> 0 made, 1 not needed, 2 cannot
#
# `git bundle create A..B` refuses when A is unknown to the repository, which happens whenever CI
# built the entry from something golden has never fetched. That is not an error: the caller falls
# back to the entry as it stands, which is correct and merely older.
ffcache_make_delta() {
    _golden=$1; _from=$2; _to=$3; _out=$4
    _tosha=$(git -C "$_golden" rev-parse --verify --quiet "${_to}^{commit}" 2>/dev/null) || return 2
    [ "$_from" != "$_tosha" ] || return 1
    git -C "$_golden" cat-file -e "${_from}^{commit}" 2>/dev/null || return 2
    git -C "$_golden" merge-base --is-ancestor "$_from" "$_tosha" 2>/dev/null || return 2
    # BUNDLE THE REF NAME, NOT THE RESOLVED SHA. `git bundle create out <sha>..<sha>` has no ref
    # to record and git answers "Refusing to create empty bundle" — the commits are in the range
    # but nothing names the tip, so there is nothing to fetch on the other side. Naming the ref
    # puts refs/heads/<name> in the bundle, which is what the container fetches.
    git -C "$_golden" bundle create "$_out" "${_from}..${_to}" >/dev/null 2>&1 || return 2
    printf '%s' "$_tosha"
}

# ffbox_validate_harvest <out dir> -> 0 publishable, 1 not. Writes the reason to harvest_error.txt.
#
# The container produced the bundle and ran the same checks on the way. This runs them AGAIN, on
# the host, from the bundle alone — because a run that skipped them would otherwise be taken at
# its word, and because the container's own changed_files.txt is a claim rather than evidence.
#
# Everything here reads the BUNDLE, never the workspace: the workspace is a tmpfs that died with
# the container, which is the property that makes this safe. A bundle is inert — git verifies it,
# and it carries no hooks and no config.
ffbox_validate_harvest() {
    _out=$1
    _bundle="$_out/work.bundle"
    _fail() { printf '%s\n' "$1" > "$_out/harvest_error.txt"
              rm -f "$_out/work.bundle" "$_out/branch.txt"
              echo "[ffbox] REFUSED: $1" >&2; return 1; }

    [ -s "$_bundle" ] || return 0          # nothing to publish is not a failure
    _branch=$(cat "$_out/branch.txt" 2>/dev/null || echo "")
    _base=$(cat "$_out/publish_base_sha.txt" 2>/dev/null || echo "")
    [ -n "$_branch" ] || { _fail "a bundle with no branch name"; return 1; }
    [ -n "$_base" ]   || { _fail "a bundle with no base commit"; return 1; }

    _bytes=$(wc -c < "$_bundle" 2>/dev/null || echo 0)
    [ "$_bytes" -le "${MAX_BUNDLE_BYTES:-268435456}" ] \
        || { _fail "the work bundle is ${_bytes} bytes, over the ceiling of ${MAX_BUNDLE_BYTES}"; return 1; }

    # A scratch repo the container never saw. Cloning golden --shared would be faster and would
    # also hand a bundle the ability to name golden's objects; this stays a bare repo with only
    # what the bundle carries plus what we fetch from golden by sha.
    _tmp=$(mktemp -d)
    # shellcheck disable=SC2064
    trap "rm -rf '$_tmp'" RETURN
    git init --quiet --bare "$_tmp" || { _fail "could not create a scratch repo"; return 1; }

    # golden belongs to the container account since the daemon move and this runs as the owner, so
    # git refuses it as "dubious ownership" without an exemption. TWO paths are needed, and the
    # second is the one that bites: fetching FROM a path makes git resolve the remote to its
    # git-dir and check ownership on THAT, so /opt/FinalFactory is not /opt/FinalFactory/.git.
    #
    # The exemption has to live in GLOBAL config. `-c safe.directory=` and GIT_CONFIG_* both fail
    # here, by design: git honours safe.directory only in PROTECTED configuration, precisely so
    # that something controlling the environment cannot exempt itself. Measured both ways before
    # believing it. 02-zfsSetup.sh records the two entries a machine needs.
    _g=${FFBOX_GOLDEN_MNT:-/opt/FinalFactory}
    if ! git -C "$_tmp" fetch --quiet "$_g" "+refs/heads/*:refs/remotes/golden/*" \
         "+refs/remotes/origin/*:refs/remotes/gorigin/*" 2>/dev/null; then
        _fail "could not read golden to check the bundle against (is safe.directory set for $_g and $_g/.git?)"
        return 1
    fi

    git -C "$_tmp" bundle verify "$_bundle" >/dev/null 2>&1 \
        || { _fail "the work bundle does not verify against what this host has"; return 1; }
    git -C "$_tmp" fetch --quiet "$_bundle" "+refs/heads/*:refs/bundle/*" >/dev/null 2>&1 \
        || { _fail "the work bundle could not be fetched from"; return 1; }

    _tip=$(git -C "$_tmp" rev-parse --verify --quiet "refs/bundle/$_branch" 2>/dev/null) \
        || { _fail "the bundle does not contain the branch it claims ($_branch)"; return 1; }
    git -C "$_tmp" cat-file -e "${_base}^{commit}" 2>/dev/null \
        || { _fail "the bundle's base ${_base} is not a commit this host knows"; return 1; }
    git -C "$_tmp" merge-base --is-ancestor "$_base" "$_tip" 2>/dev/null \
        || { _fail "the bundle's branch does not descend from the base it claims"; return 1; }

    # Re-derived, not read from the container's file.
    git -C "$_tmp" diff --name-only "${_base}..${_tip}" > "$_out/changed_files.txt" 2>/dev/null || true
    _n=$(wc -l < "$_out/changed_files.txt" 2>/dev/null || echo 0)
    [ "$_n" -le "${MAX_CHANGED_FILES:-2000}" ] \
        || { _fail "$_n changed files, over the ceiling of ${MAX_CHANGED_FILES}"; return 1; }

    _forbidden=$(grep -E "${FORBIDDEN_PATHS_RE:-^\.github/}" "$_out/changed_files.txt" | tr '\n' ' ' || true)
    [ -z "$_forbidden" ] \
        || { _fail "the range changes CI configuration, which this pipeline never publishes: $_forbidden"; return 1; }

    _foreign=$(git -C "$_tmp" log --format='%ae%n%ce' "${_base}..${_tip}" 2>/dev/null \
               | sort -u | grep -Fxv "${FFBOX_GIT_EMAIL:-ffbox@final-factory.invalid}" || true)
    [ -z "$_foreign" ] \
        || { _fail "commits claim an identity this run does not own: $(printf '%s' "$_foreign" | tr '\n' ' ')"; return 1; }

    echo "[ffbox] validated $_n changed file(s) in $(git -C "$_tmp" rev-list --count "${_base}..${_tip}") commit(s) on $_branch"
    return 0
}
