#!/bin/sh
# restore-workspace.sh — fill an empty tmpfs workspace from the host cache, inside the container.
#
# Runs as root, before the entrypoint drops privilege, because it creates the tree the run then
# works in. The agent path used to get its workspace as a ZFS clone bind-mounted from the host;
# this replaces that, so nothing host-visible is writable by the run and both modes get the same
# shape of workspace.
#
# THREE INPUTS, ALL FROM THE HOST, NONE OF THEM THE NETWORK:
#
#   FFBOX_CACHE_ENTRY   a tar under /ffcache (read-only), the whole workspace as CI left it
#   FFBOX_BASE_BUNDLE   optional git bundle carrying entry..target, written by the host
#   FFBOX_TARGET_SHA    optional commit to end up at
#
# THE CONTAINER NEVER FETCHES. ffbox-net reaches Anthropic and Unity and not GitHub, and the
# container holds no git credential, both deliberately. So the host does every network operation
# and hands the result in as data: a tar it already had, and a bundle of the few commits since.
# A bundle is inert — git verifies it, and it carries no hooks and no config.
#
# NEVER SILENTLY WRONG. A missing cache, a missing entry, a bundle that will not apply: each is
# reported and each leaves the workspace in a state the caller can see. What this must never do is
# leave a half-restored tree that looks complete.
set -eu

WORKSPACE=${FFBOX_WORKSPACE:-/opt/actions-runner/_work/FinalFactory/FinalFactory}
ENTRY=${FFBOX_CACHE_ENTRY:-}
BUNDLE=${FFBOX_BASE_BUNDLE:-}
TARGET=${FFBOX_TARGET_SHA:-}
# A READ-ONLY BIND MOUNT OF THE BARE MIRROR, which turned out simpler than the bundle this was
# written for. A bundle needs the host to know what commit the cache entry is at, which means
# opening the tar before deciding what to put in the bundle; a mirror mount needs none of that --
# git works out the delta itself. It is :ro, so a run cannot write into the mirror every later run
# and every CI job then reads.
MIRROR=${FFBOX_MIRROR:-}
REF=${FFBOX_REF:-}

log() { printf '[restore] %s\n' "$*"; }
die() { printf '[restore] ERROR: %s\n' "$*" >&2; exit 1; }

# --resync: EVERYTHING BELOW THE TAR, against a workspace that already holds one.
#
# A pooled container filled itself from the cache entry before any request existed, so when one
# arrives the tar is already extracted and only the last part of this script applies: fetch the
# mirror again, land on the commit the turn asked for, create its branch, record base_sha. Those
# steps live here rather than in pool-task.sh because getting them subtly different from what a
# cold run does is exactly how a pooled run would start producing different answers.
RESYNC=0
if [ "${1:-}" = "--resync" ]; then
    RESYNC=1
    shift
fi

[ -d "$WORKSPACE" ] || die "no workspace at $WORKSPACE"

if [ "$RESYNC" = 1 ]; then
    [ -n "$(ls -A "$WORKSPACE" 2>/dev/null)" ] || die "--resync wants a workspace that is already filled"
    [ -d "$WORKSPACE/.git" ] || die "--resync wants a git workspace, and $WORKSPACE is not one"
else
    # An empty workspace is the contract. Restoring over an existing tree would merge two states
    # and the result would be neither.
    if [ -n "$(ls -A "$WORKSPACE" 2>/dev/null)" ]; then
        die "$WORKSPACE is not empty; refusing to restore over it"
    fi

    if [ -z "$ENTRY" ]; then
        log "no cache entry given — leaving the workspace empty"
        exit 0
    fi
    [ -r "$ENTRY" ] || die "cannot read $ENTRY"
fi

if [ "$RESYNC" = 0 ]; then
    log "restoring $(basename "$ENTRY") ($(du -h "$ENTRY" 2>/dev/null | cut -f1))"
    _t0=$(date +%s)
    # --no-same-owner: the archive records a CI container's uids, which mean nothing here, and
    # letting tar apply them also rewrites the workspace directory's own ownership.
    tar -xf "$ENTRY" -C "$WORKSPACE" --no-same-owner || die "the archive did not extract"
    log "extracted in $(( $(date +%s) - _t0 ))s"

    [ -d "$WORKSPACE/.git" ] || die "the archive contained no .git"
fi

# The archive was written by a CI job, so its .git is a tree a job controlled. Nothing on the host
# will read it — the host never sees this workspace — but the AGENT is about to run git in it, and
# a hook the archive carried would run as the agent. ffcache excludes .git/hooks at save time for
# this reason; belt and braces here, because an entry could predate that.
rm -rf "$WORKSPACE/.git/hooks"
mkdir -p "$WORKSPACE/.git/hooks"

# git refuses a tree it does not own, and the workspace is root-owned while the run is not.
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=safe.directory
export GIT_CONFIG_VALUE_0="$WORKSPACE"

_have=$(git -C "$WORKSPACE" rev-parse --verify --quiet HEAD 2>/dev/null || echo "")
log "archive is at ${_have:-<no HEAD>}"

