#!/usr/bin/env bash
#
# ffmcp — the live Unity editor a turn drives over the MCP bridge, and its whole life.
#
# The third Unity entry point mounted onto a container's PATH, beside ffverify (one EditMode suite)
# and ffplaytest (one play-mode session). This one is different in kind: it starts an editor and
# LEAVES IT RUNNING, so the agent can look at live state, change something and look again over the
# MCP tools instead of paying a fresh boot per question.
# design/unitymcp_container_design.txt is the argument; this is the implementation.
#
#   ffmcp start     boot the editor and wait for the bridge. Idempotent.
#   ffmcp status    is it up, on which port, since when. Exit 0 up, 1 down.
#   ffmcp port      just the port, for anything talking to the bridge directly.
#   ffmcp stop      kill it -- as a PROCESS GROUP -- and clear the state.
#   ffmcp restart   stop then start, for a bridge that has gone deaf.
#
# WHY A SCRIPT RATHER THAN A COUPLE OF LINES IN THE TASK. Three traps, every one mechanical, and
# every one measured on this box on 2026-09-11 rather than guessed:
#
#   1. THE PROCESS GROUP. `unity-editor` in this image is a WRAPPER that execs xvfb-run, which
#      starts an Xvfb and the editor as its own children. SIGTERM to the wrapper's pid kills the
#      wrapper and REPARENTS the editor to init, where it goes on holding the Unity LICENCE SEAT and
#      the project lock. A stub reproduced exactly that. So: launch under setsid, signal the group.
#
#   2. READINESS IS A LOG LINE, NOT A FILE. PortManager writes
#      ~/.unity-mcp/unity-mcp-port-<hash>.json only when it has to move OFF the default port, so a
#      bridge that gets 6400 publishes nothing at all. The first probe of this feature waited for
#      that file and reported failure while the editor log had been saying
#      `StdioBridgeHost started on port 6400` for five minutes. The log line is the signal, and it
#      carries the port.
#
#   3. UNITY_MCP_ALLOW_BATCH. StdioBridgeHost's static constructor RETURNS EARLY in batch mode
#      without it, so the keep-alive hooks that survive a domain reload are never installed. A
#      headless editor without this variable is an editor that serves nothing.
#
# ONE PROJECT, ONE EDITOR. Unity refuses a second editor on a project it already has open --
# measured: `Multiple Unity instances cannot open the same project.`, exit 1. So ffverify and
# ffplaytest ask `ffmcp status` and refuse rather than fight, and the harness stops the bridge
# before its own verification run. While the bridge IS up, the MCP `run_tests` tool is the test
# channel: it uses the editor that is already running instead of booting a second one.
#
# No `set -e`: every command here has a reportable failure and dying silently on one would leave a
# caller unable to tell "no bridge" from "ffmcp itself broke".
set -uo pipefail

WS=${FFMCP_PROJECT:-${FFBOX_WORKSPACE:-/opt/actions-runner/_work/FinalFactory/FinalFactory}}
STATE_DIR=${FFMCP_STATE:-${FFBOX_OUT:-/ffbox/out}/mcp}
UNITY=${FFMCP_UNITY:-unity-editor}
READY_TIMEOUT=${FFMCP_READY_TIMEOUT:-600}
STATE=$STATE_DIR/state.json
LOG=$STATE_DIR/editor.log

say()  { echo "ffmcp: $*"; }
err()  { echo "ffmcp: $*" >&2; }

