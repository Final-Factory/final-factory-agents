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

WORKSPACE=${FFBOX_WORKSPACE:-/workspace}
ENTRY=${FFBOX_CACHE_ENTRY:-}
BUNDLE=${FFBOX_BASE_BUNDLE:-}
TARGET=${FFBOX_TARGET_SHA:-}

log() { printf '[restore] %s\n' "$*"; }
die() { printf '[restore] ERROR: %s\n' "$*" >&2; exit 1; }

[ -d "$WORKSPACE" ] || die "no workspace at $WORKSPACE"

# An empty workspace is the contract. Restoring over an existing tree would merge two states and
# the result would be neither.
if [ -n "$(ls -A "$WORKSPACE" 2>/dev/null)" ]; then
    die "$WORKSPACE is not empty; refusing to restore over it"
fi

if [ -z "$ENTRY" ]; then
    log "no cache entry given — leaving the workspace empty"
    exit 0
fi
[ -r "$ENTRY" ] || die "cannot read $ENTRY"

log "restoring $(basename "$ENTRY") ($(du -h "$ENTRY" 2>/dev/null | cut -f1))"
_t0=$(date +%s)
tar -xf "$ENTRY" -C "$WORKSPACE" || die "the archive did not extract"
log "extracted in $(( $(date +%s) - _t0 ))s"

[ -d "$WORKSPACE/.git" ] || die "the archive contained no .git"

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

if [ -n "$TARGET" ]; then
    git -C "$WORKSPACE" rev-parse --verify --quiet "${TARGET}^{commit}" >/dev/null 2>&1 \
        || die "target $TARGET is not in the workspace after restore (bundle missing or wrong)"
    git -C "$WORKSPACE" reset --hard --quiet "$TARGET" || die "could not reset to $TARGET"
    log "workspace at $(git -C "$WORKSPACE" rev-parse --short HEAD)"
fi

# Whoever runs next is not root; the tmpfs is 1777 but the extracted tree is not.
chmod -R a+rwX "$WORKSPACE/.git" 2>/dev/null || true
log "done"
