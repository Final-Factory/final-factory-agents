#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Every frame of a visual transition on one contact sheet, cropped on the object, with its pops marked (w1686).

A transition claim ("the Guardian stretches into the hole", "a swallowed ship stays lit as itself", "dissolves into")
is proven by every frame from the one before it starts to its end state, not by a sheet every 0.2 or 0.5 s: at 60 fps a
0.5 s step shows 1 frame in 30, and a model that vanishes in about 0.1 s (6 frames) falls between two samples. w1470,
the Singularity Lance, round 4 (2026-10-20): the second opinion said "the Guardian disappears at once"; a sheet every
0.2 s cleared it; Ben, 2026-10-21: "the guardian especially doesn't really smoothly transition to the spaghetti state it
just kind of disappears".

    uv run transition_strip.py CLIP --from 3.4 --to 6.2 --crop 480:480:900:300 --claim guardian-swallow \
        --object "the Guardian" [--every 1] [--out DIR]

Writes <out>/<claim>-strip-<from>-<to>s-every<N>f.png (each frame stamped with its time and frame number, the pop
candidates framed in red) and a .json beside it, and prints the 'Close-ups:' entry and the question for the fresh
critic. A pop candidate is a frame whose change from the one before, inside the crop, is over --pop times the median
step of the window (and over 2/255): a model that disappears or swaps in one frame. It points your eye; it does not
judge (an effect that strikes on purpose, a crackle, also spikes). Every frame is still looked at, by you and the critic.

It also tracks the object (w1816; --track X,Y, a point on one object in the first frame it is in, or X,Y,W,H, a box
round a group; a green dot on the sheet shows where it was followed) and marks what a pop check cannot see: a JUMP
(orange), its centre moving over --jump (4) times its median move of the 6 frames each side and over --jump-min (half)
of its own size in one frame; a LUNGE (orange), over 6 frames, --surge (3) times its pace of the 30 frames before;
and a HUE (magenta), --hue (35%) or more of its pixels in colours not in its first 3 frames' palette (--allow-hues
heat for a glow the person asked for). A half-speed take that shows each frame twice is found and its copies left
out. w1685, after a clip passed with "no vanish, pop, swap or jump", Ben: "i dont like that it suddenly jumps to the
center of the black hole and then also becomes that purple". The rule: lessons/visual-fixes-are-verified-by-looking.md,
"A transition keeps its place and its colours", checklists/visual.md 5i and 5j.
Needs ffmpeg; `uv run` installs numpy and Pillow from the header above (the Macs' python3 has neither, so plain
`python3 transition_strip.py` stops on ModuleNotFoundError: w1470, 2026-10-22). The rule: lessons/visual-fixes-are-verified-by-looking.md,
"A transition is stepped every frame on the object", checklists/visual.md 5h.
"""
import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path


def probe(path: str) -> tuple[int, int, float]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,avg_frame_rate,r_frame_rate", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    rate = s.get("avg_frame_rate") or s.get("r_frame_rate") or "60/1"
    num, _, den = rate.partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 60.0
    return int(s["width"]), int(s["height"]), fps


def parse_crop(text: str | None, w: int, h: int) -> tuple[int, int, int, int]:
    if not text:
        return w, h, 0, 0
    cw, ch, cx, cy = (int(float(v)) for v in re.split(r"[:,x ]+", text.strip()))
    cw, ch = min(cw, w), min(ch, h)
    return cw, ch, max(0, min(cx, w - cw)), max(0, min(cy, h - ch))


def frames(path: str, a: float, b: float, crop: tuple[int, int, int, int], width: int):
    """The frames between a and b (s) at the clip's own rate, cropped, scaled to `width`: (n, h, w, 3) uint8."""
    import numpy as np
    cw, ch, cx, cy = crop
    width = min(width, cw)
    height = max(2, int(round(width * ch / cw / 2)) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.4f}", "-i", path, "-t", f"{b - a:.4f}", "-an",
                          "-vf", f"crop={cw}:{ch}:{cx}:{cy},scale={width}:{height}:flags=area",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    n = len(raw) // (width * height * 3)
    return np.frombuffer(raw[: n * width * height * 3], np.uint8).reshape(n, height, width, 3)