usage() {
    cat <<'EOF'
Usage: ffmcp {start|stop|status|port|restart}

  start    Boot a headless editor and wait for the MCP bridge. Idempotent: a second start while
           one is up reports the existing port and changes nothing.
  status   Exit 0 and print the port if the bridge is up; exit 1 if it is not.
  port     Print the port alone. Exit 1 if there is no bridge.
  stop     Kill the editor's whole process group and clear the state.
  restart  stop, then start.

Environment:
  FFBOX_UNITY_MCP=1     required for `start` — the harness sets it for classes that enable the
                        bridge. Without it start refuses, because an editor whose tools are not on
                        the model's tool list is worse than no editor at all.
  FFMCP_READY_TIMEOUT   seconds to wait for the bridge (default 600).
  FFMCP_PROJECT         the Unity project (default: this run's workspace).
  FFMCP_STATE           where pid/port/log live (default: $FFBOX_OUT/mcp).

While the bridge is up, ffverify and ffplaytest refuse: one project cannot hold two editors. Use
the MCP `run_tests` tool instead, or `ffmcp stop` first.
EOF
}

# --- state ---------------------------------------------------------------------------------------
# One small JSON file rather than three dotfiles, because the host reads this directory too: it is
# under /ffbox/out, which the run's spool carries away, so a run that ended badly leaves its editor
# log and the bridge's last known phase where somebody can still read them.
write_state() {   # <phase> <pid> <pgid> <port>
    mkdir -p "$STATE_DIR" 2>/dev/null
    chmod g+w "$STATE_DIR" 2>/dev/null || :
    python3 - "$STATE" "$1" "$2" "$3" "$4" "$WS" "$LOG" <<'PYEOF'
import json, os, sys, time
state, phase, pid, pgid, port, ws, log = sys.argv[1:8]

# BOTH VERSIONS, because they can drift and the failure looks like nothing else: the editor package
# comes from the game repo's manifest, the server is pinned in our image, and a mismatch connects
# and then refuses tools. Recorded here so the evidence is in the spool rather than in memory.
pkg = None
for base in (os.path.join(ws, "Packages"), os.path.join(ws, "Library", "PackageCache")):
    try:
        for name in sorted(os.listdir(base)):
            if name.startswith("com.coplaydev.unity-mcp"):
                manifest = os.path.join(base, name, "package.json")
                try:
                    with open(manifest, encoding="utf-8") as fh:
                        pkg = json.load(fh).get("version")
                except OSError:
                    pkg = name
                break
    except OSError:
        continue
    if pkg:
        break

with open(state, "w", encoding="utf-8") as fh:
    json.dump({"phase": phase, "pid": int(pid or 0), "pgid": int(pgid or 0),
               "port": int(port or 0), "project": ws, "log": log,
               "editor_package_version": pkg,
               "server_version": os.environ.get("FFMCP_SERVER_VERSION") or None,
               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, fh, indent=2)
PYEOF
}

read_state() {   # sets ST_PHASE ST_PID ST_PGID ST_PORT; returns 1 with no state file
    ST_PHASE=; ST_PID=; ST_PGID=; ST_PORT=
    [ -f "$STATE" ] || return 1
    local line
    line=$(python3 -c "
import json,sys
try:
    d = json.load(open(sys.argv[1], encoding='utf-8'))
except Exception:
    raise SystemExit(1)
print(d.get('phase') or '', d.get('pid') or 0, d.get('pgid') or 0, d.get('port') or 0)
" "$STATE" 2>/dev/null) || return 1
    ST_PHASE=$(echo "$line" | cut -d' ' -f1)
    ST_PID=$(echo "$line" | cut -d' ' -f2)
    ST_PGID=$(echo "$line" | cut -d' ' -f3)
    ST_PORT=$(echo "$line" | cut -d' ' -f4)
    return 0
}

# ANY OF OURS, not just the wrapper. The wrapper exits first when a run is torn down, and an
# `editor_alive` that only watched it would report "stopped" with a 7.8 GiB editor still holding the
# licence seat -- the worst possible answer, because it is a confident wrong one.
editor_alive() {
    [ -n "${ST_PID:-}" ] && [ "${ST_PID:-0}" -gt 0 ] 2>/dev/null || return 1
    kill -0 "$ST_PID" 2>/dev/null && return 0
    [ -n "$(our_pids)" ]
}

# THE PORT CAN MOVE, so a cached one is a guess. PortManager keeps the port it was using and only
# leaves 6400 when something else holds it -- which is exactly what a DOMAIN RELOAD can look like,
# the pre-reload listener still on the socket as the new one starts. The editor announces every
# bridge start in its log, so the LAST such line is the current answer and the state file's number
# is only the last one we happened to write down.
log_port() {
    grep -o "StdioBridgeHost started on port [0-9]*" "$LOG" 2>/dev/null \
        | tail -1 | awk '{print $NF}'
}

bridge_up() {
    read_state || return 1
    [ "$ST_PHASE" = "up" ] || return 1
    editor_alive || return 1
    local fresh
    fresh=$(log_port)
    if [ -n "$fresh" ] && [ "$fresh" != "${ST_PORT:-}" ]; then
        say "the bridge moved to port $fresh (was ${ST_PORT:-none}); updating the record"
        ST_PORT=$fresh
        write_state up "$ST_PID" "${ST_PGID:-0}" "$fresh"
    fi
    [ "${ST_PORT:-0}" -gt 0 ] 2>/dev/null || return 1
    # The pid being alive is not the same as the bridge answering, so ask the socket.
    python3 - "$ST_PORT" <<'PYEOF' >/dev/null 2>&1
import socket, sys
s = socket.socket(); s.settimeout(3)
try:
    s.connect(("127.0.0.1", int(sys.argv[1])))
finally:
    s.close()
PYEOF
}

# --- stop ----------------------------------------------------------------------------------------
# IS THE RECORDED PID ACTUALLY OUR EDITOR? The state file lives under /ffbox/out, which the AGENT
# can write -- it is the same bind mount the transcript goes to. Signalling a process group because
# a file said so is therefore taking an editable file's word for which processes to kill, and the
# one thing this script must never do is kill something that is not ours.
#
# So the pid is checked against /proc before any signal: its command line has to be a Unity editor
# opened on THIS project. Not a process hunt -- there is no searching here, no pkill, no ps; we
# look up one pid we were told about and refuse it if it is not what we started. (The sweep in
# test_ffwatch.py forbids the hunting idioms outright, which is the same rule from the other side.)
pid_is_our_editor() {   # <pid>
    local cmd
    [ -r "/proc/$1/cmdline" ] || return 1
    cmd=$(tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null) || return 1
    case "$cmd" in
        *Editor/Unity*|*unity-editor*|*xvfb-run*) ;;
        *) return 1 ;;
    esac
    case "$cmd" in
        *"$WS"*) return 0 ;;
        *) return 1 ;;
    esac
}

