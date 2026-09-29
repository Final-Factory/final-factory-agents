# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = [
#   "numpy",
#   "opencv-python-headless",
#   "librosa",
#   "soundfile",
#   "scenedetect",
#   "pillow",
# ]
# ///
"""watch_video: a time-stamped review of a video (trailer, capture, gameplay clip), with sound.

    uv run watch_video.py <video> [--ref <video|report.json|steam> ...] [--brief <file>] [--out <dir>]

Writes <out>/report.md (flags, per-shot table, music, reference comparison), report.json,
timeline*.png (waveform, beats, onsets, cuts, motion, loudness on one time axis) and one contact
sheet per shot (sheets/shot_NN.jpg, frames at --sheet-fps with timestamps). The calling agent
reads report.md, then LOOKS at the timeline and the sheets to judge what the numbers cannot.

Only ffmpeg/ffprobe on PATH and uv are needed; uv installs the Python packages above.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import numpy as np

VERSION = "1.0"
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "watch_video")

# Thresholds. Calibrated on the Final Factory trailer cuts (v1-v4) and the three official Steam
# trailers (see SKILL.md "Calibration"). Motion is in % of frame width per second.
STILL_CAM = 2.0         # camera slower than this ...
STILL_ACT = 0.9         # ... and on-screen change below this (mean abs diff after camera compensation, 0-255)
LINGER_MIN = 0.6        # a still stretch this long (s) inside a shot is flagged
TAIL_DROP = 0.35        # tail motion below this fraction of the shot's own peak = "motion stopped, shot holds"
REPEAT_DIFF = 0.25      # frame-to-frame mean abs diff below this = a repeated (duplicate) frame
MATCH_MIN = 0.97        # window alignment score for 'this is that track here' (true 0.99+, a similar track ~0.94)
ON_BEAT_MS = 60         # a cut within this of a beat counts as on the beat
OFF_BEAT_FRAC = 0.2     # a cut is flagged off the beat only past this share of a beat (tracker jitter is ~50 ms)
SIMILAR_SHOT = 0.15     # share of ORB keypoints matching under one camera move: non-adjacent shots = reused view
JUMP_CUT = 0.15         # the same across a cut = jump cut (same view, time skipped)
CLUMP_SPREAD = 0.15     # action in at most this share of the frame's cells ...
CLUMP_FOCUS = 0.18      # ... with this share of all change in its busiest 3% = everything happens in one spot
TIGHT_SCALE = 14.0      # median detail size (% of frame width) at or above this = framed tight (v1 calibration)


# ----------------------------------------------------------------------------------------- utils

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]).stdout
    d = json.loads(out)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        sys.exit(f"no video stream in {path}")
    num, den = (int(x) for x in v.get("avg_frame_rate", v["r_frame_rate"]).split("/"))
    fps = num / den if den else 30.0
    if fps <= 0 or fps > 240:
        num, den = (int(x) for x in v["r_frame_rate"].split("/"))
        fps = num / den
    dur = float(d["format"].get("duration") or v.get("duration") or 0)
    return {"width": int(v["width"]), "height": int(v["height"]), "fps": fps, "duration": dur,
            "has_audio": a is not None, "vcodec": v.get("codec_name"),
            "audio_rate": int(a["sample_rate"]) if a else None}


def fmt_t(t):
    m, s = divmod(max(t, 0.0), 60)
    return f"{int(m)}:{s:05.2f}"


def ffmpeg_frames(path, w, h, fps=None, gray=False):
    """Yield decoded frames (h, w[, 3]) uint8, resampled to `fps` if given."""
    vf = (f"fps={fps}," if fps else "") + f"scale={w}:{h}:flags=area"
    pix = "gray" if gray else "rgb24"
    ch = 1 if gray else 3
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-an", "-vf", vf, "-f", "rawvideo",
                          "-pix_fmt", pix, "-"], stdout=subprocess.PIPE)
    n = w * h * ch
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        a = np.frombuffer(buf, np.uint8)
        yield a.reshape(h, w) if gray else a.reshape(h, w, 3)
    p.stdout.close()
    p.wait()


def even(x):
    return int(round(x / 2)) * 2


# ------------------------------------------------------------------------------- video signals

GRID = (16, 9)   # cells for the action-concentration map


def video_signals(path, info, sfps, max_fps=60):
    """One decode pass. Per frame: repeat diff, camera pan (x, y), zoom rate, camera-compensated
    on-screen change, brightness, change per grid cell. Also keeps colour frames at `sfps` (the first
    frame at or after each k/sfps, so a sample never comes from the next shot)."""
    import cv2
    fps = info["fps"]
    step_fps = None if fps <= max_fps + 0.5 else max_fps
    afps = step_fps or fps
    W = 320
    H = even(W * info["height"] / info["width"])
    CW = 480
    CH = even(CW * info["height"] / info["width"])
    prev = None
    rows = []
    cells = []
    samples = []
    cx, cy = W / 2, H / 2
    for n, rgb in enumerate(ffmpeg_frames(path, CW, CH, step_fps)):
        if n / afps >= len(samples) / sfps - 0.5 / afps:
            samples.append(rgb.copy())
        g = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (W, H), interpolation=cv2.INTER_AREA)
        cell = np.zeros(GRID[0] * GRID[1])
        r = {"diff": 0.0, "tx": 0.0, "ty": 0.0, "zoom": 0.0, "act": 0.0, "luma": float(g.mean()), "track": 0}
        if prev is not None:
            r["diff"] = float(np.abs(g.astype(np.int16) - prev.astype(np.int16)).mean())
            pts = cv2.goodFeaturesToTrack(prev, maxCorners=300, qualityLevel=0.01, minDistance=6)
            M = None
            if pts is not None and len(pts) >= 12:
                nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, g, pts, None, winSize=(21, 21), maxLevel=3)
                ok = st.reshape(-1) == 1
                if ok.sum() >= 10:
                    M, inl = cv2.estimateAffinePartial2D(pts[ok], nxt[ok], method=cv2.RANSAC,
                                                         ransacReprojThreshold=1.5)
                    r["track"] = int(ok.sum())
            if M is not None:
                s = math.hypot(M[0, 0], M[1, 0])
                # translation of the frame centre, sign flipped: the camera moves opposite the content
                ccx = M[0, 0] * cx + M[0, 1] * cy + M[0, 2] - cx
                ccy = M[1, 0] * cx + M[1, 1] * cy + M[1, 2] - cy
                r["tx"], r["ty"], r["zoom"] = float(-ccx), float(-ccy), float(s - 1.0)
                warped = cv2.warpAffine(prev, M, (W, H), borderMode=cv2.BORDER_REPLICATE)
                m = 8  # ignore borders the warp had to invent
                ad = np.abs(g.astype(np.int16) - warped.astype(np.int16)).astype(np.float32)
                ad[:m] = ad[-m:] = 0
                ad[:, :m] = ad[:, -m:] = 0
                r["act"] = float(ad[m:-m, m:-m].mean())
                cell = cv2.resize(ad, GRID, interpolation=cv2.INTER_AREA).ravel()
            else:
                r["act"] = r["diff"]
        rows.append(r)
        cells.append(cell)
        prev = g
    n = len(rows)
    arr = {k: np.array([r[k] for r in rows], float) for k in rows[0]} if rows else {}
    # to human units: camera speed in % of frame width per second, zoom in % per second
    arr["cam_x"] = arr["tx"] / W * afps * 100
    arr["cam_y"] = arr["ty"] / W * afps * 100
    arr["cam"] = np.hypot(arr["cam_x"], arr["cam_y"])
    arr["zoom_rate"] = arr["zoom"] * afps * 100
    arr["t"] = np.arange(n) / afps
    arr["fps"] = afps
    arr["cells"] = np.array(cells, np.float32)
    return arr, samples


def smooth(x, n):
    if n <= 1 or len(x) < n:
        return x
    k = np.ones(n) / n
    return np.convolve(np.pad(x, (n // 2, n - 1 - n // 2), mode="edge"), k, mode="valid")


def detect_cuts(path, info, sig):
    """Picture cuts: PySceneDetect's adaptive detector, cross-checked with our own frame diff."""
    cuts = []
    try:
        from scenedetect import detect, AdaptiveDetector
        scenes = detect(path, AdaptiveDetector(min_scene_len=int(info["fps"] * 0.25)), show_progress=False)
        cuts = [getattr(s[0], 'seconds', None) or s[0].get_seconds() for s in scenes[1:]]
    except Exception as e:  # pragma: no cover - scenedetect optional at runtime
        print(f"  scenedetect failed ({e}); using the frame-diff detector only", file=sys.stderr)
    # our own: a one-frame difference spike far above the frames around it. It catches the cuts
    # a content detector misses: a jump inside near-static footage of the same scene.
    d = sig["diff"]
    own = []
    for i in range(1, len(d) - 1):
        nb = np.r_[d[max(1, i - 6):i], d[i + 1:i + 7]]
        if len(nb) < 4:
            continue
        base = float(np.median(nb))
        if d[i] > 3.0 and d[i] > 6.0 * max(base, 0.3) and d[i] >= d[i - 1] and d[i] >= d[i + 1]:
            own.append(sig["t"][i])
    merged = sorted(cuts)
    for t in own:
        if all(abs(t - c) > 0.25 for c in merged):
            merged.append(t)
    merged.sort()
    # collapse detections closer than 0.25 s (dissolves and whips trigger twice): keep the frame with
    # the biggest one-frame jump, i.e. the hard cut, not the start of a whip smear
    jump = lambda t: float(d[min(len(d) - 1, max(0, int(round(t * sig["fps"]))))])
    out, cluster = [], []
    for t in merged + [1e9]:
        if cluster and t - cluster[-1] > 0.25:
            out.append(max(cluster, key=jump)); cluster = []
        cluster.append(t)
    # snap each cut to the biggest one-frame jump within 0.15 s (a whip's smear starts before the cut)
    fps = sig["fps"]
    w = int(round(0.15 * fps))
    snapped = []
    for t in out:
        i = int(round(t * fps))
        lo, hi = max(1, i - w), min(len(d), i + w + 1)
        if hi > lo:
            j = lo + int(np.argmax(d[lo:hi]))
            if d[j] > 1.5 * d[min(max(i, 0), len(d) - 1)]:
                t = sig["t"][j]
        snapped.append(float(t))
    return [round(t, 3) for t in snapped if 0.2 < t < info["duration"] - 0.2]


# ----------------------------------------------------------------------------- sampled frames

