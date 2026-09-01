#!/usr/bin/env bash
#
# ffbox's default container task: hand the mounted prompt to Claude, one-shot, in the workspace.
# Invoked by entrypoint.sh — not meant to be run directly.
#
# No `set -e`. Every failure path here needs the licensing trap in unity-license.sh to fire so the
# Unity seat comes back; errors are checked explicitly instead.
set -uo pipefail

: "${HOME:=/home/ffbox}"
export HOME
export PATH="/usr/local/bin:${PATH}"

WORKSPACE=${FFBOX_WORKSPACE:-/workspace}
FFBOX_OUT=${FFBOX_OUT:-/ffbox/out}
PROMPT_FILE=${FFBOX_PROMPT_FILE:-/ffbox/prompt.txt}
export FFBOX_OUT

log() { printf '[ffbox] %s\n' "$*"; }

# Installs the return-license trap and defines ensure_unity_license.
. /ffbox/unity-license.sh

# HARVEST IN HERE, BECAUSE THE WORKSPACE IS NOT ON A HOST PATH ANY MORE. It is a tmpfs the host
# cannot see, so the run has to turn its own work into files under /ffbox/out before this container
# exits -- and /ffbox/out is the only thing that outlives it.
#
# REPLACING THE LICENCE TRAP WOULD LEAK A UNITY SEAT ON EVERY RUN. unity-license.sh set
# `trap return_license EXIT INT TERM` above, and a bare `trap harvest EXIT` here would silently
# take its place. This calls both, harvest first: a docker stop gives 120 seconds, the harvest is
# a bundle of a small range and takes a moment, and the licence return is an editor launch that
# wants what is left.
#
# THE AGENT HAS TO BE STOPPED BEFORE ITS TREE IS BUNDLED, and it is not stopped by the signal
# that got us here: `docker stop` sends SIGTERM to PID 1 and to nothing else. See the long note
# in discord-task.sh; the short version is that bash defers a trap while waiting on a foreground
# child, so this handler only runs at all because the agent below is backgrounded.
FFBOX_AGENT_PID=

_ffbox_stop_agent() {
    [ -n "$FFBOX_AGENT_PID" ] || return 0
    kill -0 "$FFBOX_AGENT_PID" 2>/dev/null || return 0
    log "stopping the agent (pid $FFBOX_AGENT_PID)"
    kill -TERM "$FFBOX_AGENT_PID" 2>/dev/null
    _w=0
    while [ "$_w" -lt 10 ] && kill -0 "$FFBOX_AGENT_PID" 2>/dev/null; do
        sleep 1
        _w=$((_w + 1))
    done
    kill -KILL "$FFBOX_AGENT_PID" 2>/dev/null
    FFBOX_AGENT_PID=
}

_ffbox_finish() {
    _rc=$?
    _ffbox_stop_agent
    if [ -x /ffbox/harvest-workspace.sh ] && [ -n "${FFBOX_CACHE_ENTRY:-}" ]; then
        /ffbox/harvest-workspace.sh || log "WARNING: harvest failed"
    fi
    return_license
    return $_rc
}
trap _ffbox_finish EXIT INT TERM

ensure_unity_license

if [ ! -r "$PROMPT_FILE" ]; then
    log "ERROR: no prompt mounted at $PROMPT_FILE"
    exit 78
fi

cd "$WORKSPACE" || exit 1

log "workspace: $WORKSPACE ($(git rev-parse --short HEAD 2>/dev/null || echo 'not a git repo'))"
log "running one-shot prompt"

# --dangerously-skip-permissions is appropriate precisely because this container is disposable:
# the workspace is a throwaway ZFS clone, and the whole point is unattended execution.
# Backgrounded so the finish handler above can reach it; see the note there. The output still
# goes to the terminal AND to claude.log, which is what `ffbox --direct` is watched through, but
# through a process substitution rather than a pipeline: `cmd | tee` makes $! the tee, and
# killing tee leaves the agent running.
claude -p "$(cat "$PROMPT_FILE")" \
    --dangerously-skip-permissions \
    --output-format "${FFBOX_OUTPUT_FORMAT:-text}" \
    > >(tee "$FFBOX_OUT/claude.log") 2>&1 &
FFBOX_AGENT_PID=$!
wait "$FFBOX_AGENT_PID"
rc=$?
FFBOX_AGENT_PID=

log "claude exited ${rc}"
exit "$rc"
