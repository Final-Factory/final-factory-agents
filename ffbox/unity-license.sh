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
# TWO WAYS TO BE LICENSED, AND THE FIRST ONE IS THE POINT.
#
#   offline  a .ulf licence FILE, mounted read-only at FFBOX_UNITY_ULF. No credential, no network,
#            no seat, nothing to return. THIS IS THE PATH EVERYTHING SHOULD TAKE.
#   online   the old serial activation, kept only as a fallback for a caller that still supplies
#            UNITY_EMAIL and UNITY_PASSWORD -- which, after 2026-09-01, is main.yml alone.
#
# WHY OFFLINE FIRST. Until 2026-09-01 ffbox handed every container UNITY_EMAIL and UNITY_PASSWORD so
# it could activate on start. That is a full Unity account credential -- the same identity as the
# Asset Store account and the org membership -- sitting in the environment of a container that runs
# `claude -p --dangerously-skip-permissions` over text strangers wrote, readable by anything in it
# through /proc/self/environ. docs/docker-security-model.md's first premise is that this container
# is hostile; a credential inside it is compromised by assumption.
#
# The licensing client resolves entitlements from local files and makes no server call to do it:
#
#     Rebuilding resolvers from local files
#     Skipping directory watcher for: /root/.local/share/unity3d/Unity/*.ulf
#         -- Unity.Licensing.Client 1.18.1 --debug --showEntitlements, measured 2026-09-01
#
# So a mounted file is a complete substitute for the credential. ffbox/unity-offline-license.sh
# mints and installs it; this consumes it.
#
# WHY THE ONLINE PATH STILL HAS A RETURN TRAP RATHER THAN game-ci's return_license STEP. Activation
# is an online call that consumes a seat, and the seat only comes back on an explicit
# -returnlicense. game-ci returns it in an ordinary later step, which a cancelled or failed job
# never reaches, and that is how it leaks them. Installed as a trap, the return happens on every
# exit path the shell can see, including `docker stop`. SIGKILL still cannot be caught by anything
# in-process, which is why the supervisor's watchdog sends TERM first and waits.
#
# A seat is held only while the step runs, so an idle slot holds none. THE OFFLINE PATH TAKES NO
# SEAT AT ALL, so it arms none of this: a .ulf is not consumed by being read.
# shellcheck shell=bash

# INHERITED, NOT ASSUMED ZERO. A seat can be taken by one process and handed to another: the pool
# activates while it stages and then `exec`s the turn task, which is the SAME process with a new
# image, and that task has to know it already holds one rather than taking a second.
FFBOX_ACTIVATED=${FFBOX_ACTIVATED:-0}

# WHO TOOK IT, so that only they give it back. Both variables are exported once a seat is held, so
# every CHILD inherits them -- and a child must not return a seat its parent is still using.
# ffverify is exactly that child: an agent may run it mid-turn, it sources this file, and its EXIT
# trap would otherwise hand back the licence the turn is still holding and leave the rest of the
# run unlicensed.
#
# The pid is the right discriminator because `exec` PRESERVES it: pool-task.sh activates as pid 1
# and the turn task it execs is still pid 1, so the handoff works, while ffverify is a fork with a
# pid of its own and gives back only what it took itself.
FFBOX_LICENCE_OWNER=${FFBOX_LICENCE_OWNER:-}

# WHICH OF THE TWO PATHS TOOK THE LICENCE, because only one of them may give it back. An offline
# licence is a file that was read; calling -returnlicense against it would need the credentials we
# went to this trouble to remove, and there is nothing on Unity's side to return.
FFBOX_LICENCE_MODE=${FFBOX_LICENCE_MODE:-}