def readability(frame):
    """How much the frame shows: edge density, count of distinct objects, largest object's share."""
    import cv2
    g = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    e = cv2.Canny(g, 60, 160)
    dens = float((e > 0).mean())
    m = cv2.dilate(e, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    area = stats[1:, cv2.CC_STAT_AREA].astype(float) / g.size if n > 1 else np.zeros(0)
    objs = int((area > 0.0004).sum())
    big = float(area.max()) if len(area) else 0.0
    # characteristic detail size: median wavelength of the image's spectral energy, % of width
    f = np.abs(np.fft.rfft2(g.astype(float) - g.mean())) ** 2
    fy = np.fft.fftfreq(g.shape[0])[:, None] * g.shape[0] / g.shape[1]
    fx = np.fft.rfftfreq(g.shape[1])[None, :]
    rad = np.hypot(fx, fy).ravel()
    w = f.ravel()
    o = np.argsort(rad)
    cw = np.cumsum(w[o])
    med = rad[o][np.searchsorted(cw, cw[-1] * 0.5)] if cw[-1] > 0 else 0.5
    scale = float(min(100.0, 100.0 / (med * g.shape[1]) if med > 0 else 100.0))
    return {"edges": dens, "objects": objs, "largest": big, "scale": scale, "luma": float(g.mean())}


def thumb_vec(frame):
    """ORB keypoints of a frame, for 'same scene?' checks (jump cuts, reused footage)."""
    import cv2
    g = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(nfeatures=500, fastThreshold=12)
    kp, des = orb.detectAndCompute(g, None)
    return (np.float32([k.pt for k in kp]) if kp else np.zeros((0, 2), np.float32), des)


def similarity(a, b):
    """0..1: share of keypoints that match under one camera move (a similarity transform).
    Near 1 = the same view; ~0 = a different scene. Dark, empty frames score 0 (nothing to match)."""
    import cv2
    (pa, da), (pb, db) = a, b
    if da is None or db is None or len(pa) < 20 or len(pb) < 20:
        return 0.0
    m = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2)
    good = [x[0] for x in m if len(x) == 2 and x[0].distance < 0.75 * x[1].distance]
    if len(good) < 12:
        return 0.0
    src = np.float32([pa[g.queryIdx] for g in good])
    dst = np.float32([pb[g.trainIdx] for g in good])
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0)
    if M is None:
        return 0.0
    return float(inl.sum() / min(len(pa), len(pb)))


# ------------------------------------------------------------------------------------- audio

