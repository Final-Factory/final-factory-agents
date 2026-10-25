#!/usr/bin/env python3
"""record_clip: record a short 60 fps clip of the running game (a built player or the Unity editor)
while an effect plays, then optionally review it with watch_video.

    record_clip --player --effect afterburner --review "a short blue flame that ..."
    record_clip --unity --name frenzy_before --seconds 4 --lead 1     # you fire it (MCP) on RECORDING
    record_clip --pid 1234 --do "ffauto:camera.zoom|600" --do "ffauto:ability.afterburner"

It records in REAL time, what the screen shows: the simulation runs on wall-clock heartbeats
(HeartbeatSystem, Stopwatch) while the VFX clock runs on frame time, so a frame-by-frame offline
recorder would put effects and motion out of step. Standard library only; needs ffmpeg.
macOS: ScreenCaptureKit (mac/sckrec.swift, compiled once with swiftc) records the window even when
it is covered. Windows: ffmpeg gfxcapture (Windows Graphics Capture, ffmpeg 8+) of the window itself, which
records it when covered too; else ddagrab (Desktop Duplication) of the window's client area, which must be visible.
"""
from __future__ import annotations

import argparse
import ctypes
import http.client
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WIN = platform.system() == "Windows"
MAC = platform.system() == "Darwin"
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "watch_video")
DATA = (os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "LocalLow", "Never Games", "finalfactory")
        if WIN else os.path.expanduser("~/Library/Application Support/Never Games/finalfactory"))

# Named effects: `pre` runs before recording (set-up, waited on), `do` fires `lead` seconds into
# the recording. {px} {pz} = the local player's position. Commands go over the game's agent channel
# (ffauto verbs, LocalMultiplayerAutomationCommandRunner). Without a channel, fire it yourself.
EFFECTS = {
    "afterburner": {"do": ["ability.afterburner"], "seconds": 3.5,
                    "about": "the Space dash: flame, trail and the ship's burst of speed"},
    "engine": {"do": ["movement.hold|{px+900}|{pz}|3"], "seconds": 4.0,
               "about": "the player ship's engine plume while flying east"},
    "bat-exhaust": {"pre": ["spawn.ships|Bat|6"], "do": ["movement.hold|{px+900}|{pz}|3"], "seconds": 4.5,
                    "about": "six Bats following the player east: their exhaust"},
    "plasma": {"do": ["ability.cast|plasma|1|0"], "seconds": 3.0, "about": "one Plasma Bolt fired east"},
    "frenzy": {"do": ["ability.cast|frenzy|{px}|{pz}"], "seconds": 5.0, "about": "Frenzy cast on the player's fleet"},
    "guardian": {"do": ["ability.cast|guardian|{px}|{pz}"], "seconds": 5.0, "about": "Guardian cast at the player"},
    "obliterator": {"do": ["ability.cast|obliterator|{px+300}|{pz}"], "seconds": 5.0,
                    "about": "Obliterator cast just east of the player"},
}


# ------------------------------------------------------------------------------ the target

def unity_pid(project):
    """The Unity editor (not an import worker) whose -projectPath is `project`."""
    if WIN:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-CimInstance Win32_Process -Filter \"Name='Unity.exe'\" | "
                              "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
                             capture_output=True, text=True).stdout
        rows = [line.split("\t", 1) for line in out.splitlines() if "\t" in line]
    else:
        out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
        rows = [line.strip().split(None, 1) for line in out.splitlines() if "Unity" in line]
    want = os.path.normcase(os.path.abspath(project)).rstrip("\\/")
    for pid, cmd in rows:
        if "-batchMode" in cmd or "AssetImportWorker" in cmd:
            continue
        m = re.search(r"-projectpath\s+(\"[^\"]+\"|\S+)", cmd, re.I)
        if m and os.path.normcase(os.path.abspath(m.group(1).strip('"'))).rstrip("\\/") == want:
            return int(pid)
    sys.exit(f"record_clip: no Unity editor open on {project}")