# THE MOUNTED LICENCE. Read-only, and deliberately NOT at the path the licensing client reads:
# that path is under $HOME, and the two lanes have different homes -- CI runs as root and the agent
# lane drops privilege to a user entrypoint.sh creates with HOME=/home/ffbox. A fixed mount point
# plus a copy inside is one code path instead of a guess made at `docker run` time about a uid that
# does not exist yet.
FFBOX_UNITY_ULF=${FFBOX_UNITY_ULF:-/ffbox/unity/Unity_lic.ulf}

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
    # AN OFFLINE LICENCE IS NEVER RETURNED. It took no seat, so there is nothing to hand back, and
    # -returnlicense wants the -username/-password this whole change exists to delete. Checked
    # before the owner test rather than after, because the mode is the reason and the pid is only
    # the tiebreak.
    if [ "$FFBOX_LICENCE_MODE" = offline ]; then
        return $rc
    fi
    if [ "$FFBOX_ACTIVATED" = 1 ] && [ "$FFBOX_LICENCE_OWNER" = "$$" ]; then
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

# Where the licensing client looks. IT IS A GLOB UNDER $HOME, not one fixed filename:
#
#     Skipping directory watcher for: /root/.local/share/unity3d/Unity/*.ulf
#
# so the name we copy to does not matter and the directory does. $HOME is read at call time rather
# than baked, because in the agent lane this runs AFTER setpriv has dropped to a user that did not
# exist when the container started.
unity_license_dir() { printf '%s/.local/share/unity3d/Unity' "${HOME:-/root}"; }

# The licensing client binary, which is what can answer "is there a valid licence here" without
# paying for an editor launch.
licensing_client() {
    printf '%s/Editor/Data/Resources/Licensing/Client/Unity.Licensing.Client' "${UNITY_PATH:-/opt/unity}"
}

# TAKE THE MOUNTED LICENCE, or return 1 if there is not one to take.
#
# COPIED RATHER THAN SYMLINKED, and rather than mounted straight at the destination. The mount is
# read-only and lives at a fixed path; the destination is under a $HOME that differs per lane and,
# in the agent lane, belongs to a user created at run time. A copy is the one operation that works
# in both without the host having to predict a uid.
install_offline_license() {
    local src=$FFBOX_UNITY_ULF dir out

    dir=$(unity_license_dir)

    # ALREADY STAGED? entrypoint.sh copies the licence into the run user's home while it is still
    # root, because the read-only mount is mode 600 and owned by root and the task is not. So the
    # normal case in the agent lane is that the file is already here and the mount is UNREADABLE --
    # checking the destination first is what keeps that from looking like a missing licence.
    if [ -r "$dir/Unity_lic.ulf" ]; then
        verify_offline_license || return 1
        FFBOX_ACTIVATED=1
        FFBOX_LICENCE_MODE=offline
        FFBOX_LICENCE_OWNER=$$
        export FFBOX_ACTIVATED FFBOX_LICENCE_MODE FFBOX_LICENCE_OWNER
        log "licensed from the staged .ulf (no credentials, no seat taken)"
        return 0
    fi

    [ -n "$src" ] && [ -r "$src" ] || return 1
    if ! mkdir -p "$dir" 2>>"$FFBOX_LICENSE_LOG"; then
        log "WARNING: could not create $dir; cannot use the offline licence"
        return 1
    fi
    if ! cp "$src" "$dir/Unity_lic.ulf" 2>>"$FFBOX_LICENSE_LOG"; then
        log "WARNING: could not copy $src into $dir"
        return 1
    fi
    chmod 600 "$dir/Unity_lic.ulf" 2>/dev/null || :

    verify_offline_license || return 1

    FFBOX_ACTIVATED=1
    FFBOX_LICENCE_MODE=offline
    FFBOX_LICENCE_OWNER=$$
    export FFBOX_ACTIVATED FFBOX_LICENCE_MODE FFBOX_LICENCE_OWNER
    log "licensed from the mounted .ulf (no credentials, no seat taken)"
    return 0
}