def audio_signals(path, info, bpm=None):
    if not info["has_audio"]:
        return None
    import librosa
    sr = 22050
    raw = run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]).stdout
    y = np.frombuffer(raw, np.float32).copy()
    if len(y) < sr:
        return None
    hop = 512
    g = beat_grid(y, sr, hop, bpm)
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    on_fr = librosa.onset.onset_detect(onset_envelope=onset, sr=sr, hop_length=hop, backtrack=False)
    on_t = librosa.frames_to_time(on_fr, sr=sr, hop_length=hop)
    on_s = onset[on_fr] / max(onset.max(), 1e-6)
    ft = librosa.frames_to_time(np.arange(len(onset)), sr=sr, hop_length=hop)
    # timbre/harmony novelty: a checkerboard kernel over the MFCC+chroma self-similarity (~1 s)
    feat = np.vstack([librosa.util.normalize(librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13), axis=1),
                      librosa.feature.chroma_stft(y=y, sr=sr, hop_length=hop)])
    feat = librosa.util.normalize(feat, axis=0)
    nov = checkerboard_novelty(feat, int(0.75 * sr / hop))
    # peak envelope for the waveform row
    n = 4000
    seg = max(1, len(y) // n)
    env = np.abs(y[: seg * (len(y) // seg)]).reshape(-1, seg).max(axis=1)
    return {"sr": sr, "dur": len(y) / sr, "tempo": g["tempo"], "beats": g["beats"], "onsets": on_t,
            "onset_strength": on_s, "env": env, "env_dt": seg / sr, "rms": g["rms"][:len(ft)], "ft": ft,
            "novelty": nov, "flux": onset / max(onset.max(), 1e-6), "bar_phase": g["bar_phase"], "grid": g}


def checkerboard_novelty(feat, L):
    n = feat.shape[1]
    if n < 4 * L:
        return np.zeros(n)
    # sub-sample for speed, then interpolate back
    step = max(1, L // 8)
    F = feat[:, ::step]
    Ls = max(2, L // step)
    S = F.T @ F
    g = np.outer(np.hanning(2 * Ls), np.hanning(2 * Ls))
    k = np.sign(np.outer(np.r_[-np.ones(Ls), np.ones(Ls)], np.r_[-np.ones(Ls), np.ones(Ls)])) * g
    m = S.shape[0]
    out = np.zeros(m)
    Sp = np.pad(S, Ls, mode="edge")
    for i in range(m):
        out[i] = (Sp[i:i + 2 * Ls, i:i + 2 * Ls] * k).sum()
    out = np.maximum(out, 0)
    out /= max(out.max(), 1e-6)
    return np.interp(np.arange(n), np.arange(m) * step, out)


def loudness(path, info):
    """EBU R128: integrated, range, true peak, and the short-term (3 s) curve every 0.1 s."""
    if not info["has_audio"]:
        return None
    p = subprocess.run(["ffmpeg", "-nostats", "-i", path, "-vn", "-af",
                        "ebur128=metadata=1:peak=true,ametadata=print:key=lavfi.r128.S:file=-",
                        "-f", "null", "-"], capture_output=True, text=True)
    curve, t = [], None
    for line in p.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1))
        elif line.startswith("lavfi.r128.S=") and t is not None:
            v = float(line.split("=", 1)[1])
            if v > -70:
                curve.append((t, v))
    summ = p.stderr[p.stderr.rfind("Summary:"):]
    g = lambda k: (lambda m: float(m.group(1)) if m else None)(re.search(k + r":\s*(-?[\d.]+)", summ))
    return {"integrated": g("I"), "lra": g("LRA"), "true_peak": g("Peak"), "short_term": curve}


# --------------------------------------------------------------------------------- per shot

def moving_mask(sig):
    n = max(1, int(sig["fps"] * 0.25))
    # camera motion = pan plus zoom (a pull-back with no pan is still a moving camera)
    cam, act = smooth(np.hypot(sig["cam"], sig["zoom_rate"]), n), smooth(sig["act"], n)
    return cam, act, (cam > STILL_CAM) | (act > STILL_ACT)


def runs(mask):
    """(start, end) index pairs of True runs."""
    out, s = [], None
    for i, m in enumerate(mask):
        if m and s is None:
            s = i
        elif not m and s is not None:
            out.append((s, i)); s = None
    if s is not None:
        out.append((s, len(mask)))
    return out


def analyse_shots(sig, bounds, flashes):
    fps = sig["fps"]
    t = sig["t"]
    cam_s, act_s, moving = moving_mask(sig)
    shots = []
    for k, (a, b) in enumerate(bounds):
        i0 = int(math.ceil(a * fps)) + 2
        i1 = min(len(t), int(b * fps) - 1)
        s = {"i": k, "start": a, "end": b, "dur": b - a}
        if i1 - i0 < 3:
            s.update(cam=0, act=0, still_runs=[], repeats=0, unique_fps=fps)
            shots.append(s); continue
        cam, act, mov = cam_s[i0:i1], act_s[i0:i1], moving[i0:i1]
        s["cam"] = float(np.median(cam)); s["cam_p90"] = float(np.percentile(cam, 90))
        s["act"] = float(np.median(act)); s["act_p90"] = float(np.percentile(act, 90))
        s["zoom"] = float(np.median(smooth(sig["zoom_rate"][i0:i1], int(fps * 0.25))))
        s["dir"] = (float(np.median(sig["cam_x"][i0:i1])), float(np.median(sig["cam_y"][i0:i1])))
        s["still_frac"] = float(1 - mov.mean())
        # still stretches (ignore frames inside a flash / fade)
        st = []
        for r0, r1 in runs(~mov):
            ta, tb = t[i0 + r0], t[min(i0 + r1, len(t) - 1)]
            if r1 == len(mov):
                tb = b
            if r0 == 0:
                ta = a
            if tb - ta >= LINGER_MIN and not any(fa - 0.2 < ta < fb + 0.2 for fa, fb in flashes):
                st.append((float(ta), float(tb)))
        s["still_runs"] = st
        # motion energy: does it die before the shot ends?
        e = cam / STILL_CAM + act / STILL_ACT
        peak = float(np.percentile(e, 90))
        tail_n = max(3, int(min(1.0, 0.25 * s["dur"]) * fps))
        tail = float(e[-tail_n:].mean())
        s["tail_ratio"] = tail / peak if peak > 0 else 1.0
        live = np.nonzero(e >= 0.5 * peak)[0]
        s["motion_ends"] = float(t[i0 + live[-1]]) if len(live) else a
        # where the action is: share of all camera-compensated change inside the busiest 3% of the frame
        C = sig["cells"][i0:i1].sum(axis=0)
        if C.sum() > 0:
            top = np.sort(C)[::-1]
            k = max(1, int(round(0.03 * len(C))))
            s["focus"] = float(top[:k].sum() / C.sum())
            s["spread"] = float((C >= 0.2 * top[0]).mean())
        # repeated frames between moving frames (a dropped frame shows as a stutter)
        d = sig["diff"][i0:i1]
        rep = (d < REPEAT_DIFF) & (np.r_[0, d[:-1]] > 1.0) | (d < REPEAT_DIFF) & (np.r_[d[1:], 0] > 1.0)
        s["repeats"] = int(rep.sum())
        s["unique_fps"] = float(fps * (1 - (d < REPEAT_DIFF).mean())) if mov.mean() > 0.5 else None
        shots.append(s)
    return shots


def add_readability(shots, frames, sfps):
    for s in shots:
        fr = [frames[j] for j in range(len(frames)) if s["start"] + 0.1 <= j / sfps < s["end"] - 0.05]
        s["frames"] = [j for j in range(len(frames)) if s["start"] + 0.1 <= j / sfps < s["end"] - 0.05]
        if not fr:
            continue
        rd = [readability(f) for f in fr]
        for key in ("edges", "objects", "largest", "scale"):
            s[key] = float(np.median([r[key] for r in rd]))
        pick = [fr[int(len(fr) * q)] for q in (0.15, 0.5, 0.85)]
        s["_thumbs"] = [thumb_vec(f) for f in pick]
        s["_first"], s["_last"] = thumb_vec(fr[0]), thumb_vec(fr[-1])


def flashes_and_fades(sig):
    """White flashes (a short luma spike) and fades through black."""
    L = sig["luma"]
    fps = sig["fps"]
    base = smooth(L, int(fps))
    fl, fd = [], []
    for s, e in runs(L > np.maximum(base + 60, 170)):
        if (e - s) / fps < 0.6:
            # the flash includes its fade back down: extend while the picture is still darkening
            floor = float(L[min(len(L) - 1, e + int(fps)):min(len(L), e + int(1.5 * fps))].min(initial=L[-1]))
            while e < len(L) - 1 and e - s < fps and L[e] > floor + 15 and L[e + 1] <= L[e] + 1:
                e += 1
            fl.append((sig["t"][s], sig["t"][min(e, len(L) - 1)]))
    for s, e in runs(L < 8):
        if (e - s) / fps >= 0.1:
            fd.append((sig["t"][s], sig["t"][min(e, len(L) - 1)]))
    return fl, fd


# ------------------------------------------------------------------------------------ music

def music_analysis(au, cuts, duration, mruns=None, mseams=None, grids=None):
    """Beat grid under the picture, cut-on-beat accuracy, music edits, and how the music ends.
    With the source track(s) (mruns from music_map) the beat grid is the SOURCE's, mapped through
    the edit, and every music edit is exact. Without, the grid is tracked from the mix itself."""
    if au is None:
        return None
    beats, bars = [], []
    if mruns:
        for r in mruns:
            g = grids[r["track"]]
            b = g["beats"] - r["offset"]
            keep = (b >= r["t0"] - 0.03) & (b < r["t1"])
            idx = np.nonzero(keep)[0]
            beats += list(b[idx])
            bars += [None if g["bar_phase"] is None else int((j - g["bar_phase"]) % 4) for j in idx]
        tempo = float(np.median([grids[r["track"]]["tempo"] for r in mruns]))
        src = "source track"
    else:
        beats = list(au["beats"])
        bp = au["bar_phase"]
        bars = [None if bp is None else (j - bp) % 4 for j in range(len(beats))]
        tempo = au["tempo"]
        src = "tracked from the mix"
    beats = np.array(beats)
    period = 60.0 / tempo if tempo > 0 else 0.5
    res = {"tempo": tempo, "period": period, "beats": beats, "bars": bars, "grid_source": src,
           "cuts": [], "seams": [], "map": mruns or []}
    for c in cuts:
        if len(beats) == 0:
            break
        j = int(np.argmin(np.abs(beats - c)))
        dt = c - beats[j]
        ons = au["onsets"][np.abs(au["onsets"] - c) < 0.08]
        res["cuts"].append({"t": c, "beat": j, "offset_ms": dt * 1000, "on_beat": abs(dt) * 1000 <= ON_BEAT_MS,
                            "bar_pos": bars[j], "onset_near": len(ons) > 0})
    if mseams is not None:
        for sm in mseams:
            # the seam is placed from the audio alone; a picture cut within 0.15 s is where it really is
            near = [c for c in cuts if abs(c - sm["t"]) < 0.15]
            if near:
                d = near[0] - sm["t"]
                sm = {**sm, "t": near[0], "out_at": sm["out_at"] + d, "in_at": sm["in_at"] + d}
            gf, gt = grids[sm["from_track"]], grids[sm["to_track"]]
            jo, oo, bo = beat_pos(gf, sm["out_at"])
            ji, oi, bi = beat_pos(gt, sm["in_at"])
            step_db = level_db(gt, sm["in_at"], 0.75) - level_db(gf, sm["out_at"], -0.75)
            on_bar = bo == 0 and bi == 0 and abs(oo) < 0.08 and abs(oi) < 0.08
            bar_s = 4 * 60.0 / gf["tempo"]
            nxt = [x for x in gf.get("sections", []) if x > sm["out_at"] - 0.3]
            prv = [x for x in gt.get("sections", []) if x < sm["in_at"] + 0.3]
            left = (nxt[0] - sm["out_at"]) / bar_s if nxt else None    # bars the cut-off section still had
            into = (sm["in_at"] - prv[-1]) / bar_s if prv else None    # bars into the section we enter
            res["seams"].append({**sm, "out_bar": bo, "in_bar": bi, "out_off_ms": oo * 1000, "in_off_ms": oi * 1000,
                                 "bars_left": left, "bars_into": into,
                                 "on_bar": on_bar, "level_step_db": step_db, "at_cut": bool(near),
                                 "novelty": float(np.interp(sm["t"], au["ft"], au["novelty"])),
                                 "same_track": sm["from_track"] == sm["to_track"], "verified": True})
    else:
        # no source: only a strong timbre/harmony jump right on a picture cut is reported, unverified
        nov, ft = au["novelty"], au["ft"]
        for c in cuts:
            m = (ft > c - 0.15) & (ft < c + 0.15)
            if m.any() and nov[m].max() > 0.6:
                res["seams"].append({"t": c, "novelty": float(nov[m].max()), "verified": False})
    rms, rt = au["rms"], au["ft"][:len(au["rms"])]
    body = float(np.median(rms[rt < duration - 2])) if (rt < duration - 2).any() else float(np.median(rms))
    tail = float(rms[rt > duration - 0.3].mean()) if (rt > duration - 0.3).any() else 0.0
    res["end_level"] = tail / body if body > 0 else 0.0
    return res


# ---------------------------------------------------------------- music edits vs the source track

AUDIO_EXT = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aif", ".aiff", ".opus")


def load_mono(path, sr=22050):
    raw = run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]).stdout
    return np.frombuffer(raw, np.float32).copy()


def mel_feat(y, sr, hop):
    import librosa
    S = librosa.feature.melspectrogram(y=y, sr=sr, hop_length=hop, n_mels=48, fmax=8000)
    L = np.log(S + 1e-6).astype(np.float64)
    return L - L.mean(axis=0)   # per-frame mean removed: loudnorm and fades do not matter


def track_feats(path):
    """Mel features of a source track, cached (a soundtrack folder is ~20 tracks)."""
    st = os.stat(path)
    key = hashlib.sha1(f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime}".encode()).hexdigest()[:16]
    cp = os.path.join(CACHE, "tracks", key + ".npy")
    if os.path.exists(cp):
        return np.load(cp).astype(np.float64)
    F = mel_feat(load_mono(path, 22050), 22050, 512)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    np.save(cp, F.astype(np.float32))
    return F


def best_offsets(A, B, win, step):
    """For each window of A: the best-matching start frame in B and its normalised correlation."""
    n = B.shape[1]
    if n <= win:
        return []
    size = 1 << int(np.ceil(np.log2(n + win)))
    Fb = np.fft.rfft(B, size, axis=1)
    cs = np.cumsum(np.r_[0.0, (B ** 2).sum(axis=0)])
    en = np.sqrt(np.maximum(cs[win:n + 1] - cs[:n - win + 1], 0.0))
    # silent stretches of B have ~0 energy: FFT round-off over ~0 would score them "perfect"
    en = np.maximum(en, 0.05 * float(np.median(en)) + 1e-9)
    out = []
    for s in range(0, A.shape[1] - win, step):
        w = A[:, s:s + win]
        nw = np.sqrt((w ** 2).sum()) + 1e-9
        c = np.fft.irfft(Fb * np.fft.rfft(w[:, ::-1], size, axis=1), size, axis=1).sum(axis=0)[win - 1:n]
        sc = c / en / nw
        j = int(np.argmax(sc))
        out.append((s, j, float(sc[j])))
    return out


def music_map(video, sources, dur):
    """Find which source track (and where in it) plays at every moment of the video's audio.
    Returns runs [(t0, t1, track, offset)] and the seams between them."""
    sr, hop = 22050, 512
    fr = sr / hop
    A = mel_feat(load_mono(video, sr), sr, hop)
    win, step = int(1.5 * fr), int(0.25 * fr)
    per = []  # per window: (t, track, offset_s, score)
    for path in sources:
        B = track_feats(path)
        for k, (s, j, sc) in enumerate(best_offsets(A, B, win, step)):
            if len(per) <= k:
                per.append((s / fr, None, 0.0, -1.0))
            if sc > per[k][3]:
                per[k] = (s / fr, path, (j - s) / fr, sc)
    # group windows into runs of one (track, offset); a window that matches poorly is left out
    runs_ = []
    for t, trk, off, sc in per:
        if sc < MATCH_MIN:
            continue
        if runs_ and runs_[-1]["track"] == trk and abs(runs_[-1]["offset"] - off) < 0.06:
            r = runs_[-1]; r["t1"] = t + 1.5; r["n"] += 1; r["score"] = min(r["score"], sc)
        else:
            runs_.append({"t0": t, "t1": t + 1.5, "track": trk, "offset": off, "n": 1, "score": sc})
    runs_ = [r for r in runs_ if r["n"] >= 3]      # ignore one-window flukes
    covered = sum(min(r["t1"], dur) - r["t0"] for r in runs_)
    if covered < 0.5 * dur:                         # the music is not (mostly) any of these tracks
        return [], []
    # place each seam frame-exactly: where the next run's alignment starts to explain the audio better
    feats = {}
    seams = []
    for a, b in zip(runs_, runs_[1:]):
        for p in (a["track"], b["track"]):
            if p not in feats:
                feats[p] = track_feats(p)
        lo, hi = int(max(a["t0"], b["t0"] - 1.5) * fr), int(min(b["t1"], a["t1"] + 1.5) * fr)
        lo, hi = max(lo, 0), min(hi, A.shape[1])

        def fit(trk, off, i):
            j = int(round(i + off * fr))
            F = feats[trk]
            if not 0 <= j < F.shape[1]:
                return -1.0
            u, v = A[:, i], F[:, j]
            return float(u @ v / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9))
        fa = np.array([fit(a["track"], a["offset"], i) for i in range(lo, hi)])
        fb = np.array([fit(b["track"], b["offset"], i) for i in range(lo, hi)])
        if len(fa) == 0:
            continue
        gain = np.cumsum(fb - fa)          # best split: A before, B after
        k = int(np.argmin(np.r_[0.0, gain[:-1]] - gain[-1]))   # maximise sum(fa[:k]) + sum(fb[k:])
        t = (lo + k) / fr
        a["t1"], b["t0"] = t, t
        seams.append({"t": t, "from_track": a["track"], "to_track": b["track"],
                      "out_at": t + a["offset"], "in_at": t + b["offset"],
                      "skip": (t + b["offset"]) - (t + a["offset"])})
    if runs_:
        runs_[0]["t0"] = max(0.0, runs_[0]["t0"])
        runs_[-1]["t1"] = min(dur, runs_[-1]["t1"])
    return runs_, seams


def track_grid(path, cache):
    """Beat grid + bar phase + section novelty of a source track (cached per file)."""
    if path in cache:
        return cache[path]
    import librosa
    sr, hop = 22050, 512
    y = load_mono(path, sr)
    g = beat_grid(y, sr, hop)
    # the track's own sections: novelty peaks over ~2 s of MFCC + chroma
    feat = np.vstack([librosa.util.normalize(librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13), axis=1),
                      librosa.feature.chroma_stft(y=y, sr=sr, hop_length=hop)])
    nov = checkerboard_novelty(librosa.util.normalize(feat, axis=0), int(2.0 * sr / hop))
    ft = librosa.frames_to_time(np.arange(len(nov)), sr=sr, hop_length=hop)
    pk = [i for i in range(1, len(nov) - 1) if nov[i] > 0.3 and nov[i] >= nov[i - 1] and nov[i] >= nov[i + 1]]
    secs = []
    for i in sorted(pk, key=lambda i: -nov[i]):
        if all(abs(ft[i] - x) > 4.0 for x in secs):
            secs.append(float(ft[i]))
    g["sections"] = sorted(secs)
    cache[path] = g
    return g