# Any case: build_player.sh names the player finalfactory.app / finalfactory.x86_64 (w1797, 2026-10-23: a case-sensitive
# "FinalFactory" missed a running player on the M3).
PLAYER_PROCESS = re.compile(r"/FinalFactory[^/]*\.app/Contents/MacOS/|FinalFactory\S*\.x86_64", re.IGNORECASE)


def player_pid():
    """The built player THIS worker launched (w1856: a worker took the newest session file and drove another worker's
    player on BEAST). The game checkout's `player_slots.py mine --one` answers from this session's leases (FF_SESSION_ID);
    without it (no worker session, or a checkout older than w1856) only a single running player is taken: several are
    refused, never the newest picked, since the newest is whichever worker's started last."""
    slots = os.path.join(repo_root(), "scripts", "nightly", "player_slots.py")
    if os.environ.get("FF_SESSION_ID") and os.path.exists(slots):
        r = subprocess.run([sys.executable, slots, "mine", "--one"], capture_output=True, text=True)
        if r.returncode == 0:
            return int(json.loads(r.stdout)["pid"])
        if "invalid choice" not in r.stderr:  # a checkout older than w1856 has no `mine`: fall through
            sys.exit(f"record_clip: {r.stderr.strip().removeprefix('ERROR: ')} (or pass --pid <the pid launch printed>)")
    pids = running_player_pids()
    if not pids:
        sys.exit("record_clip: no running FinalFactory player (start one from the slot pool first)")
    if len(pids) > 1:
        sys.exit(f"record_clip: {len(pids)} FinalFactory players run here (pids {', '.join(map(str, pids))}), and which is "
                 "yours is unknown: pass --pid with the one you launched (player_slots.py launch --detach printed it)")
    return pids[0]


def running_player_pids():
    """Every running built Final Factory player on this computer, oldest first."""
    if WIN:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-Process | Where-Object { $_.ProcessName -like 'FinalFactory*' } | "
                              "Sort-Object StartTime | ForEach-Object { $_.Id }"], capture_output=True, text=True).stdout
        pids = [int(x) for x in out.split()]
    else:
        out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
        pids = [int(l.split()[0]) for l in out.splitlines()
                if PLAYER_PROCESS.search(l)]
    return pids


def repo_root():
    try:
        return subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return os.getcwd()


BENCH_BUSY_EXIT = 76  # the game repo's bench_queue.py EXIT_BENCH_BUSY


def bench_gate(wait_s=None):
    """w1750 (lothsahn, 2026-10-22: "Why is the game player running if the worker has an exclusive lock on beast?"): no
    clip is shot while another worker's timed run holds this machine's bench lock. The game repo's own check decides
    (`scripts/bench/bench_queue.py gate`, the same one player_slots.py launch makes): the checkout this runs in, else the
    newest one in the worker install's sandboxes. It passes the holder's own clips (its FF_SESSION_ID or FF_BENCH_TICKET),
    waits up to `wait_s` (default $FF_BENCH_WAIT_S, else 0) and exits 76 naming the holder and the end of its hold. With
    no checkout that has the gate (older than w1750, or none), the clip goes ahead. FF_BENCH_GATE=off skips it."""
    if os.environ.get("FF_BENCH_GATE", "").lower() in ("off", "0", "no"):
        return
    cands = [os.path.join(repo_root(), "scripts", "bench", "bench_queue.py")]
    root = os.environ.get("FF_WORKER_ROOT")
    if root:
        found = []
        try:
            for n in os.listdir(os.path.join(root, "sandboxes")):
                c = os.path.join(root, "sandboxes", n, "scripts", "bench", "bench_queue.py")
                if os.path.exists(c):
                    found.append((os.path.getmtime(c), c))
        except OSError:
            pass
        cands += [c for _, c in sorted(found, reverse=True)]
    for c in cands:
        if not os.path.exists(c):
            continue
        cmd = [sys.executable, c, "gate", "--what", "a clip"] + (["--wait", str(wait_s)] if wait_s is not None else [])
        try:
            r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except OSError:
            continue
        if r.returncode == 0:
            if r.stderr.strip():
                print(r.stderr.strip(), file=sys.stderr)
            return
        if r.returncode == BENCH_BUSY_EXIT:
            print(r.stderr.strip(), file=sys.stderr)
            sys.exit(BENCH_BUSY_EXIT)
        # 2: a checkout from before w1750 has no `gate`; try the next


