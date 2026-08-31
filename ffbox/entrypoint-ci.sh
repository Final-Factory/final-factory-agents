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
    git config --system lfs.url "${FFGHR_GIT_ORIGIN}.git/info/lfs" || :
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
