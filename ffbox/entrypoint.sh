#!/usr/bin/env bash
#
# ffbox container entrypoint. Runs as root, then drops to the UID that owns the workspace.
#
# WHY THE UID DANCE
# The workspace is a bind mount of a ZFS clone owned by the host user. If Claude ran as root, every
# file it created would come back root-owned, and the harvest step on the host (git diff, patch
# extraction) could neither read nor clean them up. This mirrors what game-ci's entrypoint does
# under runAsHostUser:true — which is exactly how .github/workflows/main.yml already runs.
#
# Deliberately NOT copied from game-ci IN THIS LANE: their entrypoint runs
# `dbus-uuidgen > /etc/machine-id` when the serial starts with F (a personal license), so every
# container looks like a brand-new machine to Unity's licensing service. That is ruinous for an
# agent loop — it would burn a fresh activation seat on every single run. The agent lane keeps the
# machine ID stable so repeat runs look like one machine. See run-as-user.sh for the other half.
#
# THE CI LANE DOES OVERRIDE IT, because there the stable id is what stops two jobs activating at
# once, and the supervisor derives one id PER SLOT rather than a fresh one per run — so the licence
# still sees a small fixed set of machines rather than one per job. entrypoint-ci.sh, and the
# machine id section of ffbox/runners/lib/config.sh.
set -euo pipefail

# --- mode ------------------------------------------------------------------------------------
#
# TWO KINDS OF WORK, ONE IMAGE. agent is everything this entrypoint did before and stays the
# default, so nothing that does not set FFBOX_MODE changes behaviour at all. ci skips the whole
# uid dance below: a CI job has no bind-mounted workspace to match ownership with, its workspace
# is a tmpfs the container owns outright, and the runner refuses to start as anything but the
# user it was told about.
#
# The mode is chosen by the supervisor before the container starts and cannot be changed from
# inside it. See design/ffbox_unified_runners_design.txt section 2.
case "${FFBOX_MODE:-agent}" in
    agent) ;;
    ci)    exec /ffbox/entrypoint-ci.sh ;;
    *)     echo "ffbox: FFBOX_MODE must be 'agent' or 'ci', got '${FFBOX_MODE}'" >&2; exit 2 ;;
esac

# --- the Unity machine id ------------------------------------------------------------------------
#
# WRITTEN BEFORE ANYTHING ELSE STARTS, and by the only thing in here that is root.
#
# The header above says this lane deliberately does NOT randomize the id the way game-ci's action
# does, and that stays true -- a fresh id per container makes every leaked seat permanent. What was
# missing is the other half: the image's id is a CONSTANT shared by every container built from it,
# so two runs that both reach an editor are one machine to Unity's licensing service and the second
# activation dies with "Found 0 entitlement groups and 0 free entitlements", exit 198. That is not
# hypothetical; ffgithubrunners measured it and entrypoint-ci.sh has done this since.
#
# The value is derived from a claimed SLOT on the host (ffbox/lib-workloads.sh) and passed in, so
# the licence sees a small recycled set of machines rather than one per run. Empty means "leave the
# image's alone", which is what a box that has not enabled this asks for.
#
# VALIDATED HERE because this runs as root and writes a file the whole container trusts. Anything
# that is not 32 hex characters is ignored, loudly, and the image's own id stands.
if [ -n "${FFBOX_MACHINE_ID:-}" ]; then
    if printf '%s' "$FFBOX_MACHINE_ID" | grep -qE '^[0-9a-f]{32}$'; then
        printf '%s\n' "$FFBOX_MACHINE_ID" > /etc/machine-id
        mkdir -p /var/lib/dbus
        ln -sf /etc/machine-id /var/lib/dbus/machine-id
        echo "[ffbox] machine id set to $FFBOX_MACHINE_ID"
    else
        echo "[ffbox] WARNING: FFBOX_MACHINE_ID is not 32 hex characters; keeping the image's" >&2
    fi
fi
unset FFBOX_MACHINE_ID

WORKSPACE=${FFBOX_WORKSPACE:-/opt/actions-runner/_work/FinalFactory/FinalFactory}

if [ ! -d "$WORKSPACE" ]; then
    echo "ffbox: nothing bind-mounted at $WORKSPACE" >&2
    exit 1
fi

# FILL THE WORKSPACE FIRST, WHEN IT ARRIVES EMPTY. A --tmpfs workspace starts with nothing in it,
# so the restore has to happen in here rather than on the host -- which is the whole point: the
# workspace never exists on a host path, it is capped by the tmpfs, and the kernel frees it when
# this container goes, with no cleanup code to fail. Only /ffbox/out survives, which is exactly
# what a run is meant to hand back.
#
# Guarded on the workspace being EMPTY so the bind-mounted path still works untouched: with a
# host-prepared workspace there is nothing to restore and this is skipped.
# BEFORE THE RESTORE, and that is the whole point of taking it here. tar running as root applies
# the archive's ownership to the TARGET DIRECTORY as well as its contents, so after extraction
# the workspace itself is root-owned -- and reading the uid afterwards gives 0, making the chown below
# a no-op that changes root-owned files to root-owned files. The agent then cannot write a single
# file outside .git and reports the workspace as root-owned, which is what two real runs did.
uid=$(stat -c '%u' "$WORKSPACE")
gid=$(stat -c '%g' "$WORKSPACE")

