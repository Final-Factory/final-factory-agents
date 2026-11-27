"""Windows only (w6369). Launch an ffu window in a new game, drive keys and clicks, and capture its client rect by
Desktop Duplication (dxcam) on a 60 Hz grid piped to ffmpeg, plus the speakers' loopback (soundcard), on one
perf_counter clock, so picture and sound can be timed against each other (subtitles against voice, an effect against
its sound). Run: uv run -q --no-project --with soundcard --with soundfile --with numpy --with dxcam
--with opencv-python-headless python av_capture.py OUT SECS KEYPLAN [ffu args...]
Env: FFU_EXE (your copied ffu-wNNN.exe), FFU_LOOK (looks/ffu.look), FFU_SETTINGS_FILE (optional).
KEYPLAN: comma list of t:KEY:holdms (t s after capture start), clickXxY, or clickskip (the objectives' Skip button,
found by its fill colour, since it moves with the title's line count). AUTO_T=<s>: from then on, press Skip each time no
subtitle has shown for 1.2 s, to walk the tutorial to a later beat without cutting a voice; stops at a two-row card and
saves still-two-row.png losslessly. Output: video.mp4, audio.wav, amarks.npy (sample count, capture time) and cap.json.
The audio sample at capture time t is np.interp(t, amarks[:,1], amarks[:,0]).
"""
import sys
sys.coinit_flags = 0
import ctypes, json, os, subprocess, threading, time
import numpy as np, soundcard as sc, soundfile as sf, dxcam

out, secs, plan = sys.argv[1], float(sys.argv[2]), sys.argv[3]
extra = sys.argv[4:]
os.makedirs(out, exist_ok=True)
env = dict(os.environ, FFU_CRASH_DIR=os.path.join(out, "crashes"))
ctypes.windll.shcore.SetProcessDpiAwareness(2)
u32 = ctypes.windll.user32
clog = open(os.path.join(out, "client.log"), "w")
p = subprocess.Popen([os.environ["FFU_EXE"], "--new-game", "7", "--name", "capture", "--look",
                      os.environ["FFU_LOOK"], "--seconds", str(int(secs + 8))] + extra,
                     cwd=out, env=env, stdout=clog, stderr=subprocess.STDOUT)
# find its window
hwnd = 0
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
def find():
    found = []
    def cb(h, _):
        pid = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == p.pid and u32.IsWindowVisible(h):
            found.append(h)
        return True
    u32.EnumWindows(EnumProc(cb), 0)
    return found[0] if found else 0
for _ in range(200):
    hwnd = find()
    if hwnd:
        break
    time.sleep(0.1)
time.sleep(2.5)
u32.SetForegroundWindow(hwnd)
time.sleep(0.5)
class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
class PT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
rc, pt = RECT(), PT()
u32.GetClientRect(ctypes.c_void_p(hwnd), ctypes.byref(rc))
u32.ClientToScreen(ctypes.c_void_p(hwnd), ctypes.byref(pt))
W, H = rc.r - rc.l, rc.b - rc.t
X0, Y0 = max(0, pt.x), max(0, pt.y)
print("client rect", X0, Y0, W, H, flush=True)

rate = 48000
spk = sc.default_speaker()
mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
achunks, amarks, stop = [], [], threading.Event()
def audio():
    with mic.recorder(samplerate=rate, channels=2, blocksize=480) as r:
        n = 0
        while not stop.is_set():
            d = r.record(numframes=480)
            n += len(d)
            achunks.append(d)
            amarks.append((n, time.perf_counter()))
at = threading.Thread(target=audio, daemon=True)
at.start()
time.sleep(0.3)

cam = dxcam.create(output_color="RGB")

ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                       "-s", f"{W}x{H}", "-r", "60", "-i", "-", "-c:v", "libx264", "-preset", "ultrafast", "-qp", "20",
                       "-pix_fmt", "yuv420p", os.path.join(out, "video.mp4")], stdin=subprocess.PIPE)
keys = []
skips = []
for k in [x for x in plan.split(",") if x]:
    t, key, hold = k.split(":")
    keys.append([float(t), key, int(hold), False, False])
