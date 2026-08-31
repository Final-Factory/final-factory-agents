#!/usr/bin/env bash
#
# ffverify — one Unity batchmode EditMode run against the workspace, reported as JSON.
#
# Mounted into the container at /usr/local/bin/ffverify and invoked BY NAME, the same way the
# ffdiscord shim is (design section 11). Two callers, deliberately sharing one implementation:
#
#   the harness   discord-task.sh runs it AFTER the agent process has exited, into
#                 /ffbox/out/verification. That result is the one ffwatch records in the
#                 `verification` table, and the agent has no way to write it (design section 14).
#   the agent     a fix/dev lane may run `ffverify` itself to check its own work before it
#                 finishes. It is the ONLY Unity entry point on the lane's Bash allow list, which
#                 is why this script exists as a script rather than as a line of the task: with
#                 `Bash(unity-editor *)` allowed instead, an agent could pass its own
#                 -testResults (or -executeMethod anything) and walk straight into rule 1 below.
#
# TWO RULES FROM DESIGN SECTION 14, NEITHER NEGOTIABLE:
#
#   1. NEVER read Unity's shared results file. The Performance Testing package
#      (com.unity.test-framework.performance, a transitive dependency of com.unity.entities that
#      cannot be removed) writes TestResults.xml and PerformanceTestResults.json into
#      Application.persistentDataPath on EVERY run — see its Editor/PerformanceTestRunSaver.cs.
#      That path is derived from companyName/productName and is shared by every copy of the
#      project, so whichever copy ran last clobbers it.
#
#      The game repo's CLAUDE.md names the Windows form,
#      `…/AppData/LocalLow/Never Games/finalfactory/TestResults.xml`. It does NOT translate: on
#      Linux Application.persistentDataPath is `$HOME/.config/unity3d/<company>/<product>`, so in
#      this container the file to never read is
#
#          /home/ffbox/.config/unity3d/Never Games/finalfactory/TestResults.xml
#
#      Confirmed against the image rather than assumed: `.config/unity3d` is a literal string in
#      /opt/unity/Editor/Unity, and XDG_CONFIG_HOME appears nowhere in that binary, so the editor
#      does not honour it and the path really is $HOME-relative. ProjectSettings.asset gives
#      companyName "Never Games" and productName "finalfactory".
#
#      So: -testResults is ALWAYS passed explicitly, always under our own --out directory, and
#      always tagged per invocation. We read only that file. The package still scribbles on the
#      shared one; we just never look at it.
#
#   2. Only ever destroy containers we named. Nothing here kills anything: this script runs
#      INSIDE the container that ffbox named `ffbox-<run_id>`, and stopping it is ffbox's job,
#      addressed by that exact name. There is deliberately no "find stray Unity processes" path.
#
# No `set -e`: a non-zero Unity exit is an ordinary, reportable outcome here (2 means tests
# failed), and dying on it would leave no JSON for the harness to record. Errors are explicit.
set -uo pipefail

PROJECT=${FFVERIFY_PROJECT:-${FFBOX_WORKSPACE:-/workspace}}
OUT=${FFVERIFY_OUT:-${HOME:-/tmp}/ffverify}
TAG=
# The fast EditMode suite, matching the "run FFEditorTests by default" rule in the game repo's
# CLAUDE.md. Unity's command-line test runner takes a SEMICOLON-separated list here; setting it
# empty runs every EditMode assembly, which is the slow suite and not what a turn should pay for.
ASSEMBLIES=${FFVERIFY_ASSEMBLIES-FFEditorTests}
UNITY=${FFVERIFY_UNITY:-unity-editor}

# THIS SCRIPT LAUNCHES THE EDITOR, SO THIS SCRIPT GETS THE LICENCE. discord-task.sh used to
# acquire one at the top of every run whether or not anything Unity-shaped happened, which made
# a question that changed no files pay two editor launches — one to activate, one for the trap
# to return — after the agent had already answered.
#
# Sourcing unity-license.sh installs its own EXIT trap, so an agent-invoked ffverify returns
# what it took, and a run that never calls this never holds a seat at all. ensure_unity_license
# is a no-op when the environment already has what it needs, so the harness call after the
# agent exits costs nothing extra.
if [ -r /ffbox/unity-license.sh ] && ! declare -F ensure_unity_license >/dev/null 2>&1; then
    . /ffbox/unity-license.sh
fi

usage() {
    cat <<'EOF'
Usage: ffverify [--out DIR] [--tag TAG] [--project DIR] [--assemblies "A;B"]

Runs `unity-editor -runTests -testPlatform EditMode` against the workspace with a
per-invocation -testResults path, then writes <out>/verification-<tag>.json:

  ran, compiled, compile_errors, tests_run, tests_passed, tests_failed, results_path, evidence

Exit code: 0 when the suite ran and every test passed, 1 otherwise. The JSON is written either
way — a caller that reads the exit code alone learns less than one that reads the file.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --out)        OUT=${2:?--out needs a directory}; shift 2 ;;
        --tag)        TAG=${2:?--tag needs a name}; shift 2 ;;
        --project)    PROJECT=${2:?--project needs a directory}; shift 2 ;;
        --assemblies) ASSEMBLIES=${2:?--assemblies needs a list}; shift 2 ;;
        -h|--help)    usage; exit 0 ;;
        *)            echo "ffverify: unknown option $1" >&2; usage >&2; exit 2 ;;
    esac