# ---------------------------------------------------------------------------- agent channel

class Channel:
    """The game's loopback agent API (POST /v1/command), as the shipped ff-agent uses it."""

    def __init__(self, pid):
        p = os.path.join(DATA, "AgentControl", f"session-{pid}.json")
        s = json.load(open(p, encoding="utf-8"))
        self.port, self.h = s["port"], {"Authorization": "Bearer " + s["token"], "Content-Type": "application/json"}

    @staticmethod
    def find(pid):
        try:
            return Channel(pid)
        except (OSError, KeyError, ValueError):
            return None

    def req(self, method, path, body=None, timeout=35):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        c.request(method, path, json.dumps(body) if body is not None else None, self.h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return json.loads(data) if data else {}

    def cmd(self, command, wait=False):
        command = command if command.startswith("ffauto:") else "ffauto:" + command
        r = self.req("POST", "/v1/command", {"actor": "local-player", "command": command})
        if r.get("status") == "rejected":
            print(f"  REJECTED {command}: {r.get('reason')} {r.get('detail', '')}")
        elif wait and r.get("chainId"):
            end = time.time() + 120
            while time.time() < end:
                s = self.req("GET", f"/v1/chain/{r['chainId']}?timeoutMs=25000")
                if s.get("status") not in ("running", "", None):
                    return s
        return r

    def player_xz(self):
        snap = self.req("GET", "/v1/snapshot/player")

        def find(o):
            if isinstance(o, dict):
                if "world" in o and isinstance(o["world"], dict):
                    return o["world"]
                for v in o.values():
                    f = find(v)
                    if f is not None:
                        return f
            return None
        w = find(snap) or {}
        num = lambda v: float(v["value"] if isinstance(v, dict) and "value" in v else v)
        try:
            return num(w["x"]), num(w["z"])
        except (KeyError, TypeError, ValueError):
            return None


def fill(cmd, xz):
    if "{" not in cmd:
        return cmd
    if xz is None:
        sys.exit(f"record_clip: '{cmd}' needs the player position, and the snapshot had none")
    px, pz = xz
    return re.sub(r"\{(p[xz])([+-]\d+(?:\.\d+)?)?\}",
                  lambda m: f"{(px if m.group(1) == 'px' else pz) + float(m.group(2) or 0):.1f}", cmd)


# -------------------------------------------------------------------------------- recorders

def mac_recorder():
    exe = os.path.join(CACHE, "bin", "sckrec")
    src = os.path.join(HERE, "mac", "sckrec.swift")
    if not os.path.exists(exe) or os.path.getmtime(exe) < os.path.getmtime(src):
        os.makedirs(os.path.dirname(exe), exist_ok=True)
        print("  compiling the ScreenCaptureKit recorder (once)")
        subprocess.run(["swiftc", "-O", src, "-o", exe], check=True)
    return exe


def win_client_rect(pid, with_hwnd=False):
    """Screen rect (x, y, w, h) of the pid's largest visible window's client area, in pixels (and its hwnd)."""
    from ctypes import wintypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(r))
            pt = wintypes.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(pt))
            found.append((r.right * r.bottom, pt.x, pt.y, r.right, r.bottom, int(hwnd or 0)))
        return True
    user32.EnumWindows(cb, 0)
    if not found:
        sys.exit(f"record_clip: no visible window for pid {pid}")
    _, x, y, w, h, hwnd = max(found)
    return (x, y, w, h, hwnd) if with_hwnd else (x, y, w, h)