# VERIFIED WHERE IT IS CHEAP. An unusable licence otherwise surfaces as an editor that starts, finds
# nothing, and fails thousands of log lines into somebody's run. The client answers in under a second
# and says "No licenses were found." when the file is absent, invalid, or bound to a different machine
# id -- exactly the set of ways this can be wrong.
verify_offline_license() {
    local out
    [ -x "$(licensing_client)" ] || return 0
    out=$("$(licensing_client)" --showEntitlements 2>&1 || true)
    printf '%s\n' "$out" >>"$FFBOX_LICENSE_LOG"
    case "$out" in
        *"No licenses were found"*|*"no licenses were found"*)
            log "ERROR: the Unity licence did not resolve."
            log "       Most likely it is bound to a different /etc/machine-id than this"
            log "       container presents. On the host, check:"
            log "         sh ffbox/unity-offline-license.sh status"
            return 1 ;;
    esac
    return 0
}

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
            FFBOX_LICENCE_MODE=online
            FFBOX_LICENCE_OWNER=$$
            export FFBOX_ACTIVATED FFBOX_LICENCE_MODE FFBOX_LICENCE_OWNER
            log "activated online (a seat is held until this process exits)"
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

# TRY to take a seat. Returns 0 on success, 78 for missing credentials, 79 when activation failed.
# NEVER EXITS -- see ensure_unity_license below for the caller that wants it to.
#
# Two callers want two different things from the same work. A turn cannot do its job unlicensed and
# should die loudly; a POOL container that fails to get a seat is still a perfectly good warm
# workspace, and retiring it over a licensing hiccup would turn one bad round trip into an empty
# pool. Splitting the attempt from the dying is the whole reason this function exists separately.
try_unity_license() {
    local missing="" v

    # ALREADY HOLDING ONE. The pool takes a seat while it stages and hands it across the exec, and
    # ffverify may be run by an agent whose turn already has one. Both reach here; neither should
    # spend a second editor launch discovering that the answer is yes.
    if [ "$FFBOX_ACTIVATED" = 1 ]; then
        log "already licensed (${FFBOX_LICENCE_MODE:-unknown}, taken by pid ${FFBOX_LICENCE_OWNER:-?})"
        return 0
    fi

    # THE OFFLINE LICENCE FIRST, ALWAYS. It costs a file copy and a sub-second check, it needs no
    # credential and no network, and it takes no seat -- so there is no case where trying the
    # online path first would be better. When this succeeds nothing below runs, which is the whole
    # point: a container that never reaches activate_unity never needed a password.
    if install_offline_license; then
        return 0
    fi

    # --- fallback: the old online serial activation ----------------------------------------------
    #
    # REACHED ONLY BY A CALLER THAT STILL SUPPLIES CREDENTIALS. After 2026-09-01 ffbox passes none,
    # so for the agent lane this is dead code and the error below is what a missing or misbound
    # .ulf actually produces. main.yml still puts UNITY_EMAIL/UNITY_PASSWORD in its env: block out
    # of repository secrets, so a CI job can still land here -- until that workflow is changed,
    # which needs a token scope this box deliberately lacks.
    if [ -z "${UNITY_LICENSE:-}${UNITY_EMAIL:-}${UNITY_SERIAL:-}" ]; then
        log "ERROR: no Unity licence available."
        log "       Expected a .ulf mounted at $FFBOX_UNITY_ULF and no credentials are set,"
        log "       so there is no fallback either. On the host:"
        log "         sh ffbox/unity-offline-license.sh status"
        log "       and if nothing is installed:"
        log "         sh ffbox/unity-offline-license.sh mint    # asks for the Unity account once"
        return 78
    fi

    log "NOTE: falling back to ONLINE activation with account credentials."
    log "      This container holds a Unity password. Install an offline .ulf to stop that:"
    log "      ffbox/unity-offline-license.sh"

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
        return 78
    fi
    if ! activate_unity; then
        log "ERROR: activation failed after 5 attempts"
        tail -50 "$FFBOX_LICENSE_LOG" >&2 || true
        return 79
    fi
    return 0
}

# Activate, or fail the job. A job that starts Unity unlicensed does not fail: it runs, produces
# nothing usable, and the reason is buried 4000 lines into an editor log. Fail here instead.
ensure_unity_license() {
    local rc=0
    try_unity_license || rc=$?
    [ "$rc" -eq 0 ] || exit "$rc"
}
