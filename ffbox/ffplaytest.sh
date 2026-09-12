#!/usr/bin/env bash
#
# ffplaytest — one Unity PLAY-MODE session against the workspace, reported as JSON.
#
# The sibling of ffverify, and deliberately the same shape: mounted into the container at
# /usr/local/bin/ffplaytest, invoked BY NAME, writes one JSON report per invocation under its own
# --out directory. ffverify answers "does it compile and do the EditMode tests pass"; this answers
# "does it still do the thing when the game is actually running".
#
# WHY IT EXISTS AS A SCRIPT. Not because the agent is forbidden to run Unity — it is not, and has
# not been since the lane system went away on 2026-08-25 (the allow list is bare `Bash`; see
# ffwatch.py's CAPABILITIES). It exists because a play-mode session has three ways to poison the
# NEXT run, and every one of them is mechanical:
#
#   1. A LEFTOVER .ff-local-automation.json auto-starts play mode on the next editor boot. The
#      harness's own ffverify runs in this same workspace after the agent exits, and it is the run
#      that decides whether a pull request opens. This script writes that file, and deletes it on
#      EVERY exit path including SIGTERM (see cleanup below).
#   2. A PER-RUN LABEL or nothing. Session artifacts land in
#      <persistentDataPath>/PlaytestSessions/<Label>/, so two runs sharing a label read each
#      other's journal. The label is per invocation and unique by default.
#   3. THE SHARED RESULTS FILE, which is ffverify's rule 1 and applies here unchanged: the
#      Performance Testing package writes TestResults.xml and PerformanceTestResults.json into
#      $HOME/.config/unity3d/Never Games/finalfactory/ on every run, a path every copy of the
#      project shares. NOTHING HERE READS IT. What this reads is the session journal, which is
#      label-scoped and therefore ours.
#
# WHAT IT CANNOT TELL YOU, and this is not a detail. There is no GPU in this container
# (/dev/dri does not exist), so rendering is llvmpipe software GL under Xvfb. FUNCTIONAL repro is
# sound: an op that gets dropped, a null that throws, a state machine that ends up wrong. FRAME
# TIMING IS WORTHLESS — "one frame or three on a 4070" does not survive the trip, and
# `ffauto:perf.sample` numbers taken here say more about llvmpipe than about the game. Do
# perf work on a real machine.
#
# WHICH BASE REFS THIS WORKS ON. The automation harness (.ff-local-automation.json, the `ffauto`
# command runner, PlaytestSessions/) lives on origin/develop and branches off it. It is NOT on
# master, which is the default base for a run. On a master-based workspace this script exits 3
# and says so rather than launching an editor that would ignore the config it was given.
#
# THE SOLO SHAPE, and why the work goes in PreConnectCommand. A host waits for
# TargetClientCount clients and the count is clamped to a minimum of 1, so a solo session ALWAYS
# waits for a peer that never arrives (LocalMultiplayerAutomationBootstrap, 900s
# HostPeerConnectTimeoutSeconds). PostReadyCommand runs POST-join and would therefore never run.
# PreConnectCommand runs before the wait, which is why the proven solo recipes
# (massdriver-visual-e2e, the run_*_audit.sh family) put their chain there and why this does too.
# Once the chain reports complete we stop the editor ourselves instead of paying out that
# 15-minute wait.
#
# No `set -e`: a session that ends badly is an ordinary, reportable outcome, and dying on it would
# leave no JSON for anyone to read. Errors are explicit.
set -uo pipefail

PROJECT=${FFPLAYTEST_PROJECT:-${FFBOX_WORKSPACE:-/opt/actions-runner/_work/FinalFactory/FinalFactory}}
OUT=${FFPLAYTEST_OUT:-${HOME:-/tmp}/ffplaytest}
UNITY=${FFPLAYTEST_UNITY:-unity-editor}
TAG=
LABEL=
CHAIN=
SAVE=
SEED=automation-smoke
FLATMAP=true
# The ceiling on the whole session, not on the chain. Boot + domain reload + map gen is minutes
# before any command runs, so this is generous on purpose; the normal exit is the chain finishing.
TIMEOUT=${FFPLAYTEST_TIMEOUT:-900}
# How long the sim keeps running after the chain reports complete, so effects the chain kicked off
# (a bot moving, a belt filling) are in the journal rather than cut off mid-flight.
SETTLE=${FFPLAYTEST_SETTLE:-10}
FORCE=0