# THE EDITOR IS NOT IN THE GROUP WE MADE, and the group kill alone does not touch it. Measured in
# a real container on 2026-09-11, phase F:
#
#     288 pgid=288  /bin/bash /usr/bin/unity-editor -projectPath <WS> -executeMethod ...   <- ours
#     292 pgid=288  /bin/sh /usr/bin/xvfb-run -ae /dev/stdout /opt/unity/Editor/Unity ...
#     302 pgid=288  Xvfb :99
#     305 pgid=305  /opt/unity/Editor/Unity -batchmode -projectPath <WS> ...   <- ITS OWN GROUP
#    4510 pgid=4510 Unity ... AssetImportWorker14 -projectPath <WS>            <- and its workers
#
# So `kill -- -288` reaches the wrapper and Xvfb and never signals the 7.8 GiB editor. It died
# anyway in the first probe -- because Xvfb went out from under it -- and that accident was doing
# the work the comment in this script claimed the group kill was doing. An editor that does not
# notice its display vanish keeps the LICENCE SEAT and the project lock, which is the exact failure
# this script exists to prevent.
#
# WHAT MAKES THEM OURS IS DESCENT, NOT A GUESS. We walk the tree down from the pid we started and
# take what is under it, cross-checked against our own project path. That is not the "find stray
# Unity processes" path design/discord_persistent_design.txt section 14 rule 2 forbids: we are not
# asking which editors exist, we are asking what our own process started.
our_pids() {   # prints the pids to signal, editors first
    python3 - "${ST_PID:-0}" "${ST_PGID:-0}" "$WS" <<'PYEOF'
import os, sys

root_pid, pgid, ws = int(sys.argv[1] or 0), int(sys.argv[2] or 0), sys.argv[3]
procs = {}
for entry in os.listdir("/proc"):
    if not entry.isdigit():
        continue
    pid = int(entry)
    try:
        with open(f"/proc/{pid}/stat") as fh:
            after = fh.read().rsplit(")", 1)[1].split()
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            cmd = fh.read().replace(b"\0", b" ").decode("utf-8", "replace")
    except (OSError, IndexError):
        continue
    procs[pid] = {"ppid": int(after[1]), "pgid": int(after[2]), "cmd": cmd}

children = {}
for pid, info in procs.items():
    children.setdefault(info["ppid"], []).append(pid)

# every descendant of the pid we started, transitively
tree, stack = set(), [root_pid] if root_pid else []
while stack:
    pid = stack.pop()
    if pid in tree or pid not in procs:
        continue
    tree.add(pid)
    stack.extend(children.get(pid, []))

chosen = []
for pid, info in procs.items():
    if pid == os.getpid():
        continue
    in_group = pgid and info["pgid"] == pgid          # the group we created with setsid
    descendant = pid in tree and ws and ws in info["cmd"]   # ours by descent, and our project
    if in_group or descendant:
        chosen.append((0 if "Unity" in info["cmd"] or "unity" in info["cmd"] else 1, pid))

# Editors first: an editor told to go while its Xvfb is still up can exit properly, which is how
# the licence comes back and the lockfile goes.
for _, pid in sorted(chosen):
    print(pid)
PYEOF
}