done

# A tag that cannot collide with another invocation in the same directory, so an agent running
# this three times never overwrites the harness's own results file (or its own earlier one).
if [ -z "$TAG" ]; then
    TAG=$(date +%Y%m%d-%H%M%S)-$$
fi
case "$TAG" in
    *[!A-Za-z0-9._-]*) echo "ffverify: --tag must match [A-Za-z0-9._-]+" >&2; exit 2 ;;
esac

mkdir -p "$OUT" || { echo "ffverify: cannot create $OUT" >&2; exit 2; }
RESULTS="$OUT/TestResults-$TAG.xml"
LOG="$OUT/unity-$TAG.log"
JSON="$OUT/verification-$TAG.json"
rm -f "$RESULTS" "$LOG" "$JSON"

if [ ! -d "$PROJECT/Assets" ]; then
    echo "ffverify: $PROJECT does not look like a Unity project" >&2
    exit 2
fi

ASM_ARGS=()
if [ -n "$ASSEMBLIES" ]; then
    ASM_ARGS=(-assemblyNames "$ASSEMBLIES")
fi

# The seat, taken as late as possible and only by a caller that is really about to use it.
if declare -F ensure_unity_license >/dev/null 2>&1; then
    ensure_unity_license
fi

STARTED=$(date +%s)
# No -quit: the command-line test runner quits by itself once the run finishes, and -quit races
# it into an empty results file. The image's unity-editor wrapper already supplies -batchmode and
# wraps the editor in xvfb-run, so shaders import the way they do in CI.
"$UNITY" \
    -runTests \
    -testPlatform EditMode \
    -projectPath "$PROJECT" \
    -testResults "$RESULTS" \
    "${ASM_ARGS[@]}" \
    -logFile /dev/stdout >"$LOG" 2>&1
UNITY_RC=$?
ELAPSED=$(( $(date +%s) - STARTED ))

python3 - "$RESULTS" "$LOG" "$JSON" "$UNITY_RC" "$ELAPSED" <<'PYEOF'
"""Turn one Unity run into the six facts the verification table stores.

`compiled` is deliberately not "Unity exited 0". A compile failure aborts the run before any
test executes, so the results file is missing and the exit code is a generic failure; a genuine
test failure produces a complete results file and exit 2. Distinguishing them is the whole point
of recording compile_errors separately from tests_failed.
"""
import json
import re
import sys
import xml.etree.ElementTree as ET

results_path, log_path, json_path, rc, elapsed = sys.argv[1:6]
rc, elapsed = int(rc), int(elapsed)

try:
    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
        log = fh.read()
except OSError:
    log = ""

# The same signal the MCP-bridge ritual greps for. Unity prints Burst/ILPP failures differently,
# so those are matched too rather than being reported as a clean compile.
errors = re.findall(r"^.*(?:error CS\d+|Compilation failed|error: Burst|Unhandled log message"
                    r": '\[Error\]).*$", log, re.MULTILINE)
seen, compile_errors = set(), []
for line in errors:
    line = line.strip()[:300]
    if line not in seen:
        seen.add(line)
        compile_errors.append(line)

total = passed = failed = None
parsed = False
try:
    root = ET.parse(results_path).getroot()
    total = int(root.get("total") or 0)
    passed = int(root.get("passed") or 0)
    failed = int(root.get("failed") or 0)
    parsed = True
except (OSError, ET.ParseError, TypeError, ValueError):
    pass

failures = []
if parsed:
    for case in root.iter("test-case"):
        if case.get("result") == "Failed":
            msg = case.find(".//failure/message")
            failures.append("%s: %s" % (case.get("fullname"),
                                        (msg.text or "").strip().splitlines()[0][:200]
                                        if msg is not None and msg.text else "failed"))

# A results file that parsed proves the assemblies compiled and the suite executed: the test
# runner cannot reach RunFinished with a broken assembly. Without one, only the absence of
# error lines is evidence, and that is weaker — so it is reported as not compiled.
compiled = parsed and not compile_errors
ran = parsed or bool(compile_errors) or rc != 0

evidence = []
evidence.append("unity exit %d after %ds" % (rc, elapsed))
if parsed:
    evidence.append("results %s: total=%s passed=%s failed=%s"
                    % (results_path, total, passed, failed))
else:
    evidence.append("no parseable results at %s" % results_path)
evidence += failures[:10]
if compile_errors:
    evidence.append("compile errors:")
    evidence += compile_errors[:20]
if not parsed and not compile_errors:
    evidence.append("editor log tail:")
    evidence += [ln for ln in log.strip().splitlines()[-15:]]

report = {
    "ran": bool(ran),
    "compiled": bool(compiled),
    "compile_errors": "\n".join(compile_errors[:50]) or None,
    "tests_run": total,
    "tests_passed": passed,
    "tests_failed": failed,
    "results_path": results_path,
    "evidence": "\n".join(evidence)[:8000],
    "exit_code": rc,
    "secs": elapsed,
    "log_path": log_path,
}
with open(json_path, "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2, ensure_ascii=False)

print("ffverify: compiled=%s tests %s/%s failed=%s (%s)"
      % (report["compiled"], passed, total, failed, json_path))
sys.exit(0 if report["compiled"] and (failed or 0) == 0 and parsed else 1)
PYEOF
exit $?
