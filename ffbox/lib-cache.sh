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