def win_monitors():
    """Monitors as (left, top, right, bottom, primary), primary first (the usual DXGI order)."""
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    mons = []

    class MI(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def cb(hmon, _hdc, _rc, _):
        mi = MI()
        mi.cbSize = ctypes.sizeof(MI)
        user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        r = mi.rcMonitor
        mons.append((r.left, r.top, r.right, r.bottom, bool(mi.dwFlags & 1)))
        return True
    user32.EnumDisplayMonitors(None, None, cb, 0)
    return sorted(mons, key=lambda m: (not m[4], m[0], m[1]))


def ffmpeg_has(encoder):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return f" {encoder} " in out


def ffmpeg_has_filter(name):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return any(line.split()[1:2] == [name] for line in out.splitlines() if line.strip())


def wait_first_frame(proc, raw, tries=16):
    """True once the recorder wrote its first frame (the container header comes with it), False if it ended or
    stalled for tries * 0.5 s."""
    for _ in range(tries):
        time.sleep(0.5)
        if os.path.exists(raw) and os.path.getsize(raw) > 0:
            return True
        if proc.poll() is not None:
            return False
    return False


def encoder_works(encoder):
    """Whether this machine can encode with `encoder`: ffmpeg lists NVENC whenever it was built with it, and on a PC
    without an NVIDIA GPU (lothdesktop's Intel Arc, w1065) the capture then hung instead of failing. Try one."""
    if not ffmpeg_has(encoder):
        return False
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.2", "-c:v", encoder,
                            "-f", "null", "-"], capture_output=True, timeout=20)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def start_windows(pid, raw, seconds, fps, monitor):
    x, y, w, h, hwnd = win_client_rect(pid, with_hwnd=True)
    # Windows Graphics Capture of the window itself (ffmpeg 8+ gfxcapture) first: it records the game's own client
    # area whatever covers it. On a desktop shared with other sandboxes, ddagrab and gdigrab record the screen
    # (w1934, lothdesktop, 2026-10-25: ddagrab gave no frame, the gdigrab fallback recorded another sandbox's Unity
    # splash window over the player, exit 0; gfxcapture on the player's hwnd gave the right picture in 3 of 3 clips).
    grab_mode = os.environ.get("FF_CLIP_GRAB", "")
    if grab_mode not in ("ddagrab", "gdigrab") and hwnd and ffmpeg_has_filter("gfxcapture"):
        gfx = (f"gfxcapture=hwnd={hwnd}:max_framerate={fps}:capture_cursor=0,hwdownload,format=bgra,"
               f"fps={fps},crop=trunc(iw/2)*2:trunc(ih/2)*2:0:0")
        proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-init_hw_device", "d3d11va", "-filter_complex", gfx,
                                 "-t", f"{seconds:.2f}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16",
                                 "-pix_fmt", "yuv420p", "-g", str(fps), raw])
        if wait_first_frame(proc, raw):
            print(f"  window {w}x{h} (hwnd {hwnd}), Windows Graphics Capture")
            return proc
        proc.kill()
        proc.wait()
        if os.path.exists(raw):
            os.remove(raw)
        print("  gfxcapture delivered no frame in 8 s: falling back to ddagrab (FF_CLIP_GRAB=ddagrab starts there)")
    mons = win_monitors()
    idx = monitor
    if idx is None:
        idx = next((k for k, m in enumerate(mons) if m[0] <= x < m[2] and m[1] <= y < m[3]), 0)
    left, top, right, bottom = mons[idx][0], mons[idx][1], mons[idx][2], mons[idx][3]
    if x < left or y < top or x + w > right or y + h > bottom:
        # ddagrab cannot grab past its monitor's edge; it hung on a 1920x1080 window on a 1920x1080 monitor (w1065)
        sys.exit(f"record_clip: the window's client area {w}x{h} at ({x},{y}) does not fit monitor {idx} "
                 f"({right - left}x{bottom - top} at ({left},{top})). Use a smaller window, or record the game's own "
                 "frames (-ffFeelFrames; project-memory beast-clip-capture-and-slot-launch-traps, items 1 and 12).")
    w, h = w & ~1, h & ~1
    grab = (f"ddagrab=output_idx={idx}:framerate={fps}:draw_mouse=0:"
            f"offset_x={x - left}:offset_y={y - top}:video_size={w}x{h}")
    if encoder_works("h264_nvenc"):
        enc = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "16", "-b:v", "0"]
    else:
        grab += ",hwdownload,format=bgra"
        enc = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "16"]
    print(f"  window {w}x{h} at ({x},{y}), monitor {idx}")
    if grab_mode != "gdigrab":
        proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-init_hw_device", "d3d11va", "-filter_complex", grab,
                                 "-t", f"{seconds:.2f}", *enc, "-g", str(fps), raw])
        # ddagrab can deliver no frame at all (Desktop Duplication stalled; w1086: an empty raw file for 20 minutes
        # while the recorder waited): the container header is written with the first frame, so an empty file after
        # a few seconds means it is stuck.
        for _ in range(16):
            time.sleep(0.5)
            if os.path.exists(raw) and os.path.getsize(raw) > 0:
                return proc
            if proc.poll() is not None:
                # w1335 (lothdesktop, 2026-10-15): "Desktop duplication access denied" ends ffmpeg at once with no frame
                # (the displays asleep or the session locked). The gdigrab fallback is no answer there: it returned a
                # frozen desktop from the night before. Say so, instead of a CalledProcessError on the empty file.
                sys.exit("record_clip: ddagrab ended with no frame (exit %s; 'Desktop duplication access denied' means the "
                         "displays are asleep or the session is locked, and gdigrab would record a stale picture). Wake the "
                         "display (SKILL.md, the shared-desktop note) or record the game's own frames: -ffFeelProbe <csv> "
                         "-ffFeelFrames <dir> -ffFeelFramesAt <start>+<seconds> (-ffFeelFrames does nothing without "
                         "-ffFeelProbe; SKILL.md, 'The game's own frames')." % proc.returncode)
        proc.kill()
        proc.wait()
        print("  ddagrab delivered no frame in 8 s: falling back to gdigrab (set FF_CLIP_GRAB=gdigrab to start there)")
    return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "gdigrab", "-framerate", str(fps), "-draw_mouse", "0",
                             "-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}", "-i", "desktop",
                             "-t", f"{seconds:.2f}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16",
                             "-g", str(fps), raw])


