#!/usr/bin/env python3
"""Offline tests for update-golden.sh and the golden lock.

Run: python3 ffbox/test_golden_lock.py

No network, no docker, no ZFS, no Unity. git is deliberately NOT stubbed — the whole point of
update-golden.sh is what git does to a working tree, and a stub would prove nothing about a
fast-forward, a dirty tree or a divergence. Every test builds a real bare "origin" and a real
clone standing in for golden.

THE MUTUAL-EXCLUSION TESTS DO NOT MEASURE TIME. There is no sleep anywhere in this file and no
"wait a bit and see". The interleaving is forced with a FIFO: a holder process takes the lock
and then blocks reading a pipe, so the test decides exactly when it lets go. The assertion is
an ORDER of lines in a log, not a duration.

An earlier version of this file inferred the lock from the ORDER two processes finished in.
That test passed with the flock deleted — the first process wrote its "released" marker while
the second was still running git, so the order came out right for the wrong reason. Ordering is
not evidence of exclusion. These tests observe the lock itself with `flock -n`, which either
takes it or fails immediately, and pin the observation to a moment the test controls: an updater
stopped mid-critical-section by a stub git that blocks on a pipe.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATE_GOLDEN = os.path.join(HERE, "update-golden.sh")

GIT_ENV = {
    "GIT_AUTHOR_NAME": "ffbox test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "ffbox test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
}


def git(repo, *args, check=True):
    env = dict(os.environ, **GIT_ENV)
    p = subprocess.run(["git", "-C", repo, *args], env=env,
                       capture_output=True, text=True)
    if check and p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout.strip()


def head(repo):
    return git(repo, "rev-parse", "HEAD")


class Fixture:
    """A bare origin, a golden clone of it, and a lock path — all under one temp dir."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="ffbox-golden-test-")
        self.origin = os.path.join(self.root, "origin.git")
        self.golden = os.path.join(self.root, "golden")
        self.lock = os.path.join(self.root, "golden.lock")
        self.log = os.path.join(self.root, "order.log")

        subprocess.run(["git", "init", "--quiet", "--bare", "-b", "master", self.origin],
                       check=True, capture_output=True)
        seed = os.path.join(self.root, "seed")
        subprocess.run(["git", "clone", "--quiet", self.origin, seed],
                       check=True, capture_output=True)
        self.write(seed, "README.md", "one\n")
        git(seed, "add", "-A")
        git(seed, "commit", "--quiet", "-m", "first")
        git(seed, "push", "--quiet", "origin", "master")
        self.seed = seed

        subprocess.run(["git", "clone", "--quiet", self.origin, self.golden],
                       check=True, capture_output=True)

    def write(self, repo, name, text):
        with open(os.path.join(repo, name), "w") as fh:
            fh.write(text)

    def push_new_commit(self, text="two\n"):
        """Advance origin by one commit. Returns its sha."""
        self.write(self.seed, "README.md", text)
        git(self.seed, "add", "-A")
        git(self.seed, "commit", "--quiet", "-m", "next")
        git(self.seed, "push", "--quiet", "origin", "master")
        return head(self.seed)

    def env(self):
        return dict(os.environ, **GIT_ENV, **{
            "FFBOX_GOLDEN_MNT": self.golden,
            "FFBOX_GOLDEN_LOCK": self.lock,
            "FFBOX_CONFIG_DIR": self.root,
        })

    def update(self, *args):
        return subprocess.run(["sh", UPDATE_GOLDEN, *args], env=self.env(),
                              capture_output=True, text=True)

    def read_log(self):
        try:
            with open(self.log) as fh:
                return [line.strip() for line in fh if line.strip()]
        except FileNotFoundError:
            return []

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


# ----------------------------------------------------------------------------------------------
# what the update itself promises
# ----------------------------------------------------------------------------------------------

def test_fast_forwards_golden_to_origin(fx):
    target = fx.push_new_commit()
    assert head(fx.golden) != target, "fixture is wrong: golden already has the commit"

    p = fx.update()
    assert p.returncode == 0, p.stderr
    assert head(fx.golden) == target, "golden did not reach origin"
    assert "README.md" in os.listdir(fx.golden)
    with open(os.path.join(fx.golden, "README.md")) as fh:
        assert fh.read() == "two\n", "the working tree was not updated, only the ref"


def test_no_op_when_already_current(fx):
    before = head(fx.golden)
    p = fx.update()
    assert p.returncode == 0, p.stderr
    assert head(fx.golden) == before
    assert "nothing to take" in p.stdout, p.stdout


