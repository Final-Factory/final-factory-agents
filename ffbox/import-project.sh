#!/usr/bin/env bash
#
# ffbox container task: open the project once in batch mode so Unity builds its Library/ import
# cache, then quit. Invoked by entrypoint.sh when FFBOX_ENTRY points here — see warmLibrary.sh.
#
# This is the slow one (a cold import on Final Factory is plausibly 30-60 minutes). It is worth
# paying exactly once, in golden: every per-run ZFS clone then inherits the finished Library/ for
# free, so ffbox runs start warm.
set -uo pipefail

: "${HOME:=/home/ffbox}"
export HOME
export PATH="/usr/local/bin:${PATH}"

WORKSPACE=${FFBOX_WORKSPACE:-/workspace}
FFBOX_OUT=${FFBOX_OUT:-/ffbox/out}
export FFBOX_OUT

log() { printf '[ffbox] %s\n' "$*"; }

. /ffbox/unity-license.sh

# An import with no license produces a broken half-populated Library/, which is worse than none:
# it looks warm and then fails at compile time. Never let this task run unlicensed.
if [ "${FFBOX_UNITY:-1}" != 1 ]; then
    log "ERROR: the Library import requires a Unity license; --no-unity is not valid here"
    exit 78
fi
ensure_unity_license

cd "$WORKSPACE" || exit 1

log "importing $WORKSPACE — expect this to take a long time on a cold project"
before=$(du -sh Library 2>/dev/null | cut -f1 || true)
log "Library before: ${before:-absent}"

# The image's unity-editor wrapper already supplies -batchmode and wraps the editor in xvfb-run,
# so a plain -quit run is a full asset import. No -nographics: shader importers want a display,
# and CI does not pass it either.
unity-editor \
    -quit \
    -projectPath "$WORKSPACE" \
    -logFile /dev/stdout 2>&1 | tee "$FFBOX_OUT/import.log"
rc=${PIPESTATUS[0]}

after=$(du -sh Library 2>/dev/null | cut -f1 || true)
log "Library after: ${after:-absent}"

if [ "$rc" -ne 0 ]; then
    log "ERROR: Unity exited ${rc}; see ${FFBOX_OUT}/import.log"
elif [ -z "$after" ]; then
    log "ERROR: Unity exited 0 but produced no Library/ — treating as a failure"
    rc=1
else
    log "import complete"
fi

exit "$rc"