# ------------------------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description="Record a short 60 fps clip of the running game while an effect plays.")
    tgt = ap.add_mutually_exclusive_group(required=True)
    tgt.add_argument("--player", action="store_true", help="the built player this worker launched (player_slots.py mine; w1856)")
    tgt.add_argument("--unity", nargs="?", const="", metavar="PROJECT",
                     help="the Unity editor open on PROJECT (default: this git checkout)")
    tgt.add_argument("--pid", type=int, help="any process id with a game window")
    ap.add_argument("--effect", choices=sorted(EFFECTS), help="a named effect: set it up and fire it over the agent channel")
    ap.add_argument("--do", action="append", default=[], help="ffauto command to send at --lead (repeatable)")
    ap.add_argument("--pre", action="append", default=[], help="ffauto command to run (and wait on) before recording")
    ap.add_argument("--name", help="clip name (default: the effect, or 'clip')")
    ap.add_argument("--seconds", type=float, help="clip length (default: the effect's, or 4)")
    ap.add_argument("--lead", type=float, default=1.0, help="seconds recorded before the effect fires (default 1)")
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--out", help="output folder (default <tmp>/vfx_clips)")
    ap.add_argument("--crop", help="W:H:X:Y crop in recorded pixels, e.g. the editor's Game view")
    ap.add_argument("--monitor", type=int, help="Windows: ddagrab output index, if the guess is wrong")
    ap.add_argument("--review", help="the intended look, in words: run watch_video --mode vfx on the clip")
    ap.add_argument("--brief", help="the intended look, as a file: run watch_video --mode vfx on the clip")
    ap.add_argument("--compare", help="an earlier (before / approved) clip for watch_video to compare against")
    ap.add_argument("--bench-wait", type=float, metavar="SECONDS",
                    help="while another worker's timed run holds this machine's bench lock, wait up to this long "
                         "(default $FF_BENCH_WAIT_S, else 0: refuse at once, exit 76; w1750)")
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("record_clip: needs ffmpeg on PATH")
    bench_gate(args.bench_wait)

    pid = args.pid or (player_pid() if args.player else unity_pid(args.unity or repo_root()))
    eff = EFFECTS.get(args.effect, {})
    name = args.name or args.effect or "clip"
    seconds = args.seconds or eff.get("seconds", 4.0)
    out_dir = args.out or os.path.join(tempfile.gettempdir(), "vfx_clips")
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    final = os.path.join(out_dir, f"{name}-{stamp}.mp4")
    raw = os.path.join(out_dir, f".{name}-{stamp}.raw" + (".mkv" if WIN else ".mov"))

    ch = Channel.find(pid)
    pre = [*eff.get("pre", []), *args.pre]
    do = [*eff.get("do", []), *args.do]
    if (pre or do) and ch is None:
        sys.exit(f"record_clip: pid {pid} has no agent channel session (AgentControl/session-{pid}.json). "
                 "Launch the player with -ffAgentControl true -ffAgentControlDev true, or record without "
                 "--effect/--do and fire the effect yourself (MCP) when RECORDING prints.")
    xz = ch.player_xz() if ch and any("{" in c for c in pre + do) else None
    for c in pre:
        print(f"  pre: {c}")
        ch.cmd(fill(c, xz), wait=True)

    print(f"recording pid {pid} for {seconds:.1f} s at {args.fps} fps -> {final}")
    if MAC:
        rec = subprocess.Popen([mac_recorder(), str(pid), raw, f"{seconds:.2f}", str(args.fps)],
                               stdout=subprocess.PIPE, text=True)
        for line in rec.stdout:
            print("  " + line.rstrip())
            if line.startswith("RECORDING"):
                break
        else:
            sys.exit("record_clip: the recorder stopped before its first frame (Screen Recording permission?)")
        threading.Thread(target=lambda: [print("  " + l.rstrip()) for l in rec.stdout], daemon=True).start()
    elif WIN:
        rec = start_windows(pid, raw, seconds, args.fps, args.monitor)
        time.sleep(0.5)
        print("RECORDING")
    else:
        sys.exit("record_clip: macOS and Windows only")
    sys.stdout.flush()
    t_rec = time.time()
    time.sleep(args.lead)
    fired = time.time() - t_rec
    for c in do:
        print(f"  fire: {c}")
        ch.cmd(fill(c, xz))
    try:
        rec.wait(timeout=seconds + 30)
    except subprocess.TimeoutExpired:
        # Desktop duplication delivers no frames while the display sleeps (BEAST w139, lothdesktop w1065).
        rec.kill()
        sys.exit("record_clip: the recorder got no frames in time (display asleep or locked?). Record the game's "
                 "own frames instead: -ffFeelFrames (project-memory beast-clip-capture-and-slot-launch-traps, items "
                 "1 and 12).")
    if not os.path.exists(raw):
        sys.exit("record_clip: the recorder wrote nothing")
    # constant 60 fps H.264 (a frame the game did not redraw becomes a repeat: watch_video counts them)
    vf = [f"fps={args.fps}"] + ([f"crop={args.crop}"] if args.crop else []) + ["format=yuv420p"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-vf", ",".join(vf), "-c:v", "libx264",
                    "-preset", "medium", "-crf", "16", "-an", "-movflags", "+faststart", final], check=True)
    os.remove(raw)
    # the fire time lets watch_video anchor the effect (a moving camera fools a blind estimate). With no
    # --do/--effect, the caller fires it: the lead is when RECORDING was printed plus --lead.
    json.dump({"fired_at": round(fired, 3), "effect": name, "commands": do, "pid": pid, "fps": args.fps,
               "seconds": seconds, "fired_by": "record_clip" if do else "caller, at about --lead"},
              open(final[:-4] + ".json", "w", encoding="utf-8"), indent=1)
    print(f"clip: {final} (effect fired at {fired:.2f} s)")
    if args.review or args.brief or args.compare:
        brief = args.brief
        if args.review:
            brief = os.path.join(out_dir, f"{name}-{stamp}.look.md")
            open(brief, "w", encoding="utf-8").write(
                f"Effect: {name}. {eff.get('about', '')}\n\nIntended look:\n{args.review}\n")
        wv = os.path.join(HERE, "watch_video.py")
        cmd = ["uv", "run", "--quiet", "--script", wv, final, "--mode", "vfx", "--out", final[:-4] + "_review"]
        cmd += ["--brief", brief] if brief else []
        cmd += ["--compare", args.compare] if args.compare else []
        sys.exit(subprocess.run(cmd).returncode)


if __name__ == "__main__":
    main()
