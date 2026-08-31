#!/usr/bin/env bash
#
# Unity activation and, more importantly, the return of the seat. SOURCED, never executed.
#
# ONE COPY, THREE CALLERS. ffbox's run-as-user.sh and discord-task.sh source it
# at /ffbox/unity-license.sh; main.yml's test step sources it at /opt/ffghr/unity-license.sh. The
# image installs it at BOTH paths and both are load-bearing: main.yml is already pushed naming the
# second, and changing a workflow file needs a token scope this box deliberately lacks.
#
# It used to be two copies. They diverged — ffbox required UNITY_SERIAL and decoded the .ulf in
# 04-warmLibrary.sh before ever calling in, while the CI copy decoded internally — and on
# 2026-08-29 the CI copy demanded a serial that CI never sets, so a real job died having made no
# network call at all. The decode below is why there is one copy now.
#
#     . /ffbox/unity-license.sh
#     ensure_unity_license
#     unity-editor -runTests ...
#
# WHY THIS EXISTS RATHER THAN game-ci's return_license STEP. Activation is an online call that
# consumes a seat, and the seat only comes back on an explicit -returnlicense. game-ci returns it
# in an ordinary later step, which a cancelled or failed job never reaches, and that is how it
# leaks them. Installed as a trap, the return happens on every exit path the shell can see,
# including `docker stop`. SIGKILL still cannot be caught by anything in-process, which is why
# the supervisor's watchdog sends TERM first and waits.
#
# A seat is held only while the step runs, so an idle slot holds none.
# shellcheck shell=bash

FFBOX_ACTIVATED=0

if ! declare -F log >/dev/null 2>&1; then
    log() { printf '[unity-license] %s\n' "$*"; }
fi

# The editor is extremely chatty and this runs inside a log a human reads. Full output goes to a
# file; the tail is printed only when something failed, which is when it is wanted.
#
# Where that file goes differs by caller and neither should have to care: ffbox mounts an output
# directory and exports FFBOX_OUT, a CI job has RUNNER_TEMP, and anything else gets /tmp.
: "${FFBOX_LICENSE_LOG:=${FFBOX_OUT:-${RUNNER_TEMP:-/tmp}}/unity-license.log}"
mkdir -p "$(dirname "$FFBOX_LICENSE_LOG")"

return_license() {
    local rc=$?
    if [ "$FFBOX_ACTIVATED" = 1 ]; then
        log "returning the Unity seat"
        if ! unity-editor -logFile /dev/stdout -quit -returnlicense \
                -username "$UNITY_EMAIL" -password "$UNITY_PASSWORD" \
                -projectPath /BlankProject >>"$FFBOX_LICENSE_LOG" 2>&1; then
            log "WARNING: the seat was not returned; it may be leaked"
            tail -30 "$FFBOX_LICENSE_LOG" >&2 || true
        else
            FFBOX_ACTIVATED=0
        fi
    fi
    return $rc
}
trap return_license EXIT INT TERM

activate_unity() {
    # Five tries with a doubling delay, the same shape game-ci's activate.sh uses. Unity's
    # licensing service is genuinely flaky and a first-attempt failure means nothing.
    local delay=15 attempt
    for attempt in 1 2 3 4 5; do
        log "activating (attempt ${attempt}/5)"
        if unity-editor -logFile /dev/stdout -quit \
                -serial "$UNITY_SERIAL" \
                -username "$UNITY_EMAIL" \
                -password "$UNITY_PASSWORD" \
                -projectPath /BlankProject >>"$FFBOX_LICENSE_LOG" 2>&1; then
            FFBOX_ACTIVATED=1
            log "activated"
            return 0
        fi
        if [ "$attempt" -lt 5 ]; then
            log "failed; retrying in ${delay}s"
            sleep "$delay"
            delay=$((delay * 2))
        fi
    done
    return 1
}

# THE ULF-TO-SERIAL DECODE, which is what game-ci does and what this script did not.
#
# Final Factory activates on a PERSONAL licence, so main.yml's secret is UNITY_LICENSE — the
# contents of a .ulf file — and UNITY_SERIAL is empty. Activation itself is an online serial
# activation and needs a 27-character serial, which is carried base64-encoded in the .ulf's
# DeveloperData field. game-ci decodes it; ffbox/04-warmLibrary.sh:146 decodes it; this did not,
# so it demanded a serial CI never sets and bailed before making a single network call.
#
# Measured on 2026-08-29: the smoke job's licence step exited 78 with "missing Unity credentials:
# UNITY_SERIAL" and the egress proxy logged no Unity connection at all.
#
# UNITY_LICENSE is the contents (a CI secret); UNITY_LICENSE_FILE is a path (how ffbox holds it).
# Both are accepted, contents first, because that is what a workflow passes.
decode_serial_from_ulf() {
    local ulf=""
    if [ -n "${UNITY_LICENSE:-}" ]; then
        ulf=$UNITY_LICENSE
    elif [ -n "${UNITY_LICENSE_FILE:-}" ] && [ -r "${UNITY_LICENSE_FILE}" ]; then
        ulf=$(cat "$UNITY_LICENSE_FILE")
    else
        return 1
    fi

    local serial
    serial=$(printf '%s' "$ulf" \
             | sed -n 's/.*<DeveloperData Value="\([^"]*\)".*/\1/p' \
             | head -1 | base64 -d 2>/dev/null | cut -c5-)
    if [ ${#serial} -ne 27 ]; then
        log "WARNING: decoded a ${#serial}-character serial from the licence; expected 27"
        return 1
    fi
    UNITY_SERIAL=$serial
    export UNITY_SERIAL
    log "decoded a serial from UNITY_LICENSE (ending ...${serial: -4})"
    return 0
}

# Activate, or fail the job. A job that starts Unity unlicensed does not fail: it runs, produces
# nothing usable, and the reason is buried 4000 lines into an editor log. Fail here instead.
ensure_unity_license() {
    local missing="" v

    # No serial, but a licence to decode one out of: do what game-ci does.
    if [ -z "${UNITY_SERIAL:-}" ]; then
        decode_serial_from_ulf || true
    fi

    for v in UNITY_SERIAL UNITY_EMAIL UNITY_PASSWORD; do
        [ -n "${!v:-}" ] || missing="${missing} ${v}"
    done
    if [ -n "$missing" ]; then
        log "ERROR: missing Unity credentials:${missing}"
        log "       these come from the workflow's env: block, out of repository secrets"
        log "       UNITY_SERIAL may be empty on purpose: on a Personal licence the serial is"
        log "       carried inside UNITY_LICENSE, and this script decodes it. If UNITY_SERIAL is"
        log "       still missing here, UNITY_LICENSE was empty or not a readable .ulf."
        exit 78
    fi
    if ! activate_unity; then
        log "ERROR: activation failed after 5 attempts"
        tail -50 "$FFBOX_LICENSE_LOG" >&2 || true
        exit 79
    fi
}