# Same as ffverify: this launches an editor, so it makes sure there is a licence. Usually the pool
# already took the seat and this logs one line and returns.
if [ -r /ffbox/unity-license.sh ] && ! declare -F ensure_unity_license >/dev/null 2>&1; then
    . /ffbox/unity-license.sh
fi

usage() {
    cat <<'EOF'
Usage: ffplaytest --chain 'ffauto:...;ffauto:...' [options]

Runs ONE play-mode session against the workspace and writes <out>/playtest-<tag>.json:

  ran, chain_complete, entered_play, errors, events, session_dir, journal_path, evidence

Options:
  --chain CHAIN     the ffauto chain to run pre-join, ';'-separated (this is the playtest)
  --save NAME       load this save instead of generating a map (implies --no-flatmap)
  --seed SEED       map seed when generating (default: automation-smoke)
  --flatmap         empty deterministic grid, no terrain/enemies (default)
  --no-flatmap      generate a real map from --seed
  --label LABEL     session label; default is the tag, and it scopes the artifacts
  --out DIR         where the report, log and copied journal go
  --tag TAG         per-invocation tag (default: timestamp-pid)
  --project DIR     the Unity project (default: the run's workspace)
  --timeout SECS    ceiling on the whole session (default: 900)
  --settle SECS     how long to keep simulating after the chain completes (default: 10)
  --force           write the config even though one is already there (see the warning)

Exit: 0 the chain ran to completion with no command errors, 1 it ran and something was wrong,
      2 usage/preflight, 3 this workspace has no automation harness (a master-based run).

FRAME TIMING FROM THIS CONTAINER IS MEANINGLESS — software GL, no GPU. Functional repro only.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --chain)      CHAIN=${2?--chain needs a command chain}; shift 2 ;;
        --save)       SAVE=${2:?--save needs a save name}; FLATMAP=false; shift 2 ;;
        --seed)       SEED=${2:?--seed needs a seed}; shift 2 ;;
        --flatmap)    FLATMAP=true; shift ;;
        --no-flatmap) FLATMAP=false; shift ;;
        --label)      LABEL=${2:?--label needs a name}; shift 2 ;;
        --out)        OUT=${2:?--out needs a directory}; shift 2 ;;
        --tag)        TAG=${2:?--tag needs a name}; shift 2 ;;
        --project)    PROJECT=${2:?--project needs a directory}; shift 2 ;;
        --timeout)    TIMEOUT=${2:?--timeout needs seconds}; shift 2 ;;
        --settle)     SETTLE=${2:?--settle needs seconds}; shift 2 ;;
        --force)      FORCE=1; shift ;;
        -h|--help)    usage; exit 0 ;;
        *)            echo "ffplaytest: unknown option $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [ -z "$TAG" ]; then
    TAG=$(date +%Y%m%d-%H%M%S)-$$
fi
case "$TAG" in
    *[!A-Za-z0-9._-]*) echo "ffplaytest: --tag must match [A-Za-z0-9._-]+" >&2; exit 2 ;;
esac
if [ -z "$LABEL" ]; then
    LABEL="ffplaytest-$TAG"
fi
case "$LABEL" in
    *[!A-Za-z0-9._-]*) echo "ffplaytest: --label must match [A-Za-z0-9._-]+" >&2; exit 2 ;;
esac
case "$TIMEOUT$SETTLE" in
    *[!0-9]*) echo "ffplaytest: --timeout and --settle take seconds" >&2; exit 2 ;;
esac
if [ -z "$CHAIN" ]; then
    echo "ffplaytest: --chain is required — a session with no commands proves nothing" >&2
    usage >&2
    exit 2
fi
case "$CHAIN" in
    *'"'*|*$'\n'*) echo "ffplaytest: --chain cannot contain quotes or newlines" >&2; exit 2 ;;
esac

if [ ! -d "$PROJECT/Assets" ]; then
    echo "ffplaytest: $PROJECT does not look like a Unity project" >&2
    exit 2
fi

