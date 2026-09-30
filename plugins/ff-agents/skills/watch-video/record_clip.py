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
it is covered. Windows: ffmpeg ddagrab (Desktop Duplication) of the window's client area; the
window must be visible on a monitor.
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


def player_pid():
    """A running built Final Factory player (the newest, if several)."""
    if WIN:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-Process | Where-Object { $_.ProcessName -like 'FinalFactory*' } | "
                              "Sort-Object StartTime | ForEach-Object { $_.Id }"], capture_output=True, text=True).stdout
        pids = [int(x) for x in out.split()]
    else:
        out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
        pids = [int(l.split()[0]) for l in out.splitlines()
                if re.search(r"/FinalFactory[^/]*\.app/Contents/MacOS/", l) or re.search(r"FinalFactory\S*\.x86_64", l)]
    if not pids:
        sys.exit("record_clip: no running FinalFactory player (start one from the slot pool first)")
    return pids[-1]


def repo_root():
    try:
        return subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return os.getcwd()


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


def win_client_rect(pid):
    """Screen rect (x, y, w, h) of the pid's largest visible window's client area, in pixels."""
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
            found.append((r.right * r.bottom, pt.x, pt.y, r.right, r.bottom))
        return True
    user32.EnumWindows(cb, 0)
    if not found:
        sys.exit(f"record_clip: no visible window for pid {pid}")
    _, x, y, w, h = max(found)
    return x, y, w, h


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


def start_windows(pid, raw, seconds, fps, monitor):
    x, y, w, h = win_client_rect(pid)
    mons = win_monitors()
    idx = monitor
    if idx is None:
        idx = next((k for k, m in enumerate(mons) if m[0] <= x < m[2] and m[1] <= y < m[3]), 0)
    left, top = mons[idx][0], mons[idx][1]
    w, h = w & ~1, h & ~1
    grab = (f"ddagrab=output_idx={idx}:framerate={fps}:draw_mouse=0:"
            f"offset_x={x - left}:offset_y={y - top}:video_size={w}x{h}")
    if ffmpeg_has("h264_nvenc"):
        enc = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "16", "-b:v", "0"]
    else:
        grab += ",hwdownload,format=bgra"
        enc = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "16"]
    print(f"  window {w}x{h} at ({x},{y}), monitor {idx}")
    return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-init_hw_device", "d3d11va", "-filter_complex", grab,
                             "-t", f"{seconds:.2f}", *enc, "-g", str(fps), raw])


# ------------------------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description="Record a short 60 fps clip of the running game while an effect plays.")
    tgt = ap.add_mutually_exclusive_group(required=True)
    tgt.add_argument("--player", action="store_true", help="the running built FinalFactory player")
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
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("record_clip: needs ffmpeg on PATH")

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
    rec.wait()
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