if [ -n "$BUNDLE" ] && [ -r "$BUNDLE" ]; then
    log "applying the host's delta bundle ($(du -h "$BUNDLE" | cut -f1))"
    git -C "$WORKSPACE" bundle verify "$BUNDLE" >/dev/null 2>&1 \
        || die "the delta bundle did not verify"
    # A bundle is fetched, not merged: this only adds objects and updates remote refs.
    git -C "$WORKSPACE" fetch --quiet "$BUNDLE" '+refs/heads/*:refs/remotes/bundle/*' \
        || die "could not fetch from the delta bundle"
fi

if [ -n "$MIRROR" ] && [ -d "$MIRROR" ]; then
    log "fetching the delta from the local mirror"
    git -C "$WORKSPACE" fetch --quiet --prune "$MIRROR" '+refs/heads/*:refs/remotes/origin/*' \
        || die "could not fetch from the mirror at $MIRROR"
fi

# --- Git LFS: the objects come from the mirror, and never from GitHub --------------------------
#
# THE SMUDGE FILTER IS A NETWORK CALL, AND THIS CONTAINER HAS NO CREDENTIAL. `git reset --hard`
# runs git-lfs over every LFS-tracked file it rewrites, and git-lfs answers what it cannot find in
# .git/lfs/objects by asking the ORIGIN REMOTE -- which the cache entry carries as
# https://github.com/Final-Factory/FinalFactory, because CI cloned it that way.
#
# So a workspace restored from MASTER's entry and reset onto a develop-based branch went looking
# for the objects develop added. On the dev lane that failed in about a second ("could not read
# Username for 'https://github.com'"), the reset failed, this script died, and the container was
# gone roughly two minutes in having written NOTHING -- no base_sha.txt, no claude.log, not even
# the .container-rc its own trap writes. Three runs went that way on 2026-09-11, each reported
# into Discord as "the run failed / no branch: the run changed no files", which is what a run that
# never started looks like from the outside. Measured on the FENCED lane the same smudge does not
# fail at all: it hangs until something kills it, which is worse.
#
# THE OBJECTS ARE ALREADY HERE. The mirror is mounted read-only at /ffmirror and CI's own fetches
# leave its LFS store populated -- 3044 objects, 4.3 GB when this was written, including every
# object that failing reset wanted. So seed the ones this target needs into the workspace's store
# first, and the smudge that follows is a local read of a file we just put there.
#
# WHAT CANNOT BE SEEDED IS NOT FATAL. An object the mirror does not carry would send git-lfs back
# to the network, so that reset runs with GIT_LFS_SKIP_SMUDGE=1 instead and those files land as
# their pointer text. Pointer text is worse than the real thing and far better than a container
# that dies before the agent starts -- and it is recorded, in the log and in lfs_pointers.txt
# under the run's output, rather than being silently wrong.
#
# ONE PASS OVER THE TARGET'S LFS FILES, in the shell, with no process per object: `git lfs
# ls-files --long` names every oid at that ref and the rest is file tests against two directories.
LFS_UNSEEDABLE=0

lfs_seed_from_mirror() {
    _ref=$1
    LFS_UNSEEDABLE=0
    [ -n "$MIRROR" ] && [ -d "$MIRROR/lfs/objects" ] || return 0
    git -C "$WORKSPACE" lfs version >/dev/null 2>&1 || return 0
    _list=$(mktemp 2>/dev/null) || return 0
    if ! git -C "$WORKSPACE" lfs ls-files --long "$_ref" > "$_list" 2>/dev/null; then
        rm -f "$_list"
        return 0
    fi
    _seeded=0
    _absent=0
    # `read` takes the path as the remainder, so a name with spaces in it cannot split the line.
    while read -r _oid _mark _path; do
        case "$_oid" in
            '' | *[!0-9a-f]*) continue ;;
        esac
        _rest=${_oid#??}
        _d1=${_oid%"$_rest"}
        _d2=${_rest%"${_rest#??}"}
        _dst="$WORKSPACE/.git/lfs/objects/$_d1/$_d2/$_oid"
        if [ -f "$_dst" ]; then
            continue
        fi
        _src="$MIRROR/lfs/objects/$_d1/$_d2/$_oid"
        if [ ! -f "$_src" ]; then
            _absent=$((_absent + 1))
            continue
        fi
        # Copied to a scratch name and renamed, so a copy interrupted half way cannot leave
        # something that LOOKS like an object: git-lfs verifies size and hash, but only after it
        # has decided the file is there.
        mkdir -p "$WORKSPACE/.git/lfs/objects/$_d1/$_d2"
        if cp "$_src" "$_dst.part" 2>/dev/null && mv "$_dst.part" "$_dst" 2>/dev/null; then
            _seeded=$((_seeded + 1))
        else
            rm -f "$_dst.part"
            _absent=$((_absent + 1))
        fi
    done < "$_list"
    rm -f "$_list"
    LFS_UNSEEDABLE=$_absent
    [ "$_seeded" -eq 0 ] || log "seeded $_seeded LFS object(s) from the mirror"
    [ "$_absent" -eq 0 ] \
        || log "WARNING: $_absent LFS object(s) are in neither the workspace nor the mirror"
    unset _ref _list _seeded _absent _oid _mark _path _rest _d1 _d2 _dst _src
    return 0
}