# THE BASE-REF GATE. The harness is on develop, not on master, and an editor handed a config it
# has no code to read boots, ignores it, and sits there until the timeout kills it — minutes spent
# to learn nothing. Check the source instead.
BOOTSTRAP=$PROJECT/Assets/Scripts/Behaviours/Multiplayer/LocalMultiplayerAutomationBootstrap.cs
if [ ! -f "$BOOTSTRAP" ]; then
    echo "ffplaytest: this workspace has no automation harness" >&2
    echo "  missing: $BOOTSTRAP" >&2
    echo "  It lives on origin/develop and branches off it, NOT on master (the default base)." >&2
    echo "  A play-mode repro needs a develop-based run; ffverify still works here." >&2
    exit 3
fi

CONFIG=$PROJECT/.ff-local-automation.json
STATUS=$PROJECT/.ff-local-automation-status.json
# REFUSING IS THE RIGHT ANSWER. A config already sitting there is either a session in flight or
# the wreckage of one, and overwriting it makes one of two runs report the other's world. It is
# also gitignored on develop, so it is never something the run is supposed to be editing.
if [ -e "$CONFIG" ] && [ "$FORCE" != 1 ]; then
    echo "ffplaytest: $CONFIG already exists — another session is live or left it behind." >&2
    echo "  Inspect it, then delete it, or pass --force to overwrite." >&2
    exit 2
fi

mkdir -p "$OUT" || { echo "ffplaytest: cannot create $OUT" >&2; exit 2; }
# The host has to be able to delete this afterwards and cannot unless the WRITER opens the mode --
# the full argument is in ffverify.sh, and it cost three leaked spools to learn.
chmod g+w "$OUT" 2>/dev/null || :
LOG="$OUT/playtest-$TAG.log"
JSON="$OUT/playtest-$TAG.json"
JOURNAL_COPY="$OUT/journal-$TAG.jsonl"
SESSION_COPY="$OUT/session-$TAG.json"
rm -f "$LOG" "$JSON" "$JOURNAL_COPY" "$SESSION_COPY"

# Application.persistentDataPath on Linux. Confirmed against the image rather than assumed:
# `.config/unity3d` is a literal in /opt/unity/Editor/Unity and XDG_CONFIG_HOME appears nowhere in
# that binary, so the path really is $HOME-relative. This is also where the shared results file we
# never read lives.
PDP=${FFPLAYTEST_PDP:-${HOME:-/root}/.config/unity3d/Never Games/finalfactory}
SESSION_DIR=$PDP/PlaytestSessions/$LABEL

UNITY_PID=
UNITY_PGID=

# THE GROUP FIRST, then the bare pid as a fallback for a shell with no setsid. `kill -- -PGID`
# signals every process in the group: the wrapper, its Xvfb and the editor itself.
stop_editor() {   # <signal>
    [ -n "$UNITY_PID" ] || return 0
    if [ -n "$UNITY_PGID" ]; then
        kill "-$1" -- "-$UNITY_PGID" 2>/dev/null && return 0
    fi
    kill "-$1" "$UNITY_PID" 2>/dev/null
}

editor_alive() {
    [ -n "$UNITY_PID" ] || return 1
    kill -0 "$UNITY_PID" 2>/dev/null
}

cleanup() {
    # EVERY EXIT PATH, and the reason this script exists. A config left behind auto-plays on the
    # next editor boot, and the next editor boot in this container is the harness's own ffverify --
    # the run that decides whether a pull request opens.
    rm -f "$CONFIG" "$STATUS"
    if editor_alive; then
        stop_editor TERM
    fi
}
trap cleanup EXIT INT TERM

python3 - "$CONFIG" "$LABEL" "$SEED" "$FLATMAP" "$SAVE" "$CHAIN" <<'PYEOF'
"""Write the automation config.

Field names are LocalMultiplayerAutomationSessionConfig's, and the values are the solo shape the
proven recipes use: a host, no determinism report (which would want a peer and a policy), the work
in PreConnectCommand because a solo host never reaches the post-join chain.
"""
import json
import sys