def beat_grid(y, sr, hop, bpm=None):
    """Tempo from the PERCUSSIVE onset envelope (the full mix doubles/halves or 4:3s the tempo on
    trailer music), then tempo-locked beat tracking and a bar-phase guess from the low-end accent."""
    import librosa
    yp = librosa.effects.percussive(y)
    onset_p = librosa.onset.onset_strength(y=yp, sr=sr, hop_length=hop)
    tempo = bpm or float(np.atleast_1d(librosa.feature.tempo(onset_envelope=onset_p, sr=sr, hop_length=hop,
                                                             start_bpm=100))[0])
    # beats: the full mix, tempo-locked hard (tightness 1600, as the trailer editor tracks its grids).
    # Against the editor's grids: Leviathan 100% of beats within 60 ms, The Final Factory ~80%.
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    _, beats = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=hop, bpm=tempo, tightness=1600)
    bt = librosa.frames_to_time(beats, sr=sr, hop_length=hop)
    bar_phase = None
    if len(beats) >= 8:
        S = np.abs(librosa.stft(y, hop_length=hop, n_fft=2048))
        low = S[: max(2, int(150 / (sr / 2048)))].sum(axis=0)
        acc = [low[beats[p::4]].mean() for p in range(4)]
        bar_phase = int(np.argmax(acc))
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    return {"tempo": tempo, "beats": bt, "bar_phase": bar_phase, "onset": onset / max(onset.max(), 1e-9),
            "rms": rms, "ft": librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)}


def beat_pos(g, t):
    """(beat index, offset s, position in the bar 0-3 or None) of time t on grid g."""
    b = g["beats"]
    if len(b) == 0:
        return None, 0.0, None
    j = int(np.argmin(np.abs(b - t)))
    bar = None if g["bar_phase"] is None else (j - g["bar_phase"]) % 4
    return j, float(t - b[j]), bar


def level_db(g, t, span):
    m = (g["ft"] >= t) & (g["ft"] < t + span) if span > 0 else (g["ft"] >= t + span) & (g["ft"] < t)
    v = g["rms"][m]
    return 20 * math.log10(max(float(v.mean()) if len(v) else 1e-6, 1e-6))


# ------------------------------------------------------------------------------------ flags

def flag(flags, t, kind, sev, msg, shot=None, t_end=None):
    flags.append({"t": float(t), "t_end": None if t_end is None else float(t_end), "kind": kind, "sev": sev,
                  "shot": shot, "msg": msg})


def make_flags(shots, music, loud, flashes, cuts, n_shots):
    F = []
    last = n_shots - 1
    for s in shots:
        i = s["i"]
        if "still_frac" not in s:
            continue
        endcard = i == last and s["dur"] < 6
        # a still stretch at the end of a shot = the shot lingers after the motion stopped
        for a, b in s["still_runs"]:
            tail = s["end"] - b < 0.25
            head = abs(a - s["start"]) < 0.05
            if tail and not head:
                flag(F, a, "LINGER", "high" if b - a >= 1.0 else "med",
                     f"shot {i} holds {b - a:.1f} s after the motion stops (camera < {STILL_CAM:g} %w/s, "
                     f"little on-screen change){' - end card over it?' if endcard else ''}", i, b)
            elif not (head and tail) and not endcard:
                flag(F, a, "DEAD_AIR", "med", f"shot {i}: {b - a:.1f} s with nothing moving", i, b)
        if s["still_frac"] > 0.7:
            flag(F, s["start"], "STATIC_SHOT", "med" if endcard else "high",
                 f"shot {i} barely moves: camera {s['cam']:.1f} %w/s, on-screen change {s['act']:.2f}, "
                 f"still {s['still_frac'] * 100:.0f}% of its {s['dur']:.1f} s"
                 + (" (the end card sits on footage that has stopped: keep motion under the card)" if endcard else ""),
                 i, s["end"])
        elif s.get("tail_ratio", 1) < TAIL_DROP and s["end"] - s["motion_ends"] > 0.5 and not s["still_runs"]:
            flag(F, s["motion_ends"], "MOTION_DIES", "med",
                 f"shot {i}: motion falls to {s['tail_ratio'] * 100:.0f}% of the shot's peak at {fmt_t(s['motion_ends'])}"
                 f" and the shot runs {s['end'] - s['motion_ends']:.1f} s more (a slowing player or camera)", i, s["end"])
        if (s.get("spread", 1) <= CLUMP_SPREAD and s.get("focus", 0) >= CLUMP_FOCUS and s["cam"] < 3 * STILL_CAM
                and not endcard):
            flag(F, s["start"], "ACTION_CLUMP", "high",
                 f"shot {i}: all the action is in one spot ({s['focus'] * 100:.0f}% of the on-screen change in 3% of "
                 f"the frame, {s['spread'] * 100:.0f}% of the frame active) and the camera is still: "
                 "check the sheet for stacked enemies, a lone effect, or a build that just pops in", i, s["end"])
        if s.get("repeats", 0) >= 3 and s.get("unique_fps"):
            flag(F, s["start"], "STUTTER", "med",
                 f"shot {i}: {s['repeats']} repeated frames while moving (~{s['unique_fps']:.0f} unique fps): judder", i)
        if s["dur"] < 1.0 and i not in (0, last):
            flag(F, s["start"], "FLASH_CUT", "low", f"shot {i} is only {s['dur']:.2f} s", i)
    # repetition and jump cuts
    for s in shots:
        if "_thumbs" not in s:
            continue
        for o in shots:
            if o["i"] <= s["i"] + 1 or "_thumbs" not in o or o["i"] == n_shots - 1:   # the end card repeats the title
                continue
            sim = max(similarity(a, b) for a in s["_thumbs"] for b in o["_thumbs"])
            if sim > SIMILAR_SHOT:
                flag(F, o["start"], "REPEATED", "med",
                     f"shot {o['i']} shows the same view as shot {s['i']} ({sim * 100:.0f}% of features match): reused footage?", o["i"])
    for a, b in zip(shots, shots[1:]):
        if "_last" in a and "_first" in b:
            sim = similarity(a["_last"], b["_first"])
            if sim > JUMP_CUT:
                flag(F, b["start"], "JUMP_CUT", "med",
                     f"cut {a['i']}->{b['i']} stays on the same view ({sim * 100:.0f}% of features match): reads as a skip in time", b["i"])
    if music:
        tracked = music["grid_source"] != "source track"
        for c in music["cuts"]:
            if abs(c["offset_ms"]) / 1000 > OFF_BEAT_FRAC * music["period"]:
                sev = "low" if tracked else "med"
                flag(F, c["t"], "OFF_BEAT", sev, f"cut is {c['offset_ms']:+.0f} ms from the nearest beat"
                     + (" (beat grid tracked from the mix: pass --music for an exact one)" if tracked else ""))
        for sm in music["seams"]:
            if not sm.get("verified"):
                flag(F, sm["t"], "MUSIC_EDIT?", "low",
                     f"possible music edit on this cut (sudden timbre/harmony change, novelty {sm['novelty']:.2f});"
                     " unverified: pass --music <source track> to check")
                continue
            trk = os.path.basename(sm["to_track"])
            what = (f"music jumps {sm['skip']:+.2f} s inside {trk}" if sm["same_track"]
                    else f"music switches {os.path.basename(sm['from_track'])} -> {trk}")
            why = []
            if not sm["on_bar"]:
                why.append(f"not bar-aligned (out on beat {sm['out_bar']}, in on beat {sm['in_bar']} of the bar)")
            if sm.get("bars_left") is not None and sm["bars_left"] > 0.9:
                why.append(f"leaves a section {sm['bars_left']:.1f} bars before it ends (mid-phrase)")
            if sm.get("bars_into") is not None and sm["bars_into"] > 0.9:
                why.append(f"enters {sm['bars_into']:.1f} bars into a section")
            if abs(sm["level_step_db"]) > 3:
                why.append(f"level jumps {sm['level_step_db']:+.1f} dB")
            if not sm["at_cut"]:
                why.append("not on a picture cut")
            sev = "high" if why else "med"
            flag(F, sm["t"], "MUSIC_EDIT", sev,
                 f"{what} (track {fmt_t(sm['out_at'])} -> {fmt_t(sm['in_at'])}): "
                 + ("; ".join(why) if why else "on the bar line, but still an edit inside the music: listen to it"))
        if music["end_level"] > 0.3:
            flag(F, music["cuts"][-1]["t"] if music["cuts"] else 0, "MUSIC_END", "med",
                 f"the music is still at {music['end_level'] * 100:.0f}% of its level in the last 0.3 s: it stops dead")
    if loud and loud["integrated"] is not None:
        if not -16.5 <= loud["integrated"] <= -11.5:
            flag(F, 0, "LOUDNESS", "low", f"integrated loudness {loud['integrated']:.1f} LUFS (web/Steam norm ~ -14)")
        if loud["true_peak"] is not None and loud["true_peak"] > -1.0:
            flag(F, 0, "PEAK", "med", f"true peak {loud['true_peak']:.1f} dBTP (> -1: may clip after encoding)")
    F.sort(key=lambda f: (f["t"], f["kind"]))
    return F