stop_group() {   # <signal>
    if [ -n "${ST_PID:-}" ] && [ "${ST_PID:-0}" -gt 0 ] 2>/dev/null \
       && kill -0 "$ST_PID" 2>/dev/null && ! pid_is_our_editor "$ST_PID"; then
        err "pid $ST_PID is not an editor on $WS; refusing to signal it"
        return 1
    fi
    local pid signalled=0
    for pid in $(our_pids); do
        kill "-$1" "$pid" 2>/dev/null && signalled=$(( signalled + 1 ))
    done
    # The group as well, for anything that appeared between the walk and now.
    if [ -n "${ST_PGID:-}" ] && [ "${ST_PGID:-0}" -gt 0 ] 2>/dev/null; then
        kill "-$1" -- "-$ST_PGID" 2>/dev/null && signalled=$(( signalled + 1 ))
    fi
    [ "$signalled" -gt 0 ]
}

cmd_stop() {
    if ! read_state; then
        say "no bridge recorded; nothing to stop"
        return 0
    fi
    if editor_alive; then
        say "stopping editor pid=$ST_PID pgid=$ST_PGID"
        stop_group TERM
        local i
        for i in $(seq 1 20); do
            editor_alive || break
            sleep 1
        done
        if editor_alive; then
            say "it did not go on TERM; KILL"
            stop_group KILL
            sleep 2
        fi
    else
        say "recorded editor is already gone"
    fi
    # A STALE PROJECT LOCK, AND ONLY WHEN WE KNOW WE OWN IT. Unity refuses a second editor on a
    # locked project, so a lock left by an editor we just killed would break every later editor in
    # this container -- including the harness's own ffverify. But a lock whose owner is ALIVE is
    # telling the truth, which is why this is after the kill and conditional on the pid being gone.
    # Never a general "clear the lock" step. (Where 6000.3 keeps this is not firmly established --
    # the two-editor probe could not stat it -- so this removes the path if it is there and says
    # nothing if it is not, rather than asserting the path exists.)
    if ! editor_alive && [ -e "$WS/Temp/UnityLockfile" ]; then
        say "removing the lock left by the editor we killed: $WS/Temp/UnityLockfile"
        rm -f "$WS/Temp/UnityLockfile"
    fi
    write_state down 0 0 0
    say "stopped"
}

