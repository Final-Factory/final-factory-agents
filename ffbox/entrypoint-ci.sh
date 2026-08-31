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

cd /opt/actions-runner

# NO --disableupdate. It is a config.sh option, not a `run` option: runner 2.337.0 answers
# "Unrecognized command-line input arguments for command run: 'disableupdate'" and exits 1. There
# is no environment variable for it either, so what keeps this runner current enough for GitHub to
# keep giving it jobs is the weekly image rebuild, not a flag.
#
# exec, so the runner is PID 1 and a `docker stop` delivers SIGTERM to it directly rather than to
# a shell that may or may not forward it.
exec ./bin/Runner.Listener run --jitconfig "$JIT"