def steps(fr) -> list[float]:
    """Mean absolute change (0-255) of each frame from the one before; the first frame has 0."""
    import numpy as np
    g = fr.astype(np.float32).mean(axis=3)
    return [0.0] + [float(np.abs(g[i] - g[i - 1]).mean()) for i in range(1, len(g))]


def pops(step: list[float], ratio: float, floor: float = 2.0, repeat: frozenset[int] = frozenset()) -> list[int]:
    """Frames whose step is over `ratio` times the window's median step and over `floor`: a one-frame jump. A still
    window has a median near 0, so the floor alone decides there. The `repeat` frames (a half-speed capture's second
    copy of each frame) are left out of the median, or every real step of such a clip looks like a pop (w1816: 14
    false pops in w1685's half-speed take)."""
    med = median_step([0.0] + [s for i, s in enumerate(step) if i and i not in repeat])
    return [i for i, s in enumerate(step) if i and s > floor and s > ratio * max(med, 0.25)]


def repeats(step: list[float]) -> frozenset[int]:
    """The frames that copy the one before, when the clip is a doubled capture (a half-speed take shows each frame
    twice). A copy's step is under 0.5/255 and under a fifth of the larger step beside it (the encoder's noise grows
    with the motion, so no fixed floor holds); a clip is doubled when 35% or more of its frames are copies (measured,
    w1816: 48-50% in w1685's half-speed take, 8-10% in its normal one). Otherwise none: a still in a normal clip is a
    still, not a copy."""
    copy = frozenset(i for i in range(1, len(step) - 1)
                     if step[i] < 0.5 and step[i] < 0.2 * max(step[i - 1], step[i + 1]))
    return copy if len(step) >= 20 and len(copy) >= 0.35 * (len(step) - 2) else frozenset()


