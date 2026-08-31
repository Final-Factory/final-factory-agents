#!/bin/sh
# The whole of what runs in the container: take one job, then exit.
#
# Nothing polls GitHub, nothing receives a webhook, and no inbound port is opened. The runner
# dials out, takes the job it was minted for, and the container is gone afterwards.
set -eu

: "${FFGHR_JITCONFIG:?the supervisor must pass FFGHR_JITCONFIG; there is nothing to run without it}"

# Read it out of the environment and drop it, so a workflow step does not simply inherit the
# credential in `env`. This is hygiene rather than a boundary: the value is still in this
# process's argv below, and the job runs as root in its own container, so it can be read by
# anything determined. It is scoped to this one job and dies with the container, which is the
# property section 12 actually relies on.
JIT=$FFGHR_JITCONFIG
unset FFGHR_JITCONFIG

# THE UNITY MACHINE ID, WRITTEN BEFORE ANYTHING ELSE STARTS.
#
# Unity's licensing service identifies a machine by /etc/machine-id, and game-ci's base image pins
# it to one constant for every container it builds (images/ubuntu/base/Dockerfile:73, "Support
# forward compatibility for unity activation"). That is right for a .ulf licence file, which is
# bound to a machine; it is wrong for the personal SERIAL activation this project does, where two
# containers presenting the same id are one machine holding one entitlement, and the second
# concurrent activation dies with "Found 0 entitlement groups and 0 free entitlements", exit 198.
#
# game-ci's own action undoes the pin for exactly this case — unity-test-runner v4,
# dist/platforms/ubuntu/entrypoint.sh:3-7, `dbus-uuidgen > /etc/machine-id` when the serial starts
# with F. main.yml no longer runs that action, so this is where it has to happen instead.
#
# THE VALUE COMES FROM THE SUPERVISOR AND IS DERIVED FROM THE SLOT, not randomized here. An
# activation registers a machine and only -returnlicense gives it back, so a random id per
# container makes every leaked seat permanent; a per-slot id bounds the licence's registrations at
# the slot count and lets the next job on that slot reuse its entitlement. lib/config.sh's machine
# id section has the whole argument.
#
# VALIDATED AGAIN HERE because this runs as root and writes a file the whole container trusts.
# Anything that is not 32 hex characters is ignored, loudly, and the image's own id stands.
if [ -n "${FFGHR_MACHINE_ID:-}" ]; then
    if printf '%s' "$FFGHR_MACHINE_ID" | grep -qE '^[0-9a-f]{32}$'; then
        printf '%s\n' "$FFGHR_MACHINE_ID" > /etc/machine-id
        mkdir -p /var/lib/dbus
        ln -sf /etc/machine-id /var/lib/dbus/machine-id
        echo "[ffghr] machine id set to $FFGHR_MACHINE_ID"
    else
        echo "[ffghr] WARNING: FFGHR_MACHINE_ID is not 32 hex characters; keeping the image's" >&2
    fi
fi
unset FFGHR_MACHINE_ID

# The runner refuses to start as root unless this is set. It is set because the CONTAINER is the
# boundary, not the uid inside it: the job gets namespace-root either way, and the account
# underneath on the host owns nothing. Dropping to a non-root user here would buy nothing and
# would cost the workspace-ownership dance that ffbox has to do for its bind mount.
RUNNER_ALLOW_RUNASROOT=1
export RUNNER_ALLOW_RUNASROOT

# Point the runner at the actions baked into the image (see the Dockerfile block that builds it)
# so it does not download them from codeload.github.com before step one. A miss here is not fatal:
# the runner falls through to its normal download path, which is exactly today's behaviour.
ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE=/opt/ffghr/action-cache
export ACTIONS_RUNNER_ACTION_ARCHIVE_CACHE

# FETCH THE REPOSITORY FROM THE LOCAL MIRROR, NOT FROM github.com.
#
# insteadOf rewrites the URL at fetch time, so actions/checkout goes on computing the GitHub URL it
# always computed and git quietly dials the mirror on ffghr-net instead. Nothing in the workflow
# has to know. Measured: a 40-commit delta lands in 1 second against the mirror.
#
# SYSTEM CONFIG because the runner, its actions and the job's own steps are separate processes and
# this has to apply to all of them; --system is also the only level git treats as protected.
#
# THIS IS NOT THE BOUNDARY and is not meant to be. The job runs as root here and could unset it in
# a line. What makes GitHub unreachable is github.com leaving the egress allowlist; this only
# removes the NEED, which is the half that has to come first. While that entry is still present a
# job whose redirect fails simply fetches from GitHub as it always did.
#
# LFS IS DELIBERATELY LEFT POINTING AT GITHUB. git-lfs derives its endpoint from the remote URL and
# has nowhere to go with a git:// one, so pinning lfs.url keeps it working while the git objects
# come from the mirror. In practice the restored tarball already carries .git/lfs and LFS churn is
# near zero -- zero objects across the last fifty commits on master -- so this should be a no-op
# that never opens a connection. Whether it actually is wants measuring before github.com goes.
if [ -n "${FFGHR_GIT_MIRROR:-}" ] && [ -n "${FFGHR_GIT_ORIGIN:-}" ]; then
    git config --system "url.${FFGHR_GIT_MIRROR}.insteadOf" "${FFGHR_GIT_ORIGIN}" || :
    git config --system "url.${FFGHR_GIT_MIRROR}.insteadOf" "${FFGHR_GIT_ORIGIN}.git" --add || :
    # LFS AT THE MIRROR TOO. git-lfs speaks its own HTTP batch protocol and cannot derive an
    # endpoint from a git:// URL, so this was the last thing pinning github.com to the allowlist --
    # idle on almost every job, because a restored tarball already carries .git/lfs, and fatal on
    # the two cases that matter: a cold job with no cache entry, and the first commit that touches
    # an image. The mirror serves those objects download-only.
    if [ -n "${FFGHR_LFS_URL:-}" ]; then
        git config --system lfs.url "${FFGHR_LFS_URL}" || :
    else
        git config --system lfs.url "${FFGHR_GIT_ORIGIN}.git/info/lfs" || :
    fi
    echo "[ffghr] git fetches redirected to ${FFGHR_GIT_MIRROR}"
fi

cd /opt/actions-runner

# NO --disableupdate. It is a config.sh option, not a `run` option: runner 2.337.0 answers
# "Unrecognized command-line input arguments for command run: 'disableupdate'" and exits 1. There
# is no environment variable for it either, so what keeps this runner current enough for GitHub to
# keep giving it jobs is the weekly image rebuild, not a flag.
#
# exec, so the runner is PID 1 and a `docker stop` delivers SIGTERM to it directly rather than to
# a shell that may or may not forward it.
exec ./bin/Runner.Listener run --jitconfig "$JIT"