# Resolve what to land on: an explicit commit, else a ref via the mirror's refs.
_target=$TARGET
if [ -z "$_target" ] && [ -n "$REF" ]; then
    for _c in "origin/$REF" "$REF"; do
        if git -C "$WORKSPACE" rev-parse --verify --quiet "${_c}^{commit}" >/dev/null 2>&1; then
            _target=$_c; break
        fi
    done
    [ -n "$_target" ] || die "ref '$REF' resolves to nothing after the restore"
fi

if [ -n "$_target" ]; then
    git -C "$WORKSPACE" rev-parse --verify --quiet "${_target}^{commit}" >/dev/null 2>&1 \
        || die "target $_target is not in the workspace after restore (mirror missing or wrong)"
    lfs_seed_from_mirror "$_target"
    if [ "$LFS_UNSEEDABLE" -gt 0 ]; then
        log "resetting with the LFS smudge off; $LFS_UNSEEDABLE file(s) will be pointer text"
        GIT_LFS_SKIP_SMUDGE=1 git -C "$WORKSPACE" reset --hard --quiet "$_target" \
            || die "could not reset to $_target"
        printf '%s\n' "$LFS_UNSEEDABLE" \
            > "${FFBOX_OUT:-/ffbox/out}/lfs_pointers.txt" 2>/dev/null || true
    else
        git -C "$WORKSPACE" reset --hard --quiet "$_target" || die "could not reset to $_target"
    fi
    log "workspace at $(git -C "$WORKSPACE" rev-parse --short HEAD)"
fi

# THE ENTRY'S CONFIG IS A CI JOB'S CONFIG. Hooks are already gone above; these keys name commands
# that ordinary git operations fire, so they are a persistence channel in the same way.
for _k in core.fsmonitor core.pager core.hooksPath diff.external \
          filter.lfs.process filter.lfs.smudge filter.lfs.clean; do
    git -C "$WORKSPACE" config --local --unset-all "$_k" 2>/dev/null || true
done

# AND THE RUN INHERITS THE SAME DECISION THE RESET MADE. The keys just unset are the ENTRY's; the
# image sets filter.lfs.* in SYSTEM config, so unsetting a local key does not stop the smudge --
# it only removes whatever a CI job left. When an object is missing from both the workspace and
# the mirror, every later `git checkout` in this run would go to GitHub for it and hang on the
# fenced lane, long after this script is done and with nothing to say why. `--skip` is what
# `git lfs install --skip-smudge` writes: the clean side still works, so the agent can commit,
# and the smudge writes pointer text instead of asking anybody.
if [ "$LFS_UNSEEDABLE" -gt 0 ]; then
    git -C "$WORKSPACE" config --local filter.lfs.smudge "git-lfs smudge --skip -- %f" \
        2>/dev/null || true
    git -C "$WORKSPACE" config --local filter.lfs.process "git-lfs filter-process --skip" \
        2>/dev/null || true
fi

# tar gives every restored file a new inode and ctime, so git's index cannot trust any of it and
# re-hashes the whole worktree on the first command that touches it -- measured at two minutes in
# CI. core.checkStat=minimal compares mtime, size and mode instead, which is exactly the difference
# a tarball introduces.
git -C "$WORKSPACE" config --local core.checkStat minimal 2>/dev/null || true

# THE BRANCH AND THE IDENTITY, which the host used to set before handing over the workspace. They
# move in here with everything else: there is no host-visible tree left to set them on.
#
# The identity is not decoration -- harvest-workspace.sh checks every commit in the range against
# it, so a run whose commits carry someone else's name is caught rather than published.
git -C "$WORKSPACE" config --local user.name  "${FFBOX_GIT_NAME:-ffbox}" 2>/dev/null || true
git -C "$WORKSPACE" config --local user.email "${FFBOX_GIT_EMAIL:-ffbox@final-factory.invalid}" 2>/dev/null || true

if [ -n "${FFBOX_BRANCH:-}" ]; then
    git -C "$WORKSPACE" check-ref-format --branch "$FFBOX_BRANCH" >/dev/null 2>&1 \
        || die "refusing to create a branch named '$FFBOX_BRANCH'"
    git -C "$WORKSPACE" checkout -q -B "$FFBOX_BRANCH" \
        || die "could not create branch $FFBOX_BRANCH"
    log "on branch $FFBOX_BRANCH"
fi

# What the run started from, recorded before the agent can move HEAD. harvest-workspace.sh needs it
# to know where the published range begins, and taking it here rather than at the end is the
# difference between a known-good value and one the run chose.
git -C "$WORKSPACE" rev-parse HEAD > "${FFBOX_OUT:-/ffbox/out}/base_sha.txt" 2>/dev/null || true

# Whoever runs next is not root; the tmpfs is 1777 but the extracted tree is not.
chmod -R a+rwX "$WORKSPACE/.git" 2>/dev/null || true
log "done"
