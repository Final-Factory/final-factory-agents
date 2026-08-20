#!/usr/bin/env bash
#
# Shared Unity licensing for ffbox container tasks. SOURCED by the task scripts
# (run-as-user.sh, import-project.sh), never executed directly.
#
# Sourcing this installs the return-license trap, so every task that touches Unity gives its
# activation seat back on any exit path. See ffbox/README.md for why that matters more here than
# it does in CI.
# shellcheck shell=bash

FFBOX_ACTIVATED=0

if ! declare -F log >/dev/null 2>&1; then
    log() { printf '[ffbox] %s\n' "$*"; }
fi

: "${FFBOX_OUT:=/ffbox/out}"
mkdir -p "$FFBOX_OUT"

# Activation is an ONLINE call that consumes a seat, and the seat only comes back on an explicit
# -returnlicense. game-ci's return_license.sh is an ordinary step, so a cancelled or crashed job
# never reaches it — that is how CI quietly leaks seats. As a trap this also survives `docker stop`
# and any early exit. (SIGKILL still can't be caught by anything in-process.)
return_license() {
    local rc=$?
    if [ "$FFBOX_ACTIVATED" = 1 ]; then
        log "returning Unity license"
        if ! unity-editor -logFile /dev/stdout -quit -returnlicense \
                -username "$UNITY_EMAIL" -password "$UNITY_PASSWORD" \
                -projectPath /BlankProject >>"$FFBOX_OUT/unity-license.log" 2>&1; then
            log "WARNING: license return failed — a seat may be leaked (see unity-license.log)"
        fi
    fi
    return $rc
}
trap return_license EXIT INT TERM

activate_unity() {
    # Same 5-try / 15s-doubling backoff as game-ci's activate.sh. Unity's licensing service is
    # genuinely flaky and a first-attempt failure means nothing.
    local delay=15 attempt
    for attempt in 1 2 3 4 5; do
        log "activating Unity license (attempt ${attempt}/5)"
        if unity-editor -logFile /dev/stdout -quit \
                -serial "$UNITY_SERIAL" \
                -username "$UNITY_EMAIL" \
                -password "$UNITY_PASSWORD" \
                -projectPath /BlankProject >>"$FFBOX_OUT/unity-license.log" 2>&1; then
            FFBOX_ACTIVATED=1
            log "activation complete"
            return 0
        fi
        if [ "$attempt" -lt 5 ]; then
            log "activation failed; retrying in ${delay}s"
            sleep "$delay"
            delay=$((delay * 2))
        fi
    done
    return 1
}

# Activate unless the caller opted out. Exits the task on failure — every caller needs a license
# before it can do anything useful with the editor.
ensure_unity_license() {
    if [ "${FFBOX_UNITY:-1}" != 1 ]; then
        log "Unity licensing skipped (--no-unity) — editor invocations in this run will fail"
        return 0
    fi
    local missing="" v
    for v in UNITY_SERIAL UNITY_EMAIL UNITY_PASSWORD; do
        [ -n "${!v:-}" ] || missing="${missing} ${v}"
    done
    if [ -n "$missing" ]; then
        log "ERROR: missing Unity credentials:${missing}"
        log "       set them in the ffbox secrets file, or pass --no-unity to skip licensing"
        exit 78
    fi
    if ! activate_unity; then
        log "ERROR: Unity activation failed after 5 attempts; see ${FFBOX_OUT}/unity-license.log"
        exit 79
    fi
}