def test_refuses_a_dirty_golden(fx):
    fx.push_new_commit()
    before = head(fx.golden)
    fx.write(fx.golden, "README.md", "somebody was editing golden\n")

    p = fx.update()
    assert p.returncode != 0, "a dirty golden must not be updated"
    assert "local changes" in p.stderr, p.stderr
    assert head(fx.golden) == before, "golden moved despite refusing"
    with open(os.path.join(fx.golden, "README.md")) as fh:
        assert fh.read() == "somebody was editing golden\n", "the edit was destroyed"


def test_refuses_detached_head(fx):
    git(fx.golden, "checkout", "--quiet", "--detach", "HEAD")
    p = fx.update()
    assert p.returncode != 0
    assert "detached HEAD" in p.stderr, p.stderr


def test_refuses_a_divergence(fx):
    fx.push_new_commit()
    fx.write(fx.golden, "LOCAL.md", "a commit only golden has\n")
    git(fx.golden, "add", "-A")
    git(fx.golden, "commit", "--quiet", "-m", "local only")
    before = head(fx.golden)

    p = fx.update()
    assert p.returncode != 0, "a divergence must not be merged"
    assert "fast-forward" in p.stderr, p.stderr
    assert head(fx.golden) == before


def test_survives_a_repo_with_no_lfs_content(fx):
    """golden has LFS; a test fixture does not. The updater must not care."""
    fx.push_new_commit()
    p = fx.update("--verify")
    assert p.returncode == 0, p.stderr + p.stdout


# ----------------------------------------------------------------------------------------------
# mutual exclusion
# ----------------------------------------------------------------------------------------------

# A stub `git`, first on PATH, that stops the FIRST updater dead in the middle of its critical
# section and hands the test control of when it resumes. Everything after that first call runs
# the real git, so what is under test is still the real fetch and the real fast-forward.
STUB_GIT = """#!/bin/sh
if [ ! -e "$STUB_MARKER" ]; then
    : > "$STUB_MARKER"
    # Blocking write, then a blocking read. The test learns the updater is inside its critical
    # section, and decides when it leaves. No duration is involved on either side.
    printf 'inside' > "$FIFO_INSIDE"
    cat "$FIFO_GATE" >/dev/null
fi
exec %s "$@"
"""

WRAPPER = r"""#!/bin/sh
# Announce that we are about to attempt the update (a blocking FIFO write, so the test knows we
# exist), run it, then record that we finished and with what status.
printf 'started' > "$FIFO_STARTED"
sh "$UPDATE_GOLDEN" $EXTRA_ARGS >"$LOG.b.out" 2>&1
printf 'B-out rc=%s\n' "$?" >> "$LOG"
"""


def _wrapper_path(fx):
    path = os.path.join(fx.root, "second.sh")
    with open(path, "w") as fh:
        fh.write(WRAPPER)
    os.chmod(path, 0o755)
    return path


def _lock_is_held(fx):
    """True when something else holds the golden lock RIGHT NOW.

    `flock -n` either takes the lock or fails immediately. It is an observation of state, not a
    wait, so a test built on it cannot be flaky and cannot pass by being slow enough.
    """
    p = subprocess.run(["flock", "-n", fx.lock, "true"], capture_output=True)
    return p.returncode != 0


def _stub_git_dir(fx, inside, gate):
    d = os.path.join(fx.root, "stubbin")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "git")
    with open(path, "w") as fh:
        fh.write(STUB_GIT % shutil.which("git"))
    os.chmod(path, 0o755)
    return d


def _reap(proc):
    """Wait for the killed process group to be gone.

    os.killpg returns as soon as the signals are queued, so the last holder of the lock may
    outlive the call by a scheduling quantum. waitpid on the group turns that into a fact.
    """
    while True:
        try:
            if os.waitpid(-os.getpgid(proc.pid), 0)[0] == 0:
                break
        except (ChildProcessError, ProcessLookupError):
            break


def _start_blocked_updater(fx, extra_args="", new_session=False):
    """Start a real update-golden.sh and stop it inside its critical section.

    Returns (process, gate) once the updater is provably in the middle of its work: the FIFO
    read below cannot return before the stub git has run, and the stub git cannot run before the
    lock has been taken.
    """
    inside = os.path.join(fx.root, "inside.fifo")
    gate = os.path.join(fx.root, "gate.fifo")
    for f in (inside, gate):
        os.mkfifo(f)
    stubdir = _stub_git_dir(fx, inside, gate)

    env = dict(fx.env(), PATH=stubdir + os.pathsep + os.environ["PATH"],
               STUB_MARKER=os.path.join(fx.root, "stub.used"),
               FIFO_INSIDE=inside, FIFO_GATE=gate)
    args = ["sh", UPDATE_GOLDEN] + ([extra_args] if extra_args else [])
    proc = subprocess.Popen(args, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True,
                            start_new_session=new_session)
    with open(inside) as fh:
        fh.read()
    return proc, gate


