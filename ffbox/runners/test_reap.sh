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
# <name>|<owner label>|<runner id>|<state>.
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
      IFS='|' read -r n owner rid state <<EOSTUB
$c
EOSTUB
      [ "$n" = "$name" ] || continue
      case "$fmt" in
        *ffghr.owner*)          printf '%s\n' "$owner" ;;
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

# A STUB DAEMON, RATHER THAN TRUSTING THE MACHINE. `ffwatch_alive` greps every /proc cmdline for
# ffwatch.py, which is machine-global by design -- the point is that it does not care WHICH
# daemon. On the build server the real one is always running, so the live case would pass without
# testing anything; a laptop would fail it for the opposite reason. Starting a process whose
# cmdline contains ffwatch.py makes the answer this test's own.
#
# `exec`, so this script's pid IS the sleep and the trap can kill it. And >/dev/null 2>&1, because
# a background child inherits this shell's stdout and every `out=$(reap ...)` below reads until
# every writer closes it -- a stub holding the pipe open hangs the first one. Both cost a run.
cat > "$TMP/bin/ffwatch.py" <<'EOF'
#!/bin/sh
exec sleep 60
EOF
chmod +x "$TMP/bin/ffwatch.py"
"$TMP/bin/ffwatch.py" >/dev/null 2>&1 & STUB_DAEMON=$!
trap 'kill "$STUB_DAEMON" 2>/dev/null || true; rm -rf "$TMP"' EXIT INT TERM

out=$(reap "ffghr-x-1-aa|ffwatch|103|running")
denies "$out" "would remove orphaned container ffghr-x-1-aa" \
       "a container owned by a live daemon is never removed"
says "$out" "belongs to a live ffwatch" \
     "and the reaper says which owner it recognised"

# An owner this reaper has never heard of is left alone -- including a container from before the
# owner label, and one from a newer daemon writing a name this version cannot read. That happens
# on every box during an upgrade, and it is the case where deleting would be worst.
out=$(reap "ffghr-x-2-bb|something-newer|104|running")
denies "$out" "would remove orphaned container ffghr-x-2-bb" \
       "an unrecognised owner is never an orphan"
says "$out" "no owner this reaper recognises" \
     "and the reaper says so rather than staying silent about it"

out=$(reap "ffghr-x-3-cc||105|running")
denies "$out" "would remove orphaned container ffghr-x-3-cc" \
       "a container with no owner label at all is left alone"

printf '\nan absent daemon is not an orphan until the SECOND sweep sees it\n'

# THE CASE THAT WOULD DELETE RUNNING JOBS. ffwatch restarts on every update -- a median of six
# seconds, measured over 227 of them -- and its containers keep running through it. This sweep
# runs every fifteen minutes. A bare "is a daemon running" test that landed inside that window
# would call every CI container an orphan and remove two-hour Unity jobs. So it takes two
# sightings a sweep apart.
#
# DRIVEN THROUGH THE REAL FUNCTION WITH ONE DEPENDENCY STUBBED, rather than end to end, and the
# limit is honest: `ffwatch_alive` scans every /proc cmdline, so on the machine this test runs on
# -- a build server with a live ffwatch -- the absent branch is simply unreachable from outside.
# Any seam that made it reachable would be a switch that turns "leave it alone" into "delete it",
# which is not a switch worth having in a reaper. So daemon_absent_twice is extracted and given a
# ffwatch_alive it controls; everything else about it is the shipped code.
awk '/^daemon_absent_twice\(\)/,/^}$/' "$HERE/reap.sh" > "$TMP/grace.sh"
grep -q '^daemon_absent_twice()' "$TMP/grace.sh" || {
    printf '  FAIL could not extract daemon_absent_twice; nothing below tests anything\n'; exit 1
}

grace() {   # <alive: yes|no>  -> prints the verdict
    cat > "$TMP/grace-run.sh" <<EOF
FFGHR_NO_DAEMON_STAMP=$TMP/no-daemon
skip() { printf 'SKIP %s\n' "\$*"; }
ffwatch_alive() { [ "$1" = yes ]; }
. $TMP/grace.sh
if daemon_absent_twice; then echo ORPHAN; else echo KEEP; fi
EOF
    sh "$TMP/grace-run.sh"
}

rm -f "$TMP/no-daemon"
case "$(grace no)" in
    *KEEP*) ok "the FIRST sweep with no daemon keeps the containers" ;;
    *)      bad "the first sweep with no daemon must not orphan anything" ;;
esac
[ -e "$TMP/no-daemon" ] && ok "and leaves a note for the next sweep" \
                        || bad "the first sweep must record that it saw no daemon"
case "$(grace no)" in
    *ORPHAN*) ok "the SECOND sweep, still with no daemon, orphans them" ;;
    *)        bad "two sweeps with no daemon must orphan" ;;
esac

# AND THE NOTE IS TORN UP THE MOMENT THE DAEMON IS BACK, so a restart that spans one sweep cannot
# leave suspicion lying around to mature into a deletion on the next.
case "$(grace yes)" in
    *KEEP*) ok "a daemon that came back is live again" ;;
    *)      bad "a live daemon must never orphan" ;;
esac
[ -e "$TMP/no-daemon" ] && bad "the note must be torn up once the daemon is seen" \
                        || ok "and the note is torn up, so the count starts over"

# The whole point, stated as one case: a restart cannot span two sweeps.
rm -f "$TMP/no-daemon"
grace no >/dev/null      # sweep 1: daemon down (an update is running)
grace yes >/dev/null     # sweep 2: it came back
case "$(grace no)" in
    *KEEP*) ok "down, up, down again is three sweeps and still no deletion" ;;
    *)      bad "an intermittent daemon must not accumulate towards a deletion" ;;
esac

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