# --- start ---------------------------------------------------------------------------------------
cmd_start() {
    # ENABLED FOR THIS RUN, OR NOT AT ALL. The tool list is decided by the host when it builds the
    # claude argv; a turn that starts an editor whose tools were never offered gets an editor it
    # cannot drive, which is strictly worse than no editor. design section 13.2.
    if [ "${FFBOX_UNITY_MCP:-0}" != "1" ]; then
        err "the MCP bridge is not enabled for this run"
        err "  (the host enables it per agent class: unity_mcp.enabled in ~/.config/ffbox/config.json)"
        err "  ffverify and ffplaytest are the Unity channels available here."
        return 3
    fi

    if bridge_up; then
        say "bridge already up on port $ST_PORT (pid $ST_PID)"
        echo "$ST_PORT"
        return 0
    fi

    if [ ! -d "$WS/Assets" ]; then
        err "$WS does not look like a Unity project"
        return 2
    fi

    # THE PACKAGE GATE. The Unity half of the bridge ships with the project; without it the editor
    # boots, ignores everything, and the wait burns the whole readiness budget to learn nothing.
    # Same shape as ffplaytest's own base-ref gate.
    if ! ls -d "$WS/Packages/com.coplaydev.unity-mcp" >/dev/null 2>&1 \
       && ! ls -d "$WS/Library/PackageCache/com.coplaydev.unity-mcp"* >/dev/null 2>&1; then
        err "this workspace has no MCP for Unity package (com.coplaydev.unity-mcp)"
        err "  looked in $WS/Packages and $WS/Library/PackageCache"
        err "  Without it no editor here can serve the bridge; ffverify still works."
        write_state absent 0 0 0
        return 3
    fi

    if [ -r /ffbox/unity-license.sh ] && ! declare -F ensure_unity_license >/dev/null 2>&1; then
        . /ffbox/unity-license.sh
    fi
    if declare -F ensure_unity_license >/dev/null 2>&1; then
        ensure_unity_license
    fi

    mkdir -p "$STATE_DIR" || { err "cannot create $STATE_DIR"; return 2; }
    chmod g+w "$STATE_DIR" 2>/dev/null || :
    rm -f "$LOG"
    write_state starting 0 0 0

    say "booting the editor for the bridge (project $WS)"
    # NO -quit: the editor must stay up. -executeMethod runs McpCiBoot, which forces HTTP transport
    # off and starts the stdio bridge; UNITY_MCP_ALLOW_BATCH is what lets it do that headless.
    # Telemetry off three ways because the package reads three different variables and a blocked
    # outbound call behind the egress fence is a stall waiting to happen.
    if command -v setsid >/dev/null 2>&1; then
        UNITY_MCP_ALLOW_BATCH=1 \
        DISABLE_TELEMETRY=1 UNITY_MCP_DISABLE_TELEMETRY=1 MCP_DISABLE_TELEMETRY=1 \
        setsid "$UNITY" \
            -projectPath "$WS" \
            -executeMethod MCPForUnity.Editor.McpCiBoot.StartStdioForCi \
            -logFile /dev/stdout >"$LOG" 2>&1 &
        ST_PID=$!
        ST_PGID=$ST_PID          # setsid makes the child a session and group leader
    else
        UNITY_MCP_ALLOW_BATCH=1 \
        DISABLE_TELEMETRY=1 UNITY_MCP_DISABLE_TELEMETRY=1 MCP_DISABLE_TELEMETRY=1 \
        "$UNITY" \
            -projectPath "$WS" \
            -executeMethod MCPForUnity.Editor.McpCiBoot.StartStdioForCi \
            -logFile /dev/stdout >"$LOG" 2>&1 &
        ST_PID=$!
        ST_PGID=
    fi
    write_state starting "$ST_PID" "${ST_PGID:-0}" 0

    local waited=0 port=
    while [ "$waited" -lt "$READY_TIMEOUT" ]; do
        if ! kill -0 "$ST_PID" 2>/dev/null; then
            err "the editor exited after ${waited}s without opening the bridge"
            err "  log: $LOG"
            tail -15 "$LOG" >&2
            write_state failed 0 0 0
            return 1
        fi
        port=$(grep -o "StdioBridgeHost started on port [0-9]*" "$LOG" 2>/dev/null \
               | tail -1 | awk '{print $NF}')
        if [ -n "$port" ]; then
            write_state up "$ST_PID" "${ST_PGID:-0}" "$port"
            say "bridge up on port $port after ${waited}s (pid $ST_PID)"
            echo "$port"
            return 0
        fi
        sleep 2
        waited=$(( waited + 2 ))
    done

    err "no bridge after ${READY_TIMEOUT}s; stopping the editor"
    err "  log: $LOG"
    tail -15 "$LOG" >&2
    cmd_stop >/dev/null
    write_state timeout 0 0 0
    return 1
}

cmd_status() {
    if bridge_up; then
        say "up on port $ST_PORT (pid $ST_PID, project $WS)"
        return 0
    fi
    if read_state; then
        say "down (last phase: ${ST_PHASE:-unknown}; log $LOG)"
    else
        say "down (no bridge has been started in this container)"
    fi
    return 1
}

cmd_port() {
    bridge_up || return 1
    echo "$ST_PORT"
}

case "${1:-}" in
    start)    cmd_start ;;
    stop)     cmd_stop ;;
    status)   cmd_status ;;
    port)     cmd_port ;;
    restart)  cmd_stop; cmd_start ;;
    -h|--help|help) usage ;;
    "")       usage >&2; exit 2 ;;
    *)        err "unknown command $1"; usage >&2; exit 2 ;;
esac