def median_step(step: list[float]) -> float:
    rest = sorted(step[1:])
    return rest[len(rest) // 2] if rest else 0.0


def components(mask) -> list[list[tuple[int, int]]]:
    """The 8-connected blobs of a boolean (h, w) mask, each a list of (y, x)."""
    h, w = mask.shape
    seen = mask.copy()
    blobs = []
    for y0, x0 in zip(*mask.nonzero()):
        if not seen[y0, x0]:
            continue
        seen[y0, x0] = False
        todo, blob = [(int(y0), int(x0))], []
        while todo:
            y, x = todo.pop()
            blob.append((y, x))
            for yy in (y - 1, y, y + 1):
                for xx in (x - 1, x, x + 1):
                    if 0 <= yy < h and 0 <= xx < w and seen[yy, xx]:
                        seen[yy, xx] = False
                        todo.append((yy, xx))
        blobs.append(blob)
    return blobs


def track(fr, bg, seed: tuple[float, float, float, float] | None, diff: float, min_px: int, gap: int = 3,
          roll: tuple[int, int] = (8, 30), group: bool = False,
          pad: tuple[int, int] = (0, 0)) -> list[dict | None]:
    """Follow the object through the window (w1816). A pixel is the object's when it differs by over `diff` (0-255, any
    channel) from the scene: with `bg` None, the median of the frames 8 to 30 away on each side (a scene that keeps
    moving, the hole's swirling disk, changes little in half a second while the object moves on); else `bg`, frames of
    the scene without the object, (k, h, w, 3), and the pixel must differ from every one of them. Pixels that differ in
    over half the window are the scene too (a glow that stays). Such pixels are joined across a 2 px gap into blobs.
    The first time, the object is the largest blob touching the `seed` box (x0, y0, x1, y1 in sheet pixels; every one
    of them with `group`), else the largest blob. After that, one object is the blob nearest its last place, weighted
    by size; a `group` (a box given around several ships) is every blob touching its last box widened by half its
    size, and the nearest blob only when none does: that is a jump. Blobs
    under `min_px` pixels are noise. A frame with none is None; after `gap` such frames in a row the object is gone and
    stays gone (what is left is the scene). Each entry: {x, y, area, box, pixels: (ys, xs)} or None."""
    import numpy as np
    n, h, w = fr.shape[:3]
    diag = math.hypot(w, h)
    f32 = fr.astype(np.float32)
    if bg is None:
        near = np.empty((n, h, w), np.float32)
        for i in range(n):
            pick = [j for j in range(i - roll[1], i + roll[1] + 1) if 0 <= j < n and abs(j - i) >= roll[0]]
            near[i] = np.abs(f32[i] - np.median(f32[pick], axis=0)).max(axis=2)
    else:
        near = np.full((n, h, w), np.inf, np.float32)
        for b in bg.astype(np.float32):
            near = np.minimum(near, np.abs(f32 - b[None]).max(axis=3))
    raw = near > diff
    raw &= ~(raw.mean(axis=0) > 0.5)
    raw = raw[pad[0]: len(raw) - pad[1]]                     # the frames around the window: background only
    n = len(raw)
    out: list[dict | None] = []
    last, missed = None, 0
    for i in range(n):
        if last is not None and missed > gap:
            out.append(None)
            continue
        m = raw[i]
        joined = m.copy()
        for dy in (-2, -1, 0, 1, 2):                          # a 2 px dilation: strands and sparks stay one object
            for dx in (-2, -1, 0, 1, 2):
                joined |= np.roll(np.roll(m, dy, 0), dx, 1)
        blobs = []
        for blob in components(joined[::2, ::2]):             # half resolution: the blobs only pick the pixels
            if len(blob) * 4 >= min_px:
                blobs.append((np.array([p[0] for p in blob]) * 2, np.array([p[1] for p in blob]) * 2))
        if last is not None:
            x0, y0, x1, y1 = last["box"]
            grow = max(3.0, 0.5 * math.sqrt(last["area"]))
            region = (x0 - grow, y0 - grow, x1 + grow, y1 + grow) if group else None
        else:
            region = seed
        pick = [bl for bl in blobs if region and (bl[1].max() >= region[0] and bl[1].min() <= region[2]
                                                  and bl[0].max() >= region[1] and bl[0].min() <= region[3])]
        if pick and not group:
            pick = [max(pick, key=lambda bl: len(bl[0]))]
        if last is not None and not group:                    # one object: the blob over its own last pixels
            was = np.zeros((h, w), bool)
            for dy in (-2, -1, 0, 1, 2):
                for dx in (-2, -1, 0, 1, 2):
                    was[np.clip(last["pixels"][0] + dy, 0, h - 1), np.clip(last["pixels"][1] + dx, 0, w - 1)] = True
            over = [(int(was[bl[0], bl[1]].sum()), bl) for bl in blobs]
            over = [o for o in over if o[0]]
            pick = [max(over, key=lambda o: o[0])[1]] if over else []
        if not pick and blobs and (last is not None or seed is None):
            if last is None:
                pick = [max(blobs, key=lambda bl: len(bl[0]))]
            else:
                pick = [max(blobs, key=lambda bl: len(bl[0]) * math.exp(
                    -math.hypot(bl[1].mean() - last["x"], bl[0].mean() - last["y"]) / (0.08 * diag)))]
        entry = None
        if pick:
            sel = np.zeros_like(m)
            for ys, xs in pick:
                for oy in (0, 1):
                    for ox in (0, 1):
                        sel[np.clip(ys + oy, 0, h - 1), np.clip(xs + ox, 0, w - 1)] = True
            ys, xs = (sel & m).nonzero()
            if len(ys) >= min_px:
                entry = {"x": float(xs.mean()), "y": float(ys.mean()), "area": int(len(ys)),
                         "box": (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())), "pixels": (ys, xs)}
        out.append(entry)
        if entry:
            last, missed = entry, 0
        elif last is not None:
            missed += 1
    return out