def key_ev(key, up):
    vk = ord(key.upper()[0])
    if key == "clickskip":
        if up:
            u32.mouse_event(4, 0, 0, 0, 0); return
        col = last[100:500, 120].astype(int) if last is not None else None
        ys = [] if col is None else [i + 100 for i, c in enumerate(col) if 45 <= c[1] <= 70 and 75 <= c[2] <= 110 and c[0] < 40]
        if not ys:
            skips.append((time.perf_counter() - t0, -1)); return
        y = (ys[0] + ys[-1]) // 2
        skips.append((time.perf_counter() - t0, y))
        u32.SetCursorPos(X0 + 120, Y0 + y); u32.mouse_event(2, 0, 0, 0, 0)
        return
    if key.startswith("click"):
        x, y = key[5:].split("x")
        if not up:
            u32.SetCursorPos(X0 + int(x), Y0 + int(y))
        u32.mouse_event(4 if up else 2, 0, 0, 0, 0)
        return
    u32.keybd_event(vk, u32.MapVirtualKeyW(vk, 0), 2 if up else 0, 0)

AUTO_T = float(os.environ["AUTO_T"]) if os.environ.get("AUTO_T") else None
AUTO_MAX = int(os.environ.get("AUTO_MAX", "200"))
quiet_since, last_skip, auto_n, two_row, saved_png = 0.0, 0.0, 0, None, False
t0 = time.perf_counter()
last, frames = None, []
i = 0
while True:
    tick = t0 + i / 60
    now = time.perf_counter()
    if now - t0 > secs or p.poll() is not None or (two_row is not None and now - t0 - two_row > 12):
        break
    if now < tick:
        time.sleep(max(0, tick - now - 0.002))
        while time.perf_counter() < tick:
            pass
    for k in keys:
        rel = time.perf_counter() - t0
        if not k[3] and rel >= k[0]:
            u32.SetForegroundWindow(hwnd); key_ev(k[1], False); k[3] = True
        if k[3] and not k[4] and rel >= k[0] + k[2] / 1000:
            key_ev(k[1], True); k[4] = True
    # auto skip: from AUTO_T, Skip only once no subtitle has shown for 1.2 s; stop for good at a two-row card
    if AUTO_T is not None and last is not None and i % 6 == 0:
        rel = time.perf_counter() - t0
        band = last[680:800, 300:1620].astype(np.int16)
        wh = (band.min(axis=2) > 150) & (np.abs(band[..., 0] - band[..., 2]) < 30)
        rows = np.nonzero(wh.sum(axis=1) > 3)[0]
        if len(rows):
            quiet_since = rel
            if rows[0] + 680 < 765 and two_row is None:
                two_row = rel
                print("two-row card at", round(rel, 2), "rows", rows[0] + 680, rows[-1] + 680, flush=True)
        if (two_row is None and rel >= AUTO_T and rel - quiet_since > 1.2 and rel - last_skip > 0.7
                and auto_n < AUTO_MAX):
            key_ev("clickskip", False); key_ev("clickskip", True)
            last_skip = rel; auto_n += 1
    if two_row is not None and not saved_png and time.perf_counter() - t0 - two_row > 0.8 and last is not None:
        import cv2
        cv2.imwrite(os.path.join(out, "still-two-row.png"), last[:, :, ::-1]); saved_png = True
        print("still saved", flush=True)
    f = cam.grab(region=(X0, Y0, X0 + W, Y0 + H))
    tg = time.perf_counter()
    new = f is not None
    if new:
        last = f
    if last is not None:
        ff.stdin.write(last.tobytes())
        frames.append((i, tg - t0, new))
        i += 1
    else:
        t0 = time.perf_counter()  # wait for the first frame
ff.stdin.close(); ff.wait()
stop.set(); at.join(2)
data = np.concatenate(achunks)
sf.write(os.path.join(out, "audio.wav"), data, rate)
marks = np.array(amarks)
# time of sample n ~ fit of perf_counter at chunk ends (minus t0)
a, b = np.polyfit(marks[:, 0], marks[:, 1] - t0, 1)
np.save(os.path.join(out, "amarks.npy"), np.column_stack([marks[:, 0], marks[:, 1] - t0]))
json.dump({"frames": frames, "audio_fit": [a, b], "audio_rate": rate, "skips": skips, "two_row": two_row, "auto_n": auto_n, "fg": u32.GetForegroundWindow() == hwnd},
          open(os.path.join(out, "cap.json"), "w"))
print("frames", len(frames), "new", sum(1 for f in frames if f[2]), "audio s", len(data) / rate,
      "audio t(0)", b, "slope*rate", a * rate)
try:
    p.wait(timeout=20)
except subprocess.TimeoutExpired:
    p.terminate()