if [ -n "${FFBOX_CACHE_ENTRY:-}" ] && [ -z "$(ls -A "$WORKSPACE" 2>/dev/null)" ]; then
    [ -x /ffbox/restore-workspace.sh ] || { echo "ffbox: restore-workspace.sh is missing" >&2; exit 1; }
    /ffbox/restore-workspace.sh || { echo "ffbox: workspace restore failed" >&2; exit 1; }
    # Hand the whole tree to the account the run drops to. Not conditional and not best-effort:
    # a workspace the agent cannot write is a run that can do nothing and says so late.
    chown -R "$uid":"$gid" "$WORKSPACE" \
        || { echo "ffbox: could not give the workspace to $uid:$gid" >&2; exit 1; }
fi

# Which task this container runs: the one-shot Claude prompt by default, or the Library import
# when --task or --job sets FFBOX_ENTRY. Both drop privileges the same way and share the Unity
# licensing in unity-license.sh.
TASK=${FFBOX_ENTRY:-/ffbox/run-as-user.sh}
[ -r "$TASK" ] || { echo "ffbox: no such task script: $TASK" >&2; exit 1; }

# UNMAPPED MEANS THE DAEMON AND THE WORKSPACE DISAGREE ABOUT WHO OWNS IT. 65534 is what a
# rootless daemon shows for a host uid outside its own subuid map. It happens when the workspace
# belongs to one account and the daemon to another — the exact state of a machine half-migrated
# onto the shared daemon. Carrying on would run `useradd -u 65534`, which either fails or invents
# a user that owns nothing, and the run would fail much later for a reason that looks unrelated.
#
# Measured on 2026-08-29: golden owned by FinalFactoryTester reads as 0:0 on that account's own
# daemon and as 65534:65534 on ffbox-container's.
if [ "$uid" -eq 65534 ] || [ "$gid" -eq 65534 ]; then
    cat >&2 <<'MSG'
ffbox: the workspace is owned by a uid this daemon cannot map (65534/nobody).

  The daemon and the workspace belong to different accounts. On the shared daemon the workspace
  must be owned by the container account, so that it appears as root inside:

      sudo chown -R ffbox-container:ffbox-container /opt/FinalFactory

  See section 17 of design/ffgithubrunners_design.txt.
MSG
    exit 1
fi

# A ROOT-OWNED WORKSPACE STILL MEANS DROPPING PRIVILEGE, and it did not used to.
#
# The shortcut here used to `exec bash "$TASK"` as root, on the grounds that there was no
# ownership to match. That is true and it is not the only reason the dance exists: Claude Code
# refuses --dangerously-skip-permissions when it is running as root, so run-as-user.sh died with
# "cannot be used with root/sudo privileges for security reasons" and the run produced nothing.
#
# This is not new and the shared daemon did not cause it. The workspace mapped to uid 0 on the old
# daemon too, for the mirror-image reason: it was owned by the account that owned that daemon.
# design/ffcache_design.txt section 12 records the same observation from the other side.
#
# So: pick an ordinary uid and drop to it, keeping GROUP 0. The workspace and the output mount are
# both 2775 and both group-owned by the container account, which is gid 0 in here, so group
# membership is what carries write access across. Nothing else changes — the same setpriv, the
# same PID-1 reasoning, the same trap.
if [ "$uid" -eq 0 ]; then
    uid=1000
    gid=0
fi

if ! getent group "$gid" >/dev/null; then
    groupadd -g "$gid" ffbox
fi

# `|| true` is load-bearing: getent exits 2 when the id is absent, which under `set -e` with
# pipefail aborts the script on the assignment itself — silently, before anything is logged.
user=$(getent passwd "$uid" | cut -d: -f1) || true
if [ -z "$user" ]; then
    user=ffbox
    useradd -u "$uid" -g "$gid" -m -d /home/ffbox -s /bin/bash ffbox
fi

# Unity writes its licence and cache under HOME, so HOME has to be this user's. The activation
# would otherwise fail in a way that reads as a licensing problem.


home=$(getent passwd "$uid" | cut -d: -f6) || true
[ -n "$home" ] || home=/home/ffbox
mkdir -p "$home"
chown "$uid:$gid" "$home"

# The privilege drop needs to leave run-as-user.sh as PID 1, so that a `docker stop` delivers
# SIGTERM straight to it and its return-license trap fires. `su` forks rather than execs and
# forwards signals unreliably, which would silently leak a Unity seat on every stopped container;
# setpriv replaces the process image instead.
export HOME="$home"
export USER="$user"