def framing_flags(shots, F):
    """Tight framing. Absolute, not relative to the references: Final Factory's own Steam trailers are
    much tighter than Ben wants (detail 28-45 %w against ~6-10 for the wide shots he approved)."""
    for s in shots:
        if "scale" not in s or s["i"] == len(shots) - 1 or s["dur"] < 0.5:   # end card, flash frames
            continue
        if s["scale"] >= TIGHT_SCALE:
            flag(F, s["start"], "TIGHT", "med",
                 f"shot {s['i']} is framed tight: typical detail is {s['scale']:.0f}% of the frame width "
                 f"(wide shots measure 5-10; v1's zoomed-in shots 17-35). Check the sheet: is the camera too close, "
                 "or is a title/planet filling the frame?", s["i"])
    F.sort(key=lambda f: (f["t"], f["kind"]))


# ------------------------------------------------------------------------------- summary stats

def stats(info, shots, music, loud):
    d = np.array([s["dur"] for s in shots])
    st = {"duration": info["duration"], "shots": len(shots),
          "shots_per_min": len(shots) / info["duration"] * 60 if info["duration"] else 0,
          "shot_median": float(np.median(d)), "shot_p10": float(np.percentile(d, 10)),
          "shot_p90": float(np.percentile(d, 90)), "shot_max": float(d.max()),
          "long_share": float((d >= 5).mean())}
    moving = [s for s in shots if "cam" in s]
    if moving:
        w = np.array([s["dur"] for s in moving])
        st["cam_median"] = float(np.average([s["cam"] for s in moving], weights=w))
        st["act_median"] = float(np.average([s["act"] for s in moving], weights=w))
        st["still_share"] = float(np.average([s.get("still_frac", 0) for s in moving], weights=w))
    ob = [s["objects"] for s in shots if "objects" in s]
    if ob:
        st["objects_median"] = float(np.median(ob)); st["objects_p25"] = float(np.percentile(ob, 25))
        st["scale_median"] = float(np.median([s["scale"] for s in shots if "scale" in s]))
    if music and music["cuts"]:
        st["on_beat_share"] = float(np.mean([c["on_beat"] for c in music["cuts"]]))
        st["tempo"] = music["tempo"]
        st["music_edits"] = sum(1 for s in music["seams"] if s.get("verified"))
    if loud:
        st["lufs"] = loud["integrated"]; st["true_peak"] = loud["true_peak"]
    return st


# ------------------------------------------------------------------------------------ images

