#!/bin/sh
# test.sh — every offline suite in this tree, in one command, with one exit status.
#
#   sh ffbox/test.sh
#
# WHY THIS EXISTS. There are four suites now, in two languages, in two directories. Running them
# as `for t in ...; do sh $t; done` looks like it checks them and does not: the loop's status is
# the LAST one's, so a failure anywhere but the end is invisible to `&&`. That is not a
# hypothetical -- on 2026-09-08 a red test_reap.sh went past exactly that shape and was committed
# and pushed. One entry point with one status is the fix, and it is four lines of the work.
#
# OFFLINE ONLY. Nothing here needs the daemon, GitHub, or a container: test_reap.sh and
# test_ci_lane.py stub what they need and both refuse to run if the stub is not the thing they
# reached. Suites that need a live box do not belong here, because a suite that is sometimes
# skipped is a suite nobody believes.

set -u

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
FAILED=""

run() {   # <name> <command...>
    # THE NAME IS CAPTURED BEFORE THE shift, and the first version of this did not do that -- so a
    # failure was reported as `FAILED: sh`, which is the name of the interpreter rather than of
    # anything that failed. Caught by deliberately breaking a suite to check this file works,
    # which is worth doing to a test runner before trusting one.
    _name=$1
    printf '\n======== %s\n' "$_name"
    shift
    if "$@"; then
        unset _name
        return 0
    fi
    FAILED="$FAILED $_name"
    unset _name
    return 0        # keep going: one broken suite should not hide the state of the others
}

run "runners/test_pool.sh"  sh  "$HERE/runners/test_pool.sh"
run "runners/test_reap.sh"  sh  "$HERE/runners/test_reap.sh"
run "runners/test_pin.sh"   sh  "$HERE/runners/test_pin.sh"
run "test_ci_lane.py"       python3 "$HERE/test_ci_lane.py"
# THE ONE SUITE THAT DRIVES THE REAL ffbox, against a stub docker and its own secrets file. It
# was not in this runner until 2026-09-10, which meant the properties it holds -- no credential
# in argv, one Claude credential per container and never two -- were checked only when somebody
# remembered to run it by hand. That is the state this file exists to end.
run "test_container_credential.sh" sh "$HERE/test_container_credential.sh"
run "test_update_drain.sh"  sh  "$HERE/test_update_drain.sh"
# THE RESTORE, which is the one script that decides whether a container gets as far as the agent
# at all. Its suite needs git-lfs and skips itself without one, because the property it holds --
# that a reset onto a branch resolves LFS from the mirror rather than from GitHub -- cannot be
# checked with LFS absent.
run "test_restore_workspace.sh" sh "$HERE/test_restore_workspace.sh"
# THE TWO BIG PYTHON SUITES BELONG HERE TOO, and leaving them out was the same mistake this file
# was written to stop. I built a single entry point for the shell suites and then went on running
# test_ffwatch.py and test_ffweb.py by hand -- which meant reading their output rather than their
# exit status, and on 2026-09-08 that let a ffweb check fail unnoticed for three commits because I
# looked at the head of the output instead of the end. A runner that covers most of the suites is
# a runner somebody will still supplement by hand.
#
# test_ffwatch.py IS SLOW -- minutes, against a real sqlite database and a stubbed daemon -- and
# that is not a reason to leave it out. It is a reason to run this before pushing rather than
# after every edit.
run "test_ffwatch.py"       python3 "$HERE/test_ffwatch.py"
run "test_ffweb.py"         python3 "$HERE/test_ffweb.py"

printf '\n========\n'
if [ -n "$FAILED" ]; then
    printf 'FAILED:%s\n' "$FAILED"
    exit 1
fi
printf 'all suites passed\n'
