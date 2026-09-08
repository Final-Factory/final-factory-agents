#!/bin/sh
# test_reap.sh — offline tests for the one decision in reap.sh that can delete a running job.
#
#   sh ffbox/runners/test_reap.sh
#
# WHY THIS EXISTS SEPARATELY FROM test_pool.sh. reap.sh is a SCRIPT, not a library: it runs
# top to bottom and cannot be sourced, so its rules cannot be called the way test_pool.sh calls
# lib/config.sh's. The first version of this test copied `owner_state` into the test file and
# asserted against the copy, which would have gone on passing if the real function were deleted.
# So this drives the real reap.sh instead, with a stub `docker` on PATH standing in for the daemon.
#
# WHAT IT COVERS AND WHERE IT STOPS. The container sweep, which is the part that removes things.
# reap.sh then lists runners from the GitHub API and exits non-zero when it cannot, which offline
# it cannot -- so everything after that point (registrations, the staging sweep) is out of reach
# here and the exit status is deliberately ignored. That is a real limit and it is the reason the
# staging-path rule is tested in test_pool.sh, where it IS a sourceable function.
#
# THE DECISION UNDER TEST. A container says who owns it, and which liveness question to ask
# depends on the answer: a slot.sh has one supervisor per container whose pid is exact, and an
# ffwatch has one daemon for all of them which restarts while they keep running. Asking the pid
# question of an ffwatch container would mark every adopted container an orphan and delete live
# jobs. design/ffbox_ci_in_ffwatch_design.txt section 4b.

set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  ok   %s\n' "$*"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL %s\n' "$*"; }

# The stub daemon. STUB_CONTAINERS is a space-separated list of
# <name>|<owner label>|<supervisor pid>|<runner id>|<state>.
mkdir -p "$TMP/bin"
cat > "$TMP/bin/docker" <<'EOF'
#!/bin/sh
case "$1" in
  # A SENTINEL NOTHING ELSE ANSWERS. The precondition below needs to know that THIS docker is on
  # PATH, not that A docker is: the real one is installed on the box that runs this test, it
  # answers `version` perfectly well, and without this the suite would quietly point reap.sh at
  # the live daemon and assert against whatever containers happened to be running.
  ffghr-test-stub) echo stub ;;
  version) exit 0 ;;
  ps)      for c in ${STUB_CONTAINERS:-}; do printf '%s\n' "${c%%|*}"; done ;;
  inspect)
    fmt=""; name=""
    while [ $# -gt 0 ]; do case "$1" in -f) fmt=$2; shift 2 ;; *) name=$1; shift ;; esac; done
    for c in ${STUB_CONTAINERS:-}; do
      IFS='|' read -r n owner pid rid state <<EOSTUB
$c
EOSTUB
      [ "$n" = "$name" ] || continue
      case "$fmt" in
        *ffghr.owner*)          printf '%s\n' "$owner" ;;
        *ffghr.supervisor.pid*) printf '%s\n' "$pid" ;;
        *ffghr.runner.id*)      printf '%s\n' "$rid" ;;
        *State.Status*)         printf '%s\n' "$state" ;;
        *)                      printf '\n' ;;
      esac
      exit 0
    done
    exit 1 ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$TMP/bin/docker"
[ -z "${TEST_BREAK_STUB:-}" ] || rm -f "$TMP/bin/docker"   # for the self-check below
PATH="$TMP/bin:$PATH"
export PATH

# Its own config, so nothing here reads the machine's. No app id, so the GitHub call fails and
# reap.sh stops after the part being tested.
FFGITHUBRUNNERS_CONFIG_DIR="$TMP/config"; export FFGITHUBRUNNERS_CONFIG_DIR
FFBOX_CONFIG_DIR="$TMP/config";           export FFBOX_CONFIG_DIR
mkdir -p "$FFBOX_CONFIG_DIR"
printf '{ "max_concurrent_runs": 6, "githubrunner": { "cache_dir": "" } }\n' \
    > "$FFBOX_CONFIG_DIR/config.json"

# PID 1 IS THE LIVE PID AND IT IS NOT A slot.sh. `supervisor_alive` reads /proc/<pid>/cmdline and
# greps for slot.sh, so init is a pid that exists and fails the test -- which is exactly the
# "supervisor died, its pid got recycled by something else" case. For a pid that IS a live
# slot.sh, the test uses this shell's own pid and a cmdline it cannot have, so those cases assert
# the ORPHAN direction; the live direction is covered by the ffwatch cases, where liveness is a
# process search this test can satisfy honestly.
DEAD_PID=4294967295          # above /proc/sys/kernel/pid_max: cannot exist
RECYCLED_PID=1               # exists, is not a slot.sh

# EVERY ASSERTION BELOW READS reap.sh's STDOUT, so anything that stops it producing any makes
# them all fail at once and none of them say why. That happened once on 2026-09-08 -- one red run
# in a batch, five green ones after it, no output kept and no cause found. A test that can fail
# for a reason it does not name is a test somebody will eventually decide to ignore.
#
# So the output is checked for emptiness at the point it is produced, and an empty answer is
# reported as what it is: the script did not run, rather than nine wrong decisions.
reap() {   # STUB_CONTAINERS is set by the caller
    _out=$(STUB_CONTAINERS="$1" sh "$HERE/reap.sh" --dry-run 2>"$TMP/reap.err" || true)
    if [ -z "$_out" ]; then
        bad "reap.sh produced no output at all -- it did not get as far as the container sweep."
        printf '       its stderr was: %s\n' "$(head -3 "$TMP/reap.err" | tr '\n' ' ')"
        printf '       (this is an environment problem, not a decision this test is about)\n'
    fi
    printf '%s\n' "$_out"
    unset _out
}