def font(size):
    from PIL import ImageFont
    for p in ("/System/Library/Fonts/Menlo.ttc", "C:/Windows/Fonts/consola.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default(size=size)


SEV_COL = {"high": (235, 60, 60), "med": (245, 165, 40), "low": (150, 150, 150)}


def render_timeline(out_dir, info, sig, shots, frames, sfps, au, music, loud, flags, page_s=48.0):
    """One image per ~48 s: filmstrip, waveform + beats + onsets + music edits, loudness, camera
    speed, on-screen change, stillness, flags, with every picture cut drawn through all rows."""
    from PIL import Image, ImageDraw
    dur = info["duration"]
    pages = max(1, int(math.ceil(dur / page_s - 0.08)))
    span = dur / pages
    paths = []
    Wd, L, R = 1800, 150, 20
    rows = [("film", 110), ("audio", 120), ("loud", 60), ("camera", 90), ("change", 90), ("flags", 70)]
    Ht = 40 + sum(h + 8 for _, h in rows) + 30
    f12, f14 = font(12), font(15)
    cam_s, act_s, moving = moving_mask(sig)
    for p in range(pages):
        t0, t1 = p * span, min(dur, (p + 1) * span)
        img = Image.new("RGB", (Wd, Ht), (18, 18, 22))
        d = ImageDraw.Draw(img)
        X = lambda t: L + (t - t0) / (t1 - t0) * (Wd - L - R)
        d.text((10, 8), f"{os.path.basename(info['path'])}  {fmt_t(t0)}-{fmt_t(t1)}  "
                        f"(cuts: green on the beat, red off it; magenta = music edit)", fill=(230, 230, 230), font=f14)
        y = 40
        box = {}
        for name, h in rows:
            box[name] = (y, y + h)
            d.rectangle([L, y, Wd - R, y + h], outline=(60, 60, 70))
            d.text((8, y + h / 2 - 8), name, fill=(200, 200, 200), font=f14)
            y += h + 8
        # filmstrip: one thumbnail per shot at its midpoint, plus extra thumbnails for long shots
        y0, y1 = box["film"]
        for s in shots:
            a, b = max(s["start"], t0), min(s["end"], t1)
            if b <= a:
                continue
            fw = int(X(b) - X(a)) - 2
            th = y1 - y0 - 4
            tw = int(th * 16 / 9)
            n = max(1, fw // tw)
            for k in range(n):
                t = a + (k + 0.5) * (b - a) / n
                j = min(len(frames) - 1, int(t * sfps))
                im = Image.fromarray(frames[j]).resize((tw, th))
                x = int(X(a) + 1 + k * fw / n + (fw / n - tw) / 2)
                img.paste(im.crop((max(0, int(X(a)) + 1 - x), 0, min(tw, int(X(b)) - 1 - x), th)),
                          (max(x, int(X(a)) + 1), y0 + 2))
            d.text((X(a) + 3, y0 + 3), str(s["i"]), fill=(255, 255, 0), font=f14)
        # audio: waveform, beats (downbeats taller), onsets
        if au is not None:
            y0, y1 = box["audio"]
            mid = (y0 + y1) / 2
            env = au["env"]
            for x in range(L, Wd - R):
                ta = t0 + (x - L) / (Wd - L - R) * (t1 - t0)
                k = int(ta / au["env_dt"])
                if 0 <= k < len(env):
                    a = env[k] * (y1 - y0) / 2 * 0.95
                    d.line([x, mid - a, x, mid + a], fill=(90, 130, 180))
            if music is not None:
                for bt, bar in zip(music["beats"], music["bars"]):
                    if t0 <= bt <= t1:
                        d.line([X(bt), y0, X(bt), y0 + (20 if bar == 0 else 9)], fill=(120, 220, 255), width=2 if bar == 0 else 1)
            for ot, os_ in zip(au["onsets"], au["onset_strength"]):
                if t0 <= ot <= t1 and os_ > 0.25:
                    d.ellipse([X(ot) - 2, y1 - 6 - 14 * os_, X(ot) + 2, y1 - 2 - 14 * os_], fill=(255, 120, 120))
        if loud and loud["short_term"]:
            y0, y1 = box["loud"]
            pts = [(X(t), y1 - (min(max(v, -35), -5) + 35) / 30 * (y1 - y0)) for t, v in loud["short_term"] if t0 <= t <= t1]
            if len(pts) > 1:
                d.line(pts, fill=(200, 200, 120), width=2)
            d.text((L + 4, y0 + 2), "short-term LUFS (-35..-5)", fill=(140, 140, 140), font=f12)
        # camera speed (log) + zoom, on-screen change, still shading
        for name, arr, ref, col in (("camera", cam_s, STILL_CAM, (120, 230, 140)), ("change", act_s, STILL_ACT, (240, 170, 90))):
            y0, y1 = box[name]
            top = np.log1p(max(np.percentile(arr, 99), ref * 4))
            yy = lambda v: y1 - np.log1p(max(v, 0)) / top * (y1 - y0 - 4)
            ts = sig["t"]
            m = (ts >= t0) & (ts <= t1)
            idx = np.nonzero(m)[0][:: max(1, int(sig["fps"] / 30))]
            for i0, i1 in runs(~moving[idx]):
                d.rectangle([X(ts[idx[i0]]), y0 + 1, X(ts[idx[min(i1, len(idx) - 1)]]), y1 - 1], fill=(55, 35, 35))
            d.line([(X(ts[i]), yy(arr[i])) for i in idx], fill=col, width=2)
            d.line([L, yy(ref), Wd - R, yy(ref)], fill=(110, 60, 60))
            lab = "camera %w/s (log); red band = still" if name == "camera" else "on-screen change (log)"
            d.text((L + 4, y0 + 2), lab, fill=(140, 140, 140), font=f12)
        # flags
        y0, y1 = box["flags"]
        ends = [0.0, 0.0, 0.0]          # right edge of the last label in each lane
        for fl in sorted(flags, key=lambda f: ({"high": 0, "med": 1, "low": 2}[f["sev"]], f["t"])):
            if t0 <= fl["t"] <= t1:
                x = X(fl["t"]); xe = X(min(fl["t_end"], t1)) if fl["t_end"] else x + 4
                w = max(xe - x, 8 * len(fl["kind"]) + 6)
                lane = next((k for k in range(3) if ends[k] <= x), None)
                if lane is None:
                    continue               # full: the report lists it anyway
                ends[lane] = x + w + 2
                yy0 = y0 + 4 + lane * 21
                d.rectangle([x, yy0, max(xe, x + 4), yy0 + 17], fill=SEV_COL[fl["sev"]])
                d.text((x + 3, yy0 + 1), fl["kind"], fill=(255, 255, 255) if fl["sev"] == "high" else (0, 0, 0), font=f12)
        # cuts and music edits through every row
        for c in [s["start"] for s in shots[1:]]:
            if t0 <= c <= t1:
                ok = True
                if music:
                    cc = [m for m in music["cuts"] if abs(m["t"] - c) < 1e-3]
                    ok = cc[0]["on_beat"] if cc else True
                d.line([X(c), 40, X(c), Ht - 30], fill=(60, 230, 60) if ok else (255, 50, 50), width=2)
        if music:
            for sm in music["seams"]:
                if t0 <= sm["t"] <= t1:
                    d.line([X(sm["t"]), box["audio"][0], X(sm["t"]), box["loud"][1]], fill=(255, 60, 255), width=3)
        # time axis
        for s in range(int(t0), int(t1) + 1):
            x = X(s)
            d.line([x, Ht - 30, x, Ht - (22 if s % 5 else 16)], fill=(180, 180, 180))
            if s % 5 == 0:
                d.text((x - 10, Ht - 16), fmt_t(s)[:-3], fill=(200, 200, 200), font=f12)
        path = os.path.join(out_dir, f"timeline{'' if pages == 1 else f'_{p + 1}'}.png")
        img.save(path)
        paths.append(path)
    return paths


def render_sheets(out_dir, shots, frames, sfps, sig, max_frames=16):
    """One contact sheet per shot: frames at the sample rate, stamped with video time, time in the
    shot, camera speed and on-screen change, and STILL where nothing moves."""
    from PIL import Image, ImageDraw
    os.makedirs(os.path.join(out_dir, "sheets"), exist_ok=True)
    cam_s, act_s, moving = moving_mask(sig)
    f14 = font(15)
    paths = []
    for s in shots:
        idx = s.get("frames") or []
        if not idx:
            continue
        if len(idx) > max_frames:
            idx = [idx[int(round(k * (len(idx) - 1) / (max_frames - 1)))] for k in range(max_frames)]
        cols = 4 if len(idx) > 6 else min(3, len(idx))
        tw = 440
        th = int(tw * frames[0].shape[0] / frames[0].shape[1])
        rows_ = int(math.ceil(len(idx) / cols))
        img = Image.new("RGB", (cols * (tw + 6) + 6, rows_ * (th + 28) + 40), (15, 15, 18))
        d = ImageDraw.Draw(img)
        d.text((8, 10), f"shot {s['i']}  {fmt_t(s['start'])}-{fmt_t(s['end'])}  ({s['dur']:.2f} s)  "
                        f"camera {s.get('cam', 0):.1f} %w/s  change {s.get('act', 0):.2f}  "
                        f"objects {s.get('objects', 0):.0f}", fill=(240, 240, 240), font=f14)
        for k, j in enumerate(idx):
            r, c = divmod(k, cols)
            x, y = 6 + c * (tw + 6), 40 + r * (th + 28)
            img.paste(Image.fromarray(frames[j]).resize((tw, th)), (x, y))
            t = j / sfps
            fi = min(len(sig["t"]) - 1, int(t * sig["fps"]))
            still = not moving[fi]
            d.text((x + 2, y + th + 4), f"{fmt_t(t)} (+{t - s['start']:.2f})  cam {cam_s[fi]:.0f}  chg {act_s[fi]:.1f}"
                   + ("  STILL" if still else ""), fill=(255, 110, 110) if still else (200, 200, 200), font=f14)
        p = os.path.join(out_dir, "sheets", f"shot_{s['i']:02d}.jpg")
        img.save(p, quality=85)
        paths.append(p)
    return paths


def render_overview(out_dir, shots, frames, sfps):
    """Every shot on one row: first, 1/3, 2/3 and last sampled frame."""
    from PIL import Image, ImageDraw
    tw, th = 300, int(300 * frames[0].shape[0] / frames[0].shape[1])
    f14 = font(14)
    per_img = 12
    paths = []
    for p0 in range(0, len(shots), per_img):
        grp = shots[p0:p0 + per_img]
        img = Image.new("RGB", (150 + 4 * (tw + 4), len(grp) * (th + 4) + 4), (15, 15, 18))
        d = ImageDraw.Draw(img)
        for r, s in enumerate(grp):
            idx = s.get("frames") or []
            y = 4 + r * (th + 4)
            d.text((6, y + 4), f"shot {s['i']}\n{fmt_t(s['start'])}\n{s['dur']:.2f} s", fill=(230, 230, 230), font=f14)
            for c, q in enumerate((0, 1 / 3, 2 / 3, 1)):
                if idx:
                    j = idx[min(len(idx) - 1, int(q * (len(idx) - 1)))]
                    img.paste(Image.fromarray(frames[j]).resize((tw, th)), (150 + c * (tw + 4), y))
        path = os.path.join(out_dir, f"overview{'' if len(shots) <= per_img else f'_{p0 // per_img + 1}'}.jpg")
        img.save(path, quality=85)
        paths.append(path)
    return paths


# ------------------------------------------------------------------- Gemini (whole video + sound)

CONF = os.path.join(os.path.expanduser("~"), ".config", "ff-watch-video")
# USD per 1M tokens (input, output incl. thinking), paid tier, from ai.google.dev/gemini-api/docs/pricing
# (2026-09-29). Unknown models are costed at the most expensive row so the daily cap stays safe.
PRICES = {"gemini-3.8-flash": (0.75, 3.75), "gemini-3.7-flash": (0.75, 3.75), "gemini-3.5-flash": (1.50, 9.00),
          "gemini-3.1-pro": (2.00, 12.00), "gemini-2.5-pro": (1.25, 10.00), "gemini-2.5-flash": (0.30, 2.50)}
PRICE_UNKNOWN = (4.00, 18.00)
TOKENS_PER_FRAME = 300      # Gemini video: ~300 tokens per sampled frame at default media resolution
TOKENS_AUDIO_S = 32


def gemini_key():
    k = os.environ.get("GEMINI_API_KEY")
    if k:
        return k
    p = os.path.join(CONF, "gemini.env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.strip().startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"\'')
    return None


def price(model):
    for k, v in PRICES.items():
        if model.startswith(k):
            return v
    return PRICE_UNKNOWN


def spend_today():
    p = os.path.join(CONF, "spend.json")
    d = json.load(open(p)) if os.path.exists(p) else {}
    return d, d.get(time.strftime("%Y-%m-%d"), 0.0), p


def http(method, url, key, body=None, headers=None, raw=False):
    h = {"x-goog-api-key": key}
    h.update(headers or {})
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    if body is not None and not isinstance(body, bytes):
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return (r.headers, r.read()) if raw else json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:600]
        raise RuntimeError(f"Gemini API {e.code}: {msg}") from None


GEMINI_PROMPT = """You are a senior game-trailer editor reviewing a cut, watching AND listening to it the way a
viewer on a Steam store page would. Be blunt and specific; praise only what is genuinely strong.
Judge only what you see and hear in this video: you get no measurements or hints, on purpose.

{brief}

Write markdown with exactly these sections:
1. **First impression** (3-5 sentences): how it feels to watch, pacing, energy, whether music and picture feel
   like one piece, whether you understand what the game is and why you would want it.
2. **Timeline**: one bullet per problem, in time order, EXACTLY in this form:
   `- [m:ss.s] CATEGORY: what you see/hear, why it hurts, the fix`
   Categories: LINGER (a shot holds after the action or camera stops), MUSIC (an audible music edit, chop,
   jump, or music that fights the picture), CUT (off the beat, awkward, a jump cut), ACTION (combat or movement
   that looks fake, stacked on one spot, frozen or unreadable), FRAMING (too zoomed in, subject too small or
   too large, hard to read), TRANSITION, REPETITION, TEXT (titles, captions, UI clutter), BRIEF.
3. **Against the brief**: what it delivers, what it misses.
4. **Score**: pacing, music edit, action, framing, overall, each /10.
5. **Top 5 fixes**, most important first.
Only report what you actually see or hear; write "unsure" rather than guess. Timestamps are video time."""

# which machine flags a model finding of each category can corroborate
CORROBORATES = {"LINGER": {"LINGER", "DEAD_AIR", "STATIC_SHOT", "MOTION_DIES"},
                "MUSIC": {"MUSIC_EDIT", "MUSIC_EDIT?", "MUSIC_END", "OFF_BEAT"},
                "CUT": {"OFF_BEAT", "JUMP_CUT", "FLASH_CUT"},
                "ACTION": {"ACTION_CLUMP", "STATIC_SHOT", "DEAD_AIR"},
                "FRAMING": {"TIGHT"}, "REPETITION": {"REPEATED", "JUMP_CUT"}, "TRANSITION": {"JUMP_CUT", "FLASH_CUT"}}


def model_findings(text, offset):
    """Parse `- [m:ss.s] CATEGORY: ...` lines (also ranges like [0:24.0 - 0:27.5])."""
    out = []
    pat = re.compile(r"^\s*[-*]\s*\**\[(\d+):(\d+(?:\.\d+)?)(?:\s*[-\u2013]\s*(\d+):(\d+(?:\.\d+)?))?\]\**\s*\**([A-Z /_?]+?)\**\s*:\s*(.+)$")
    for line in text.splitlines():
        m = pat.match(line)
        if not m:
            continue
        t0 = int(m.group(1)) * 60 + float(m.group(2)) + offset
        t1 = int(m.group(3)) * 60 + float(m.group(4)) + offset if m.group(3) else t0
        cats = [c.strip() for c in m.group(5).split("/")]
        out.append({"t": t0, "t_end": t1, "cats": cats, "text": m.group(6).strip()})
    return out


def corroborate(flags, findings, slack=1.0):
    """Mark flags a blind model finding agrees with (same kind of problem, overlapping time)."""
    used = set()
    for f in flags:
        fe = f["t_end"] if f["t_end"] is not None else f["t"]
        for k, g in enumerate(findings):
            kinds = set().union(*(CORROBORATES.get(c, set()) for c in g["cats"]))
            if f["kind"] in kinds and g["t"] - slack <= fe and g["t_end"] + slack >= f["t"]:
                f.setdefault("model", []).append(k)
                used.add(k)
    return [g for k, g in enumerate(findings) if k not in used]


def gemini_review(video, info, flags, brief_text, out_dir, model, fps, segment, daily_limit, dry=False):
    key = gemini_key()
    if not key:
        return {"status": "skipped", "why": "no GEMINI_API_KEY (env or ~/.config/ff-watch-video/gemini.env)"}
    a, b = segment or (0.0, info["duration"])
    dur = b - a
    pin, pout = price(model)
    est_in = dur * fps * TOKENS_PER_FRAME + dur * TOKENS_AUDIO_S + 3000
    est = est_in / 1e6 * pin + 6000 / 1e6 * pout
    ledger, today, lpath = spend_today()
    if today + est > daily_limit:
        return {"status": "skipped", "why": f"daily cap: ${today:.2f} spent today + ~${est:.3f} > ${daily_limit:.2f}"}
    if dry:
        return {"status": "dry", "estimate_usd": est, "model": model}
    # a 720p proxy keeps the upload small; Gemini samples frames itself
    proxy = os.path.join(out_dir, "gemini_proxy.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", video,
         "-vf", "scale=-2:720", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", proxy])
    size = os.path.getsize(proxy)
    base = "https://generativelanguage.googleapis.com"
    hdr, _ = http("POST", f"{base}/upload/v1beta/files", key, {"file": {"display_name": "watch_video"}},
                  {"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                   "X-Goog-Upload-Header-Content-Length": str(size),
                   "X-Goog-Upload-Header-Content-Type": "video/mp4"}, raw=True)
    up = hdr["x-goog-upload-url"]
    _, body = http("POST", up, key, open(proxy, "rb").read(),
                   {"X-Goog-Upload-Command": "upload, finalize", "X-Goog-Upload-Offset": "0",
                    "Content-Length": str(size)}, raw=True)
    f = json.loads(body)["file"]
    try:
        for _ in range(120):
            if f.get("state") == "ACTIVE":
                break
            if f.get("state") == "FAILED":
                raise RuntimeError(f"Gemini could not process the upload: {f.get('error')}")
            time.sleep(2)
            f = http("GET", f"{base}/v1beta/{f['name']}", key)
        brief = f"The brief for this cut:\n\n{brief_text.strip()}\n" if brief_text else "No brief was given."
        prompt = GEMINI_PROMPT.format(brief=brief)
        video_part = {"file_data": {"mime_type": "video/mp4", "file_uri": f["uri"]}, "video_metadata": {"fps": fps}}
        req = {"contents": [{"role": "user", "parts": [video_part, {"text": prompt}]}]}
        t0 = time.time()
        r = http("POST", f"{base}/v1beta/models/{model}:generateContent", key, req)
        took = time.time() - t0
    finally:
        try:
            http("DELETE", f"{base}/v1beta/{f['name']}", key)
        except Exception:
            pass
        os.remove(proxy)
    text = "".join(p.get("text", "") for c in r.get("candidates", [])[:1] for p in c["content"].get("parts", []))
    u = r.get("usageMetadata", {})
    tin = u.get("promptTokenCount", 0)
    tout = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    cost = tin / 1e6 * pin + tout / 1e6 * pout
    ledger[time.strftime("%Y-%m-%d")] = round(today + cost, 5)
    os.makedirs(CONF, exist_ok=True)
    json.dump(ledger, open(lpath, "w"), indent=1)
    res = {"status": "ok", "model": model, "fps": fps, "segment": [a, b], "tokens_in": tin, "tokens_out": tout,
           "cost_usd": cost, "estimate_usd": est, "seconds": took, "spent_today_usd": today + cost}
    with open(os.path.join(out_dir, "gemini.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# Gemini review ({model}, {fps} fps, {fmt_t(a)}-{fmt_t(b)})\n\n"
                 f"Cost ${cost:.4f} ({tin} in, {tout} out incl. thinking); today ${today + cost:.3f} of ${daily_limit:.2f}."
                 f"\nTimestamps below are relative to {fmt_t(a)}.\n\n{text}\n")
    res["text"] = text
    return res


# ------------------------------------------------------------------------------ references

STEAM_APP = 1383150   # Final Factory


def steam_refs():
    """The game's official Steam trailers, downloaded once into the cache."""
    d = os.path.join(CACHE, "refs")
    os.makedirs(d, exist_ok=True)
    have = sorted(os.path.join(d, f) for f in os.listdir(d) if f.startswith("ff_steam_") and f.endswith(".mp4"))
    if have:
        return have
    meta = json.loads(urllib.request.urlopen(
        f"https://store.steampowered.com/api/appdetails?appids={STEAM_APP}&filters=movies", timeout=60).read())
    for m in meta[str(STEAM_APP)]["data"].get("movies", []):
        url = m.get("hls_h264") or m.get("mp4", {}).get("max")
        name = re.sub(r"[^a-z0-9]+", "_", m["name"].lower()).strip("_")
        out = os.path.join(d, f"ff_steam_{name}.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", url, "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", out])
        have.append(out)
    return have


def ref_stats(ref, args):
    if ref.endswith(".json"):
        return json.load(open(ref, encoding="utf-8"))["stats"] | {"name": os.path.basename(ref)}
    st = os.stat(ref)
    key = hashlib.sha1(f"{os.path.abspath(ref)}|{st.st_size}|{st.st_mtime}|{VERSION}".encode()).hexdigest()[:16]
    cp = os.path.join(CACHE, "ref_stats", key + ".json")
    if os.path.exists(cp):
        return json.load(open(cp))
    print(f"  measuring reference {os.path.basename(ref)} (cached afterwards)")
    r = analyse(ref, args, light=True)
    s = r["stats"] | {"name": os.path.basename(ref)}
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    json.dump(s, open(cp, "w"), indent=1)
    return s


# ---------------------------------------------------------------------------------- pipeline

def ff_music_dir():
    """The game's soundtrack: <FinalFactory checkout>/Assets/Audio/Music."""
    cands = [os.environ.get("FF_REPO")]
    try:
        cands.append(run(["git", "rev-parse", "--show-toplevel"], text=True).stdout.strip())
    except Exception:
        pass
    cands.append(os.path.join(os.path.expanduser("~"), "nevergames", "FinalFactory"))
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "Assets", "Audio", "Music")):
            return os.path.join(c, "Assets", "Audio", "Music")
    sys.exit("--music ff: no FinalFactory checkout found (set FF_REPO)")