# GIT INSIDE THE CONTAINER NEEDS THE SAME EXEMPTION THE HOST DOES. The workspace belongs to the
# container account, which is uid 0 in here, and we have just dropped to 1000 — so git refuses
# with "detected dubious ownership" and the run reports "<the workspace> (not a git repo)" while
# looking otherwise healthy. An agent that cannot read the repo cannot do its job, and nothing
# about the failure says so.
#
# Through the environment rather than a config file: it names the one directory, it applies to
# every git the task runs, and it leaves nothing behind in an image layer or a home directory.
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=safe.directory
export GIT_CONFIG_VALUE_0="$WORKSPACE"

# GIT NEVER ASKS A QUESTION IN HERE. There is no terminal to answer it on, and the failure git
# produces when it tries -- "could not read Username for 'https://github.com'" -- reads like a
# broken url rather than a missing credential. Off, so an unauthenticated fetch fails in one line
# that says what it is. Set whether or not there is a credential below: it is a property of being
# a container, not of being an authenticated one.
export GIT_TERMINAL_PROMPT=0

# THE GIT CREDENTIAL, STAGED WHILE WE ARE STILL ROOT, and only when this container was given one.
# ffbox passes FFBOX_GH_TOKEN only for an agent class whose pools.<class>.github.container_token
# names a variable that is set; ffagent names nothing, so a container serving strangers' text
# reaches this block with nothing in the variable and writes no credential at all.
#
# READ ffbox/CREDENTIALS.md SECTION 4. For a class that has one of these, the scope of the token
# is what stands between an agent and a force-push to master. Nothing in this file constrains it.
#
# ~/.git-credentials RATHER THAN THE ENVIRONMENT ALONE, because git-lfs, a hook, and anything the
# agent shells out to all find a credential helper and none of them inherit a variable reliably.
# It matches by HOST, so the token is offered to github.com and to nothing else -- not to a
# registry, not to a package host, not to whatever a prompt talks it into cloning.
#
# THE VALUE IS WRITTEN, NEVER ECHOED, and the file is the run user's at 600. Staged here for the
# same reason the Unity licence below is: this is the last moment we are root, and the file has to
# belong to the account the task runs as.
if [ -n "${FFBOX_GH_TOKEN:-}" ]; then
    _credfile="$home/.git-credentials"
    if (umask 077; printf 'https://x-access-token:%s@github.com\n' "$FFBOX_GH_TOKEN" \
            > "$_credfile") 2>/dev/null; then
        # `|| :` under `set -e`: a container that cannot write a gitconfig is a container with
        # no git credential, which is a degraded run and not a dead one. Dying here would take
        # the whole turn down for the one capability it can most easily do without.
        git config --file "$home/.gitconfig" credential.helper store || :
        chown "$uid:$gid" "$_credfile" "$home/.gitconfig" 2>/dev/null || :
        chmod 600 "$_credfile" 2>/dev/null || :
        echo "[ffbox] git credential staged for $user (github.com)"
    else
        echo "[ffbox] WARNING: could not stage the git credential at $_credfile" >&2
    fi
fi

# THE UNITY LICENCE, STAGED WHILE WE ARE STILL ROOT. This has to happen HERE and cannot be left to
# unity-license.sh in the task, which is the obvious place for it.
#
# The .ulf is mounted read-only from the host at mode 600. Under the rootless daemon the host account
# maps to root in here, so the file arrives owned by root and readable by root ALONE -- and the task
# runs as uid 1000. It would find the mount unreadable, report "no Unity licence available", and the
# run would die at its first editor with a message about a file that is plainly right there.
#
# Measured 2026-09-01: CI (which stays root) licensed fine while the agent lane failed with exit 78
# on the identical mount. Copying it across as root, owned by the run user, is what makes the two
# lanes behave the same.
#
# WIDENING THE HOST FILE INSTEAD WOULD BE WRONG. It is a licence; 600 on the host is correct, and the
# container is where the copy belongs.
if [ -n "${FFBOX_UNITY_ULF:-}" ] && [ -r "${FFBOX_UNITY_ULF}" ]; then
    _licdir="$home/.local/share/unity3d/Unity"
    if mkdir -p "$_licdir" && cp "$FFBOX_UNITY_ULF" "$_licdir/Unity_lic.ulf"; then
        chown -R "$uid:$gid" "$home/.local" 2>/dev/null || :
        chmod 600 "$_licdir/Unity_lic.ulf" 2>/dev/null || :
        echo "[ffbox] Unity licence staged for $user"
    else
        echo "[ffbox] WARNING: could not stage the Unity licence into $_licdir" >&2
    fi
fi

exec setpriv --reuid="$user" --regid="$gid" --init-groups bash "$TASK"
