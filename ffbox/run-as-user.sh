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
claude -p "$(cat "$PROMPT_FILE")" \
    --dangerously-skip-permissions \
    --output-format "${FFBOX_OUTPUT_FORMAT:-text}" 2>&1 | tee "$FFBOX_OUT/claude.log"
rc=${PIPESTATUS[0]}

log "claude exited ${rc}"
exit "$rc"