def jumps(tr: list[dict | None], ratio: float, share: float, around: int = 6,
          repeat: frozenset[int] = frozenset()) -> list[tuple[int, float, float]]:
    """Frames where the object moves further in one frame than `ratio` times its speed in the frames around it (the
    median step of the `around` frames on each side) and over `share` of its own size (the square root of its area in
    the frame before) and 2 sheet pixels: a jump (w1685, Ben: "it suddenly jumps to the center of the black hole").
    Across a frame or two where it is not seen, the move is shared out over
    them. A frame in `repeat` (the same picture as the one before: a half-speed capture shows each frame twice) is no
    sample. A step where its size also changes over 1.8x may be the tracker taking another blob (ships merging or
    parting) or a real jump that shrinks it: it comes back marked, for the eye. (index, step per frame, the speed
    around it, resized)."""
    d: list[float | None] = [None] * len(tr)
    prev_of: dict[int, int] = {}
    prev = None
    for i, t in enumerate(tr):
        if t is None or i in repeat:
            continue
        if prev is not None and i - prev <= 4:
            d[i] = math.hypot(t["x"] - tr[prev]["x"], t["y"] - tr[prev]["y"]) / (i - prev)
            prev_of[i] = prev
        prev = i
    found = []
    for i, s in enumerate(d):
        if s is None:
            continue
        before = tr[prev_of[i]]
        if s <= max(2.0, share * math.sqrt(before["area"])):
            continue
        near = sorted(v for v in d[max(0, i - around): i] + d[i + 1: i + 1 + around] if v is not None)
        speed = near[len(near) // 2] if near else 0.0
        if s > ratio * max(speed, 0.5):
            found.append((i, s, speed, switched(before["area"], tr[i]["area"])))
    return found


def switched(*areas: int) -> bool:
    """The object's size changed over 1.8x across these samples: perhaps the tracker took another blob."""
    return max(areas) > 1.8 * max(1, min(areas))


def surges(tr: list[dict | None], ratio: float, share: float, span: int = 6, before: int = 30,
           repeat: frozenset[int] = frozenset()) -> list[tuple[int, float, float]]:
    """Frames where the object, over the last `span` frames, moves over `ratio` times faster than its median speed in
    the `before` frames ahead of them, and over `share` of its own size in that time: it drifts, then lunges (w1685: the
    ships crept along the rim at about 1 px a frame for 1.5 s, then dropped into the hole at 3 to 4; Ben: "it suddenly
    jumps to the center of the black hole ... it'd be cool if it more smoothly swirled into the black hole"). A jump
    that takes a few frames, which `jumps` (one frame) does not see. The first frame of each lunge: (index, speed over
    the span, the speed before, whether its size changed over 1.8x in the span: a likely track switch)."""
    seen = [(i, t) for i, t in enumerate(tr) if t is not None and i not in repeat]
    pos = {i: t for i, t in seen}

    def pace(i: int) -> float | None:
        """Its net move per frame over the `span` frames up to i (a tracker's jitter cancels out), or None."""
        back = [j for j in pos if i - span <= j < i]
        if i not in pos or not back or i - min(back) < span - 2:
            return None
        j = min(back)
        return math.hypot(pos[i]["x"] - pos[j]["x"], pos[i]["y"] - pos[j]["y"]) / (i - j)

    paces = {i: pace(i) for i in pos}
    found: list[tuple[int, float, float]] = []
    last_hit = -10 ** 6
    for i, t in seen:
        fast = paces[i]
        if fast is None:
            continue
        j = i - span
        moved = fast * span
        base = sorted(v for k, v in paces.items() if v is not None and j - before <= k <= j)
        if len(base) < before // 3 or j not in pos and not any(k in pos for k in range(j, i)):
            continue
        slow = base[len(base) // 2]
        j = min(k for k in pos if k >= j)
        if fast > ratio * max(slow, 0.25) and moved > share * math.sqrt(pos[j]["area"]):
            if i - last_hit > 8:                              # a new lunge, not the same one going on
                found.append((i, fast, slow, switched(*(pos[k]["area"] for k in pos if j <= k <= i))))
            last_hit = i
    return found


HUES = (("red", 0, 15), ("orange", 15, 45), ("yellow", 45, 70), ("green", 70, 160), ("cyan", 160, 200),
        ("blue", 200, 245), ("purple", 245, 290), ("magenta", 290, 345), ("red", 345, 360))
HEAT = {"neutral", "red", "orange", "yellow"}                  # a heat glow: white-hot, red, orange, yellow


def colour_classes(rgb):
    """Each pixel's colour class: 0 neutral (grey, white, black: saturation under 0.25 or value under 0.15), else
    1 + its hue in 10-degree bins (1..36)."""
    import numpy as np
    c = rgb.astype(np.float32) / 255.0
    mx, mn = c.max(axis=1), c.min(axis=1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = c[:, 0], c[:, 1], c[:, 2]
    delta = np.maximum(mx - mn, 1e-6)
    hue = np.where(mx == r, (g - b) / delta % 6, np.where(mx == g, (b - r) / delta + 2, (r - g) / delta + 4)) * 60
    cls = 1 + (hue // 10).astype(int) % 36
    return np.where((sat < 0.25) | (mx < 0.15), 0, cls)


def hue_name(cls: int) -> str:
    if cls == 0:
        return "neutral"
    deg = (cls - 1) * 10 + 5
    return next(name for name, a, b in HUES if a <= deg < b)


def palette_shift(fr, tr: list[dict | None], frac: float, allow: set[str], first: int = 3,
                  least: float = 0.15) -> list[tuple[int, float, str]]:
    """Frames whose object has `frac` or more of its pixels in colours that were not its own in its first frames
    (w1685, Ben: "then also becomes that purple ... used the objects actual colors"): its palette is every colour class
    with 4% or more of its pixels in the first `first` frames it is seen, widened by one hue bin (10 degrees) each side.
    Classes named in `allow` (e.g. a heat glow's red, orange, yellow and white) are never foreign. A frame where the
    object is under `least` of its first size is not judged: a speck in the hole is mostly the hole's own pixels, and
    the critic judges it on the sheet. (index, foreign share, the commonest foreign hue)."""
    import numpy as np
    seen = [i for i, t in enumerate(tr) if t][:first]
    if not seen:
        return []
    size = sum(tr[i]["area"] for i in seen) / len(seen)
    base = np.concatenate([colour_classes(fr[i][tr[i]["pixels"]]) for i in seen])
    counts = np.bincount(base, minlength=37)
    own = {int(c) for c in np.nonzero(counts >= 0.04 * len(base))[0]}
    wide = {0} & own | {1 + (c - 1 + k) % 36 for c in own if c for k in (-1, 0, 1)}
    wide |= {c for c in range(37) if hue_name(c) in allow}
    found = []
    for i, t in enumerate(tr):
        if not t or t["area"] < least * size:
            continue
        cls = colour_classes(fr[i][t["pixels"]])
        foreign = ~np.isin(cls, list(wide))
        share = float(foreign.mean())
        if share >= frac:
            names = {}
            for c, k in zip(*np.unique(cls[foreign], return_counts=True)):
                names[hue_name(int(c))] = names.get(hue_name(int(c)), 0) + int(k)
            found.append((i, share, max(names, key=names.get)))
    return found


def sheet(fr, pick: list[int], times: list[float], fnums: list[int], marked: dict[int, list[str]], title: str,
          out: Path, cols: int, tr: list[dict | None] | None = None) -> None:
    """The contact sheet: a frame framed in red is a pop, orange a jump, magenta a colour off the object's palette; a
    green dot is where the tracker has the object (its centre), so a wrong track is seen at once."""
    from PIL import Image, ImageDraw, ImageFont
    h, w = fr.shape[1], fr.shape[2]
    rows = int(math.ceil(len(pick) / cols))
    img = Image.new("RGB", (cols * (w + 6) + 6, rows * (h + 24) + 36), (15, 15, 18))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=14)
    except TypeError:                                         # Pillow < 10.1
        font = ImageFont.load_default()
    d.text((6, 8), title, fill=(235, 235, 235), font=font)
    edge = {"POP": (255, 40, 40), "JUMP": (255, 150, 0), "SURGE": (255, 150, 0), "HUE": (230, 60, 230)}
    for k, j in enumerate(pick):
        r, c = divmod(k, cols)
        x, y = 6 + c * (w + 6), 32 + r * (h + 24)
        tags = marked.get(j, [])
        if tags:
            d.rectangle((x - 3, y - 3, x + w + 2, y + h + 2), outline=edge[tags[0]], width=3)
        img.paste(Image.fromarray(fr[j]), (x, y))
        if tr and tr[j]:
            cx, cy = x + tr[j]["x"], y + tr[j]["y"]
            d.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=(60, 255, 90))
        d.text((x + 2, y + h + 4), f"{times[j]:.3f}s f{fnums[j]}" + "".join(f" {t}?" for t in tags),
               fill=edge[tags[0]] if tags else (200, 200, 200), font=font)
    img.save(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("clip")
    ap.add_argument("--from", dest="a", type=float, required=True, help="seconds: the frame before the transition starts")
    ap.add_argument("--to", dest="b", type=float, required=True, help="seconds: its stated end state (gone, in the core)")
    ap.add_argument("--crop", help="W:H:X:Y in the clip's pixels, on the object (the w1567 close-up); default the frame")
    ap.add_argument("--every", type=int, default=1, help="1 (default) or 2; 2 only on a clip of 50 fps or more")
    ap.add_argument("--claim", default="transition", help="a short name for the claim, used in the file names")
    ap.add_argument("--object", default="the object", help="whose model must stay on screen, for the critic's question")
    ap.add_argument("--out", default=".", help="folder for the sheet and its json (the review note's folder)")
    ap.add_argument("--width", type=int, default=240, help="each frame's width on the sheet")
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--pop", type=float, default=4.0, help="a step over this many times the median step is a pop candidate")
    ap.add_argument("--track", help="X,Y (a point on the object) or X,Y,W,H (a box around it, e.g. a group of ships) in "
                                    "the clip's pixels, in the first frame it is in; default: the largest thing that "
                                    "differs from the scene. Check the green dot sits on it in every frame")
    ap.add_argument("--bg", help="seconds, or A:B seconds: the frame(s) of the clip without the object, as the "
                                 "background; a range over a scene that keeps moving (a swirling disk: 1 s of it before "
                                 "the object arrives). Default: each frame against the median of the frames 8-30 away on each side")
    ap.add_argument("--diff", type=float, default=80.0, help="0-255: how far a pixel differs from the background to be "
                                                             "the object")
    ap.add_argument("--jump", type=float, default=4.0, help="a one-frame move over this many times the object's speed "
                                                            "in the frames around it is a jump")
    ap.add_argument("--jump-min", type=float, default=0.5, help="and over this share of the object's own size "
                                                                "(the square root of its area)")
    ap.add_argument("--surge", type=float, default=3.0, help="moving over this many times faster, over 6 frames, than "
                                                             "in the 30 frames before is a lunge")
    ap.add_argument("--hue", type=float, default=0.35, help="a frame with this share of the object's pixels in colours "
                                                            "not its own is off its palette")
    ap.add_argument("--allow-hues", default="", help="comma-separated colours that are not foreign, e.g. 'heat' (white, "
                                                     "red, orange, yellow: a heat glow) or 'blue,cyan'")
    args = ap.parse_args(argv)
    if args.b <= args.a:
        ap.error("--to must be after --from")
    if args.every not in (1, 2):
        ap.error("--every is 1 or 2: a coarser step is the sheet that missed w1470's vanish")
    w, h, fps = probe(args.clip)
    if args.every == 2 and fps < 50:
        print(f"note: the clip is {fps:.1f} fps, so every 2nd frame is a {2 / fps:.3f} s step: use --every 1")
    crop = parse_crop(args.crop, w, h)
    fr = frames(args.clip, args.a, args.b, crop, args.width)
    if not len(fr):
        print(f"no frames between {args.a} and {args.b} s in {args.clip}")
        return 1
    import numpy as np
    cw, ch, cx, cy = crop
    scale = fr.shape[2] / cw
    if args.bg:
        ba, _, bb = args.bg.partition(":")
        ba, bb = float(ba), float(bb) if bb else float(ba) + 1.5 / fps
        bg = frames(args.clip, ba, bb, crop, args.width)
        bg = bg[:: max(1, len(bg) // 60)]                    # at most about 60 frames of it
    else:
        bg = None                                             # rolling median (track)
    seed, group = None, False
    if args.track:
        v = [float(t) for t in re.split(r"[,: ]+", args.track.strip())]
        tx, ty, tw, th = (v + [0.0, 0.0])[:4]
        group = len(v) >= 4
        seed = ((tx - cx) * scale - 3, (ty - cy) * scale - 3, (tx + tw - cx) * scale + 3, (ty + th - cy) * scale + 3)
    allow = set()
    for word in filter(None, (v.strip().lower() for v in args.allow_hues.split(","))):
        allow |= HEAT if word == "heat" else {word}
    step = steps(fr)
    same = repeats(step)
    pop_at = pops(step, args.pop, repeat=same)
    ctx, pad = fr, (0, 0)
    if bg is None:                                            # half a second each side, for the rolling background
        a0 = max(0.0, args.a - 0.5)
        ctx = frames(args.clip, a0, args.b + 0.5, crop, args.width)
        p0 = min(int(round((args.a - a0) * fps)), max(0, len(ctx) - len(fr)))
        pad = (p0, max(0, len(ctx) - p0 - len(fr)))
        if len(ctx) - sum(pad) != len(fr):
            ctx, pad = fr, (0, 0)
    tr = track(ctx, bg, seed, args.diff, min_px=max(6, int(fr.shape[1] * fr.shape[2] * 0.0005)), group=group,
               pad=pad)
    jump_at = jumps(tr, args.jump, args.jump_min, repeat=same)
    surge_at = surges(tr, args.surge, args.jump_min, repeat=same)
    hue_at = palette_shift(fr, tr, args.hue, allow)
    marked: dict[int, list[str]] = {}
    for tag, at in (("POP", pop_at), ("JUMP", [j[0] for j in jump_at]), ("SURGE", [j[0] for j in surge_at]),
                    ("HUE", [q[0] for q in hue_at])):
        for j in at:
            marked.setdefault(j, []).append(tag)
    times = [args.a + i / fps for i in range(len(fr))]
    fnums = [int(round(t * fps)) for t in times]
    pick = sorted(set(range(0, len(fr), args.every)) | set(marked) | {len(fr) - 1})
    name = re.sub(r"[^\w.-]+", "-", args.claim).strip("-") or "transition"
    stem = f"{name}-strip-{args.a:.2f}-{args.b:.2f}s-every{args.every}f"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    hue_spans = spans([q[0] for q in hue_at], gap=8)
    title = (f"{Path(args.clip).name}  {args.a:.2f}-{args.b:.2f} s  every {'' if args.every == 1 else '2nd '}frame "
             f"({fps:.0f} fps, {len(pick)} of {len(fr)})  crop {cw}x{ch}+{cx}+{cy}  "
             f"pops: {', '.join(f'f{fnums[j]}' for j in pop_at) or 'none'}  "
             f"jumps: {', '.join(f'f{fnums[j[0]]}' for j in jump_at) or 'none'}  "
             f"lunges: {', '.join(f'f{fnums[j[0]]}' for j in surge_at) or 'none'}  "
             f"off-palette: {', '.join(f'f{fnums[a]}-f{fnums[b]}' for a, b in hue_spans) or 'none'}")
    sheet(fr, pick, times, fnums, marked, title, out / f"{stem}.png", args.cols, tr)
    med = median_step(step)
    hue_of = {q[0]: q for q in hue_at}
    report = {"clip": args.clip, "from": args.a, "to": args.b, "fps": fps, "every": args.every,
              "crop": {"w": cw, "h": ch, "x": cx, "y": cy}, "frames": len(fr), "median_step": round(med, 3),
              "pops": [{"frame": fnums[j], "t": round(times[j], 3), "step": round(step[j], 2),
                        "times_median": round(step[j] / max(med, 0.25), 1)} for j in pop_at],
              "jumps": [{"frame": fnums[j], "t": round(times[j], 3), "px": round(d / scale, 1),
                         "speed_px": round(v / scale, 1), "times_speed": round(d / max(v, 0.5), 1), "resized": r}
                        for j, d, v, r in jump_at],
              "surges": [{"frame": fnums[j], "t": round(times[j], 3), "speed_px": round(v / scale, 1),
                          "before_px": round(b / scale, 1), "times_before": round(v / max(b, 0.25), 1), "resized": r}
                         for j, v, b, r in surge_at],
              "off_palette": [{"from": fnums[a], "to": fnums[b], "t": round(times[a], 3),
                               "peak_share": round(max(hue_of[k][1] for k in range(a, b + 1) if k in hue_of), 2),
                               "hue": commonest(hue_of[k][2] for k in range(a, b + 1) if k in hue_of)} for a, b in hue_spans],
              "thresholds": {"pop": args.pop, "jump": args.jump, "jump_min": args.jump_min, "surge": args.surge,
                             "hue": args.hue, "repeat_frames": len(same),
                             "diff": args.diff, "allow_hues": sorted(allow)},
              "track": [None if t is None else {"x": round(t["x"] / scale + cx, 1), "y": round(t["y"] / scale + cy, 1),
                                                "area": t["area"]} for t in tr],
              "steps": [round(s, 3) for s in step]}
    (out / f"{stem}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    pop_text = "; ".join(f"f{p['frame']} {p['t']:.3f} s {p['times_median']}x" for p in report["pops"]) or "none"
    jump_text = "; ".join(f"f{j['frame']} {j['t']:.3f} s {j['px']} px against {j['speed_px']} px/frame around it"
                          + (" (its size changed over 1.8x too)" if j["resized"] else "") for j in report["jumps"]) or "none"
    surge_text = "; ".join(f"f{j['frame']} {j['t']:.3f} s {j['speed_px']} px/frame after {j['before_px']} before"
                           + (" (its size changed over 1.8x too)" if j["resized"] else "") for j in report["surges"]) or "none"
    hue_text = "; ".join(f"f{q['from']}-f{q['to']} to {q['hue']} (up to {q['peak_share']:.0%} of it)"
                         for q in report["off_palette"]) or "none"
    seen = sum(1 for t in tr if t)
    print(f"{stem}.png: {len(pick)} frames of {len(fr)} at {fps:.1f} fps, median step {med:.2f}/255, pops: {pop_text}")
    print(f"tracked in {seen} of {len(fr)} frames; jumps: {jump_text}; lunges: {surge_text}; "
          f"off its own colours: {hue_text}")
    if any(j["resized"] for j in report["jumps"] + report["surges"]):
        print("a move marked 'its size changed over 1.8x too' may be the tracker taking another blob (ships merging or "
              "parting) rather than the object moving: check the green dot in that frame and the one before")
    print(f"Close-ups entry: {args.claim}: {stem}.png ({args.a:.2f}-{args.b:.2f} s, every "
          f"{'' if args.every == 1 else '2nd '}frame, pops: {pop_text}, jumps: {jump_text}, lunges: {surge_text}, off-palette: {hue_text})")
    look = ([f"f{p['frame']}" for p in report["pops"]] + [f"f{j['frame']}" for j in report["jumps"] + report["surges"]]
            + [f"f{q['from']}" for q in report["off_palette"]])
    print(f"Critic question: In {stem}.png, is {args.object}'s own model on screen in every frame from "
          f"{args.a:.2f} s until its end state at {args.b:.2f} s, getting thinner or smaller a little each frame? Name "
          f"the first frame where it is gone or replaced, and say what the frame before it shows. Does it move about "
          f"as far each frame as in the frames around it, or does it jump (to the centre, across the hole) in one frame, or creep and then lunge? "
          f"Name the frame. Does it keep its own colours from the first frame, or turn another colour (purple, a tint, "
          f"a glow that hides its hull)? Name the first frame and the colour"
          + (f"; look hardest at {', '.join(look)}" if look else "") + ".")
    return 0


def commonest(names) -> str:
    """The name seen most often (the first of a tie)."""
    seen: dict[str, int] = {}
    for n in names:
        seen[n] = seen.get(n, 0) + 1
    return max(seen, key=seen.get)


def spans(idx: list[int], gap: int = 0) -> list[tuple[int, int]]:
    """Runs of indices, as (first, last); a run carries on across up to `gap` missing ones (the object crossing a
    patch of its new colour, a frame it is too small to judge)."""
    out: list[tuple[int, int]] = []
    for i in idx:
        if out and i <= out[-1][1] + 1 + gap:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


if __name__ == "__main__":
    sys.exit(main())