config, label, seed, flatmap, save, chain = sys.argv[1:7]
cfg = {
    "Enabled": True,
    "AutoStartInEditor": True,
    "ForceOutOfGameStartMode": True,
    "Role": "Host",
    "Host": "127.0.0.1",
    "Port": 7777,
    "Seed": seed,
    "FlatMap": flatmap == "true",
    # OFF, AND THE TWO GO TOGETHER: a report wants a peer and, since feature 045, an identity
    # tuple; asking for one from a solo session buys "Determinism report publication failed".
    "EnableDeterminismAudit": False,
    "WriteReport": False,
    "Label": label,
    # Quit when the session ends so the container is not holding an editor open, and leave play
    # mode first so the editor is not torn down mid-frame.
    "AutoQuit": True,
    "ExitPlayModeOnComplete": True,
    # The minimum the bootstrap clamps to. No client will come; the chain runs before the wait and
    # this script stops the editor once it completes.
    "TargetClientCount": 1,
    "PostConnectDelayMs": 1500,
    "PreConnectCommand": chain,
    # Reject-and-continue (the 020 default): one malformed command journals a commandError and the
    # rest of the chain still runs, which is what makes a partial result readable.
    "StrictCommands": False,
}
if save:
    cfg["SaveName"] = save
    cfg["FlatMap"] = False
