#!/usr/bin/env bash
#
# ffbox container entrypoint. Runs as root, then drops to the UID that owns the workspace.
#
# WHY THE UID DANCE
# /workspace is a bind mount of a ZFS clone owned by the host user. If Claude ran as root, every
# file it created would come back root-owned, and the harvest step on the host (git diff, patch
# extraction) could neither read nor clean them up. This mirrors what game-ci's entrypoint does
# under runAsHostUser:true — which is exactly how .github/workflows/main.yml already runs.
#
# Deliberately NOT copied from game-ci: their entrypoint runs `dbus-uuidgen > /etc/machine-id`
# when the serial starts with F (a personal license), so every container looks like a brand-new
# machine to Unity's licensing service. That is fine for CI running a few times a day and ruinous
# for an agent loop — it would burn a fresh activation seat on every single run. We keep the
# machine ID stable so repeat runs look like one machine. See run-as-user.sh for the other half.
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

WORKSPACE=${FFBOX_WORKSPACE:-/workspace}

if [ ! -d "$WORKSPACE" ]; then
    echo "ffbox: nothing bind-mounted at $WORKSPACE" >&2
    exit 1
fi

uid=$(stat -c '%u' "$WORKSPACE")
gid=$(stat -c '%g' "$WORKSPACE")

# Which task this container runs: the one-shot Claude prompt by default, or the Library import
# when 04-warmLibrary.sh sets FFBOX_ENTRY. Both drop privileges the same way and share the Unity
# licensing in unity-license.sh.
TASK=${FFBOX_ENTRY:-/ffbox/run-as-user.sh}
[ -r "$TASK" ] || { echo "ffbox: no such task script: $TASK" >&2; exit 1; }

# A root-owned workspace means no mapping to do — just run.
if [ "$uid" -eq 0 ]; then
    exec bash "$TASK"
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
exec setpriv --reuid="$user" --regid="$gid" --init-groups bash "$TASK"