says() {   # <output> <substring> <what>
    case "$1" in
        *"$2"*) ok "$3" ;;
        *)      bad "$3 (looked for '$2')" ;;
    esac
}
denies() {
    case "$1" in
        *"$2"*) bad "$3 (should not have said '$2')" ;;
        *)      ok "$3" ;;
    esac
}

# THE ONE PRECONDITION reap.sh HAS, checked before anything is asserted. It exits 1 the moment it
# cannot reach a daemon, before the sweep this file tests, so a stub that is not on PATH turns
# every case below into a failure about ownership when the truth is that nothing ran.
if [ "$(docker ffghr-test-stub 2>/dev/null)" != stub ]; then
    printf '  FAIL the stub docker is not first on PATH.\n'
    printf '       Every case below would run reap.sh against the REAL daemon and assert about\n'
    printf '       whatever containers happen to be running, which is not what any of them mean.\n'
    printf '       (--dry-run means nothing would have been destroyed, but nothing would have\n'
    printf '       been tested either.)\n'
    exit 1
fi

printf '\nwho owns a container, and how the reaper asks\n'

out=$(reap "ffghr-x-1-aa|slot.sh|$DEAD_PID|101|running")
says "$out" "would remove orphaned container ffghr-x-1-aa" \
     "a slot.sh container whose pid is gone is an orphan"

out=$(reap "ffghr-x-2-bb|slot.sh|$RECYCLED_PID|102|running")
says "$out" "would remove orphaned container ffghr-x-2-bb" \
     "and so is one whose pid exists but is not a slot.sh"

# THE CASE THAT MATTERS MOST. An ffwatch container must never be judged by a pid: the daemon
# restarts on every update while its containers keep running, so a pid test would delete live
# jobs on every deploy. The pid below is deliberately dead and deliberately ignored.
#
# A STUB DAEMON, RATHER THAN TRUSTING THE MACHINE. `ffwatch_alive` greps every /proc cmdline for
# ffwatch.py, which is machine-global by design -- the whole point is that it does not care WHICH
# daemon. On the build server the real one is always running, so this case would pass without
# testing anything; a laptop would fail it for the opposite reason. Starting a process whose
# cmdline contains ffwatch.py makes the answer the test's own.
#
# THE ORPHAN DIRECTION CANNOT BE ISOLATED HERE and that is worth writing down rather than
# quietly omitting: proving "no daemon is running" means no ffwatch anywhere on the box, which a
# test must not arrange on a machine that is serving Discord. So the negative is covered by the
# unrecognised-owner case below, which reaches the same branch by a different route.
# `exec`, so this script's pid IS the sleep and killing it kills the sleep. Without it the trap
# killed a shell whose `sleep` child outlived it, and the suite took two minutes to return for no
# reason. 60s is far longer than the assertions below need and short enough to be harmless if a
# run is interrupted before the trap fires.
cat > "$TMP/bin/ffwatch.py" <<'EOF'
#!/bin/sh
exec sleep 60
EOF
chmod +x "$TMP/bin/ffwatch.py"
"$TMP/bin/ffwatch.py" & STUB_DAEMON=$!
trap 'kill "$STUB_DAEMON" 2>/dev/null || true; rm -rf "$TMP"' EXIT INT TERM

out=$(reap "ffghr-x-3-cc|ffwatch|$DEAD_PID|103|running")
denies "$out" "would remove orphaned container ffghr-x-3-cc" \
       "an ffwatch container is NOT orphaned by a dead pid"
says "$out" "belongs to a live ffwatch" \
     "it is live because a daemon is running, which is the only question worth asking"

# An owner this reaper has never heard of is left alone. This happens on every box during an
# upgrade, in the window where a newer supervisor writes a name the older reaper cannot read, and
# it is the one case where deleting would be worst.
out=$(reap "ffghr-x-4-dd|something-newer|$DEAD_PID|104|running")
denies "$out" "would remove orphaned container ffghr-x-4-dd" \
       "an unrecognised owner is never an orphan"
says "$out" "no owner this reaper recognises" \
     "and the reaper says so rather than staying silent about it"

# A container from before the owner label falls back to the pid, which is what it carries.
out=$(reap "ffghr-x-5-ee||$DEAD_PID|105|running")
says "$out" "would remove orphaned container ffghr-x-5-ee" \
     "a pre-2026-09-08 container is still judged by its pid"

# And one with neither label is left alone and reported, which is this file's oldest rule:
# what cannot be explained is sometimes a running job.
out=$(reap "ffghr-x-6-ff|||106|running")
denies "$out" "would remove orphaned container ffghr-x-6-ff" \
       "a container with no labels at all is left alone"

# The registration goes with the container, rather than waiting for GitHub to mark it offline.
out=$(reap "ffghr-x-7-gg|slot.sh|$DEAD_PID|107|running")
says "$out" "would delete its registration 107" \
     "an orphan's registration is deleted with it"

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