with open(config, "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, indent=2)
PYEOF
if [ ! -f "$CONFIG" ]; then
    echo "ffplaytest: could not write $CONFIG" >&2
    exit 2
fi

if declare -F ensure_unity_license >/dev/null 2>&1; then
    ensure_unity_license
fi

STARTED=$(date +%s)
# No -runTests and no -executeMethod: the editor's own 1s poller reads the config and enters play
# mode. The image's unity-editor wrapper supplies -batchmode and wraps the editor in xvfb-run, so
# this is a headless editor with a software GL context -- which renders, slowly, and is why
# functional repro works here and timing does not.
#
# IN ITS OWN PROCESS GROUP, and that is not decoration. `unity-editor` in this image is a WRAPPER:
# it execs xvfb-run, which starts an Xvfb and the editor as its own children. SIGTERM to the
# wrapper's pid kills the wrapper and reparents the editor to init -- measured here on 2026-09-11
# with a stub, which left its child running after a clean-looking shutdown. A leaked editor holds
# the LICENCE SEAT the next run needs, and a leaked Xvfb holds a display.
#
# Killing a process GROUP WE CREATED is not the "find stray Unity processes" path design section 14
# forbids: we are not guessing which editor is ours, we made this one and we know its group.
if command -v setsid >/dev/null 2>&1; then
    setsid "$UNITY" -projectPath "$PROJECT" -logFile /dev/stdout >"$LOG" 2>&1 &
    UNITY_PID=$!
    # setsid makes the child a session and group leader, so its pgid IS its pid.
    UNITY_PGID=$UNITY_PID
else
    "$UNITY" -projectPath "$PROJECT" -logFile /dev/stdout >"$LOG" 2>&1 &
    UNITY_PID=$!
    UNITY_PGID=
fi

# WATCHING THE LOG IS THE SUPPORTED CHANNEL, not a trick: WriteStatus logs every phase as
# `[LocalMultiplayerAutomation] status <phase>: <details>` precisely so a harness script can gate
# on it (the built-player audit driver gates the client launch on this same line).
DEADLINE=$(( STARTED + TIMEOUT ))
CHAIN_DONE=0
OUTCOME=timeout
while :; do
    if ! editor_alive; then
        OUTCOME=exited
        break
    fi
    if [ "$(date +%s)" -ge "$DEADLINE" ]; then
        OUTCOME=timeout
        break
    fi
    if [ "$CHAIN_DONE" = 0 ] && grep -qF "status pre-connect-command-complete" "$LOG" 2>/dev/null
    then
        CHAIN_DONE=1
        # The chain is done and the host is about to start its 15-minute wait for a peer that does
        # not exist. Let the sim run a little for the consequences, then stop it ourselves.
        sleep "$SETTLE"
        OUTCOME=chain-complete
        break
    fi
    if grep -qF "status session-ended" "$LOG" 2>/dev/null; then
        OUTCOME=session-ended
        break
    fi
    sleep 2
done

if editor_alive; then
    # SIGTERM, then insist. A -batchmode editor under xvfb-run does not always take the first one,
    # and an editor left running holds the licence seat the next run needs.
    stop_editor TERM
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        editor_alive || break
        sleep 1
    done
    stop_editor KILL
fi
wait "$UNITY_PID" 2>/dev/null
UNITY_RC=$?
ELAPSED=$(( $(date +%s) - STARTED ))

# The journal is the repro (spec 020 D6), and it is label-scoped, so copying it out of
# persistentDataPath is ours to copy and nobody else's to clobber.
if [ -f "$SESSION_DIR/journal.jsonl" ]; then
    cp "$SESSION_DIR/journal.jsonl" "$JOURNAL_COPY" 2>/dev/null || :
fi
if [ -f "$SESSION_DIR/session.json" ]; then
    cp "$SESSION_DIR/session.json" "$SESSION_COPY" 2>/dev/null || :
fi

python3 - "$LOG" "$JSON" "$JOURNAL_COPY" "$SESSION_COPY" "$SESSION_DIR" \
            "$OUTCOME" "$UNITY_RC" "$ELAPSED" "$LABEL" "$CHAIN" <<'PYEOF'
"""Turn one play-mode session into a report somebody can act on.

`chain_complete` is the fact that matters: the editor exiting 0 says nothing about whether the
commands ran, and a session can end for reasons that have nothing to do with the game being wrong
(the peer wait, our own timeout). Command errors are journaled rather than fatal since 020, so
they have to be read out of the journal explicitly.
"""
import json
import re
import sys

(log_path, json_path, journal_path, session_path, session_dir,
 outcome, rc, elapsed, label, chain) = sys.argv[1:11]
rc, elapsed = int(rc), int(elapsed)

try:
    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
        log = fh.read()
except OSError:
    log = ""

phases = re.findall(r"\[LocalMultiplayerAutomation\] status ([a-z0-9-]+): ?(.*)", log)
entered_play = bool(re.search(r"\[LocalMultiplayerAutomation\] status "
                              r"(?:host-listening|pre-connect-command-start|player-ready)", log))
chain_complete = any(p == "pre-connect-command-complete" for p, _ in phases)

events, command_errors = [], []
try:
    with open(journal_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            events.append(ev)
            kind = ev.get("event") or ev.get("kind") or ""
            if "error" in str(kind).lower():
                command_errors.append(json.dumps(ev)[:300])
except OSError:
    pass

# Unity's own failures, which are not journaled anywhere: a compile break stops the editor before
# the poller ever runs, and an exception in play mode is the bug half the time.
engine_errors = []
seen = set()
for line in re.findall(r"^.*(?:error CS\d+|Compilation failed|error: Burst|NullReferenceException"
                       r"|Unhandled log message: '\[Error\]).*$", log, re.MULTILINE):
    line = line.strip()[:300]
    if line not in seen:
        seen.add(line)
        engine_errors.append(line)

evidence = ["outcome %s after %ds (unity exit %d)" % (outcome, elapsed, rc),
            "chain: %s" % chain[:400]]
if phases:
    evidence.append("phases: " + " -> ".join(p for p, _ in phases[:20]))
else:
    evidence.append("NO automation phase reached — the config was never read. "
                    "On a master-based workspace that is expected; ffplaytest should have "
                    "refused earlier, so this is worth reporting.")
evidence.append("journal: %d events at %s" % (len(events), journal_path or session_dir))
evidence += command_errors[:10]
if engine_errors:
    evidence.append("engine errors:")
    evidence += engine_errors[:20]
if not chain_complete:
    evidence.append("log tail:")
    evidence += [ln for ln in log.strip().splitlines()[-15:]]

report = {
    "ran": bool(phases) or bool(engine_errors),
    "chain_complete": chain_complete,
    "entered_play": entered_play,
    "outcome": outcome,
    "label": label,
    "events": len(events),
    "command_errors": "\n".join(command_errors[:50]) or None,
    "engine_errors": "\n".join(engine_errors[:50]) or None,
    "journal_path": journal_path,
    "session_path": session_path,
    "session_dir": session_dir,
    "log_path": log_path,
    "exit_code": rc,
    "secs": elapsed,
    # Said in the report itself, because a number read off a report outlives the README that
    # explained it.
    "timing_valid": False,
    "timing_note": "software GL under Xvfb, no GPU in this container: frame timings are "
                   "meaningless. Functional behaviour only.",
    "evidence": "\n".join(evidence)[:8000],
}
with open(json_path, "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2, ensure_ascii=False)

print("ffplaytest: chain_complete=%s events=%d errors=%d (%s)"
      % (chain_complete, len(events),
         len(command_errors) + len(engine_errors), json_path))
sys.exit(0 if chain_complete and not command_errors and not engine_errors else 1)
PYEOF
RC=$?
# cleanup() runs on EXIT and takes the config with it.
exit $RC