def _open_gate(gate):
    with open(gate, "w") as fh:
        fh.write("go")


def test_the_lock_is_held_for_the_whole_update(fx):
    """THE detector. Delete the flock from update-golden.sh and this test fails outright."""
    fx.push_new_commit()
    assert not _lock_is_held(fx), "nothing should hold the lock before we start"

    updater, gate = _start_blocked_updater(fx)
    try:
        # The updater is stopped in the middle of its work. The lock must be ours-to-nobody.
        assert _lock_is_held(fx), \
            "the golden lock is NOT held while update-golden.sh is working"
    finally:
        _open_gate(gate)
    assert updater.wait() == 0, updater.communicate()[1]

    assert not _lock_is_held(fx), "the lock outlived the updater that took it"
    assert head(fx.golden) == head(fx.seed)


def test_the_lock_dies_with_its_holders(fx):
    """No stale-lock recovery path exists here because none is needed.

    Kill the whole process group, not just the shell. A `git` child inherits the lock fd, and
    while it lives it is still writing to golden — the lock outliving the shell in that case is
    the correct answer, not a leak. What must never happen is a lock file that survives every
    process that ever held it, because that is the case somebody has to clean up by hand.
    """
    fx.push_new_commit()
    updater, _gate = _start_blocked_updater(fx, new_session=True)
    assert _lock_is_held(fx)

    os.killpg(os.getpgid(updater.pid), signal.SIGKILL)
    updater.wait()
    _reap(updater)
    assert not _lock_is_held(fx), \
        "the lock survived every process that held it — something is not using flock"


def test_a_second_updater_waits_rather_than_running(fx):
    """The end-to-end shape: one updater inside, a second one launched, and it does not finish."""
    fx.push_new_commit()
    updater, gate = _start_blocked_updater(fx)

    started = os.path.join(fx.root, "started.fifo")
    os.mkfifo(started)
    env = dict(fx.env(), FIFO_STARTED=started, UPDATE_GOLDEN=UPDATE_GOLDEN,
               LOG=fx.log, EXTRA_ARGS="")
    second = subprocess.Popen(["sh", _wrapper_path(fx)], env=env)
    with open(started) as fh:
        fh.read()

    # The second updater is running and wants the lock. The first still holds it, and that is an
    # observation rather than an inference about how fast anything is.
    assert _lock_is_held(fx)
    assert fx.read_log() == [], "the second updater finished while the first held the lock"

    _open_gate(gate)
    assert updater.wait() == 0
    second.wait()

    log = fx.read_log()
    assert log == ["B-out rc=0"], log
    assert head(fx.golden) == head(fx.seed)


def test_locked_skips_acquisition_so_callers_do_not_deadlock(fx):
    """ffbox and 04-warmLibrary.sh hold the lock themselves and pass --locked.

    If --locked tried to take it again they would block on their own lock forever, which is the
    one bug that would take the whole box down rather than one run.
    """
    fx.push_new_commit()
    holder, gate = _start_blocked_updater(fx)
    assert _lock_is_held(fx)

    # Runs to completion while the lock is held by somebody else. Waiting for its exit here is
    # what makes this deterministic: if --locked blocked, this call would never return.
    inner = fx.update("--locked")
    assert inner.returncode == 0, inner.stderr

    _open_gate(gate)
    holder.wait()


def test_eight_concurrent_updaters_all_succeed(fx):
    """The real launch pattern at max_concurrent_runs=8: everybody wants golden at once."""
    target = fx.push_new_commit()

    procs = [subprocess.Popen(["sh", UPDATE_GOLDEN], env=fx.env(),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for _ in range(8)]
    results = [(p.wait(), p.communicate()) for p in procs]

    failed = [(rc, err) for rc, (_out, err) in results if rc != 0]
    assert not failed, f"{len(failed)} of 8 concurrent updaters failed: {failed[:2]}"
    assert head(fx.golden) == target
    assert git(fx.golden, "status", "--porcelain") == "", "golden left dirty by concurrent runs"


# ----------------------------------------------------------------------------------------------

def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        fx = Fixture()
        try:
            t(fx)
            print(f"  ok   {t.__name__}")
        except Exception:
            failures += 1
            print(f"  FAIL {t.__name__}")
            traceback.print_exc()
        finally:
            fx.cleanup()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