def music_sources(spec):
    out = []
    for s in spec or []:
        if s == "ff":
            s = ff_music_dir()
        if os.path.isdir(s):
            out += sorted(os.path.join(s, f) for f in os.listdir(s) if f.lower().endswith(AUDIO_EXT))
        elif os.path.exists(s):
            out.append(s)
        else:
            sys.exit(f"--music: no such file or folder: {s}")
    return out


def analyse(path, args, light=False):
    t_start = time.time()
    info = probe(path)
    info["path"] = path
    print(f"  {os.path.basename(path)}: {info['width']}x{info['height']} {info['fps']:.2f} fps, {info['duration']:.2f} s")
    sfps = args.sheet_fps
    sig, frames = video_signals(path, info, sfps)
    cuts = detect_cuts(path, info, sig)
    fl, fades = flashes_and_fades(sig)
    # a white flash is not a cut, except that a flash usually opens one: keep the first detection
    # in each flash and drop the rest (the flash fading out reads as a second "cut")
    keep = []
    for c in cuts:
        f = [(a, b) for a, b in fl if a - 0.1 <= c <= b + 0.1]
        if f and any(f[0][0] - 0.1 <= k <= f[0][1] + 0.1 for k in keep):
            continue
        keep.append(c)
    cuts = keep
    bounds = list(zip([0.0] + cuts, cuts + [info["duration"]]))
    shots = analyse_shots(sig, bounds, fl)
    add_readability(shots, frames, sfps)
    au = audio_signals(path, info, args.bpm)
    loud = loudness(path, info)
    mruns = mseams = grids = None
    srcs = [] if light else music_sources(args.music)
    if au is not None and srcs:
        mruns, mseams = music_map(path, srcs, info["duration"])
        cache = {}
        grids = {r["track"]: track_grid(r["track"], cache) for r in mruns}
        if getattr(args, "beats", None):
            tracks = sorted(set(r["track"] for r in mruns))
            if len(tracks) == 1:
                bt = np.array(sorted(json.load(open(args.beats))), float)
                grids[tracks[0]] = {**grids[tracks[0]], "beats": bt, "tempo": 60.0 / float(np.median(np.diff(bt)))}
                print(f"  beat grid from {os.path.basename(args.beats)} ({len(bt)} beats)")
            else:
                print("  --beats ignored: the music comes from more than one track")
        if not mruns:
            print("  --music: the audio does not match any given track; falling back to the mix's own beat grid")
            mruns = mseams = None
    music = music_analysis(au, cuts, info["duration"], mruns, mseams, grids)
    flags = make_flags(shots, music, loud, fl, cuts, len(shots))
    st = stats(info, shots, music, loud)
    print(f"  analysed in {time.time() - t_start:.1f} s: {len(shots)} shots, {len(flags)} flags")
    return {"info": info, "sig": sig, "cuts": cuts, "flashes": fl, "fades": fades, "shots": shots,
            "frames": frames, "sfps": sfps, "au": au, "loud": loud, "music": music, "flags": flags, "stats": st}


def md_table(rows, head):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def direction(dx, dy):
    if math.hypot(dx, dy) < STILL_CAM:
        return "-"
    ang = math.degrees(math.atan2(-dy, dx)) % 360
    return ["E", "NE", "N", "NW", "W", "SW", "S", "SE"][int((ang + 22.5) // 45) % 8]


def write_report(out, r, refs, brief_text, gem, images):
    info, shots, music, loud, flags, st = r["info"], r["shots"], r["music"], r["loud"], r["flags"], r["stats"]
    L = [f"# watch_video: {os.path.basename(info['path'])}", ""]
    L.append(f"{info['width']}x{info['height']}, {info['fps']:.2f} fps, {info['duration']:.2f} s, {len(shots)} shots, "
             f"median shot {st['shot_median']:.2f} s" + (f", {st['tempo']:.1f} BPM" if music else "")
             + (f", {loud['integrated']:.1f} LUFS" if loud and loud["integrated"] is not None else "")
             + f". watch_video {VERSION}.")
    L += ["", "## How to review this (for the agent reading it)", "",
          "1. Read the flags below: each has a video time. They are measurements, not verdicts.",
          f"2. LOOK at {', '.join(os.path.basename(p) for p in images['timeline'])} (every cut, the beat grid, "
          "music edits, motion and loudness on one time axis) and "
          f"{', '.join(os.path.basename(p) for p in images['overview'])} (every shot on one row).",
          "3. For every flagged shot, open its contact sheet `sheets/shot_NN.jpg` and judge what the numbers "
          "cannot: is the action believable (enemies spread out, not stacked on one spot), is the subject "
          "readable, does the framing show enough of the world, does the shot match the brief? Open the "
          "combat sheets even when unflagged: a clump the camera moves over has no machine flag.",
          "4. If `gemini.md` exists, it is a whole-video review WITH sound: weigh its music and feel "
          "judgements; check its visual claims against the sheets (it samples only a few fps).",
          "5. Write the critique: per issue, the time, what is wrong, and the concrete fix.", ""]
    L += ["## Flags", ""]
    if not flags:
        L.append("None.")
    for f in flags:
        span = f"-{fmt_t(f['t_end'])}" if f["t_end"] else ""
        agree = " **[the blind model review heard/saw this too]**" if f.get("model") else ""
        L.append(f"- **{fmt_t(f['t'])}{span}** `{f['kind']}` ({f['sev']}): {f['msg']}{agree}")
    L += ["", "## Shots", ""]
    rows = []
    for s in shots:
        cut = ""
        if music:
            cc = [c for c in music["cuts"] if abs(c["t"] - s["start"]) < 1e-3]
            if cc:
                c = cc[0]
                cut = f"{c['offset_ms']:+.0f} ms" + (f" (bar beat {c['bar_pos']})" if c["bar_pos"] is not None else "")
        rows.append([s["i"], fmt_t(s["start"]), f"{s['dur']:.2f}", f"{s.get('cam', 0):.1f}", f"{s.get('act', 0):.2f}",
                     f"{s.get('zoom', 0):+.1f}", direction(*s.get("dir", (0, 0))), f"{s.get('still_frac', 0) * 100:.0f}%",
                     f"{s.get('objects', 0):.0f}", f"{s.get('scale', 0):.1f}", s.get("repeats", 0), cut or "-"])
    L.append(md_table(rows, ["#", "start", "dur s", "camera %w/s", "change", "zoom %/s", "moves", "still",
                             "objects", "detail %w", "dup frames", "cut vs beat"]))
    L += ["", "camera = median camera speed in % of the frame width per second; change = on-screen change after "
          "removing camera motion (0-255 mean abs diff); still = share of the shot where neither moves; objects = "
          "distinct things on screen (edge blobs); detail = typical feature size, % of width (bigger = tighter "
          "framing); cut vs beat = the cut INTO this shot against the nearest beat.", ""]
    if music:
        L += ["## Music", "", f"Tempo {music['tempo']:.1f} BPM, beat grid {music['grid_source']}. "
              f"{sum(c['on_beat'] for c in music['cuts'])}/{len(music['cuts'])} cuts within {ON_BEAT_MS} ms of a beat."]
        if music["map"]:
            L += ["", "Where the music comes from:", ""]
            L.append(md_table([[fmt_t(m["t0"]), fmt_t(m["t1"]), os.path.basename(m["track"]),
                                f"{fmt_t(m['t0'] + m['offset'])}-{fmt_t(m['t1'] + m['offset'])}", f"{m['score']:.2f}"]
                               for m in music["map"]], ["from", "to", "track", "track time", "match"]))
            if len(music["map"]) == 1:
                L.append("\nOne continuous run of the track: no music edits.")
        for sm in music["seams"]:
            if sm.get("verified"):
                L.append(f"\n- Music edit at **{fmt_t(sm['t'])}**: out of {os.path.basename(sm['from_track'])} at "
                         f"{fmt_t(sm['out_at'])} (bar beat {sm['out_bar']}, {sm['out_off_ms']:+.0f} ms), into "
                         f"{os.path.basename(sm['to_track'])} at {fmt_t(sm['in_at'])} (bar beat {sm['in_bar']}, "
                         f"{sm['in_off_ms']:+.0f} ms); level step {sm['level_step_db']:+.1f} dB; "
                         f"{'on' if sm['at_cut'] else 'NOT on'} a picture cut.")
        L.append(f"\nMusic level in the last 0.3 s: {music['end_level'] * 100:.0f}% of its body "
                 f"({'fades out' if music['end_level'] < 0.3 else 'stops dead'}). Bar beat 0 = the downbeat "
                 "(guessed from the low-end accent: check it by ear if it matters).")
        if loud:
            L.append(f"\nLoudness: {loud['integrated']} LUFS integrated, LRA {loud['lra']} LU, true peak {loud['true_peak']} dBTP.")
        L.append("")
    if refs:
        L += ["## Against the references", ""]
        keys = [("duration", "duration s", "{:.1f}"), ("shots", "shots", "{:.0f}"), ("shots_per_min", "shots/min", "{:.1f}"),
                ("shot_median", "median shot s", "{:.2f}"), ("shot_p10", "p10 shot s", "{:.2f}"),
                ("shot_p90", "p90 shot s", "{:.2f}"), ("long_share", "shots >= 5 s", "{:.0%}"),
                ("cam_median", "camera %w/s", "{:.1f}"), ("act_median", "change", "{:.2f}"),
                ("still_share", "still share", "{:.0%}"), ("objects_median", "objects", "{:.0f}"),
                ("scale_median", "detail %w", "{:.1f}"), ("on_beat_share", "cuts on beat", "{:.0%}"),
                ("lufs", "LUFS", "{:.1f}")]
        head = ["", "this cut"] + [x["name"].replace("ff_steam_", "steam ").replace(".mp4", "") for x in refs]
        rows = []
        for k, lab, f in keys:
            row = [lab] + [f.format(v) if (v := d.get(k)) is not None else "-" for d in [st] + refs]
            rows.append(row)
        L.append(md_table(rows, head))
        L.append("")
    if brief_text:
        L += ["## Brief", "", brief_text.strip(), ""]
    L += ["## Whole-video model review", ""]
    if gem.get("status") == "ok":
        n_agree = sum(1 for f in flags if f.get("model"))
        L.append(f"`gemini.md`: {gem['model']} watched and listened to the cut BLIND (the brief only, no flags), "
                 f"{gem['fps']:g} fps, cost ${gem['cost_usd']:.4f} ({gem['tokens_in']} tokens in / {gem['tokens_out']} out). "
                 f"It independently agrees with {n_agree} of the {len(flags)} flags (marked above).")
        if gem.get("model_only"):
            L += ["", "What only the model reported (no machine flag nearby): check each on the contact sheet or "
                  "by ear before acting on it.", ""]
            L += [f"- **{fmt_t(g['t'])}** {'/'.join(g['cats'])}: {g['text']}" for g in gem["model_only"]]
    else:
        L.append(f"Not run: {gem.get('why', gem.get('status'))}.")
    L += ["", "## Files", ""] + [f"- `{os.path.relpath(p, out)}`" for k in ("timeline", "overview") for p in images[k]]
    L.append(f"- `sheets/` ({len(images['sheets'])} contact sheets, {r['sfps']:g} frames/s)")
    open(os.path.join(out, "report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


def to_json(r, refs, gem):
    shots = [{k: v for k, v in s.items() if not k.startswith("_") and k != "frames"} for s in r["shots"]]
    m = r["music"]
    mj = None
    if m:
        mj = {k: v for k, v in m.items() if k not in ("beats", "bars")}
        mj["beats"] = [round(float(b), 3) for b in m["beats"]]
    return json.loads(json.dumps({"version": VERSION, "info": r["info"], "stats": r["stats"], "cuts": r["cuts"],
                                  "flashes": r["flashes"], "shots": shots, "flags": r["flags"], "music": mj,
                                  "loudness": {k: v for k, v in (r["loud"] or {}).items() if k != "short_term"},
                                  "refs": refs, "gemini": {k: v for k, v in gem.items() if k != "text"}},
                                 default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def main():
    ap = argparse.ArgumentParser(description="Watch a video (with sound) and write a time-stamped review report.")
    ap.add_argument("video")
    ap.add_argument("--ref", action="append", default=[],
                    help="reference video or its report.json (repeatable); 'steam' = Final Factory's official trailers")
    ap.add_argument("--brief", help="text/markdown file: what the cut is supposed to do")
    ap.add_argument("--music", action="append", default=[],
                    help="source music track(s), a folder of them, or ff (the game soundtrack): exact music-edit map + beat grid")
    ap.add_argument("--out", help="output folder (default: <tmp>/watch_video/<name>)")
    ap.add_argument("--sheet-fps", type=float, default=4.0, help="contact-sheet frames per second (default 4)")
    ap.add_argument("--bpm", type=float, help="force the tempo if the tracker gets it wrong")
    ap.add_argument("--beats", help="JSON list of beat times (s) in the SOURCE track (the editor's own grid); "
                                    "used instead of the tracked grid when --music matches one track")
    ap.add_argument("--model", choices=["auto", "gemini", "none"], default="auto",
                    help="whole-video review: gemini (needs GEMINI_API_KEY), none, or auto (gemini if a key exists)")
    ap.add_argument("--gemini-model", default=os.environ.get("WATCH_VIDEO_GEMINI_MODEL", "gemini-3.8-flash"))
    ap.add_argument("--gemini-fps", type=float, default=2.0, help="frames/s Gemini samples (default 2)")
    ap.add_argument("--segment", help="only send this part to Gemini, e.g. 12.5-30 (seconds)")
    ap.add_argument("--daily-limit", type=float, default=float(os.environ.get("WATCH_VIDEO_DAILY_USD", 5.0)),
                    help="hard cap on Gemini spend per day in USD (default 5)")
    args = ap.parse_args()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("watch_video needs ffmpeg and ffprobe on PATH")
    if not os.path.exists(args.video):
        sys.exit(f"no such file: {args.video}")
    name = os.path.splitext(os.path.basename(args.video))[0]
    out = args.out or os.path.join(tempfile.gettempdir(), "watch_video", name)
    os.makedirs(out, exist_ok=True)
    for old in ("sheets",):
        shutil.rmtree(os.path.join(out, old), ignore_errors=True)
    brief_text = open(args.brief, encoding="utf-8", errors="replace").read() if args.brief else None
    print("watch_video: analysing")
    r = analyse(args.video, args)
    refs = []
    for ref in args.ref:
        for p in (steam_refs() if ref == "steam" else [ref]):
            refs.append(ref_stats(p, args))
    framing_flags(r["shots"], r["flags"])
    r["stats"] = stats(r["info"], r["shots"], r["music"], r["loud"])
    print("  rendering the timeline and contact sheets")
    images = {"timeline": render_timeline(out, r["info"], r["sig"], r["shots"], r["frames"], r["sfps"], r["au"],
                                          r["music"], r["loud"], r["flags"]),
              "overview": render_overview(out, r["shots"], r["frames"], r["sfps"]),
              "sheets": render_sheets(out, r["shots"], r["frames"], r["sfps"], r["sig"])}
    gem = {"status": "skipped", "why": "--model none"}
    if args.model != "none" and (args.model == "gemini" or gemini_key()):
        seg = tuple(float(x) for x in args.segment.split("-")) if args.segment else None
        print(f"  asking {args.gemini_model} to watch it (with sound)")
        try:
            gem = gemini_review(args.video, r["info"], r["flags"], brief_text, out, args.gemini_model,
                                args.gemini_fps, seg, args.daily_limit)
        except Exception as e:
            gem = {"status": "error", "why": str(e)[:500]}
        if gem.get("status") == "ok":
            gem["findings"] = model_findings(gem["text"], gem["segment"][0])
            gem["model_only"] = corroborate(r["flags"], gem["findings"])
            print(f"  gemini: ${gem['cost_usd']:.4f} ({gem['tokens_in']} in / {gem['tokens_out']} out), "
                  f"today ${gem['spent_today_usd']:.3f}")
        else:
            print(f"  gemini: {gem.get('why', gem.get('status'))}")
    elif args.model == "auto":
        gem = {"status": "skipped", "why": "no GEMINI_API_KEY (env or ~/.config/ff-watch-video/gemini.env)"}
    write_report(out, r, refs, brief_text, gem, images)
    json.dump(to_json(r, refs, gem), open(os.path.join(out, "report.json"), "w", encoding="utf-8"), indent=1)
    print(f"\nreport: {os.path.join(out, 'report.md')}")
    for f in r["flags"]:
        if f["sev"] == "high":
            print(f"  {fmt_t(f['t'])} {f['kind']}: {f['msg']}")


if __name__ == "__main__":
    main()
