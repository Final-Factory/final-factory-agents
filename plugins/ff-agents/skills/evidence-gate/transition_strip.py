#!/usr/bin/env python3
"""Every frame of a visual transition on one contact sheet, cropped on the object, with its pops marked (w1686).

A transition claim ("the Guardian stretches into the hole", "a swallowed ship stays lit as itself", "dissolves into")
is proven by every frame from the one before it starts to its end state, not by a sheet every 0.2 or 0.5 s: at 60 fps a
0.5 s step shows 1 frame in 30, and a model that vanishes in about 0.1 s (6 frames) falls between two samples. w1470,
the Singularity Lance, round 4 (2026-10-20): the second opinion said "the Guardian disappears at once"; a sheet every
0.2 s cleared it; Ben, 2026-10-21: "the guardian especially doesn't really smoothly transition to the spaghetti state it
just kind of disappears".

    python3 transition_strip.py CLIP --from 3.4 --to 6.2 --crop 480:480:900:300 --claim guardian-swallow \
        --object "the Guardian" [--every 1] [--out DIR]

Writes <out>/<claim>-strip-<from>-<to>s-every<N>f.png (each frame stamped with its time and frame number, the pop
candidates framed in red) and a .json beside it, and prints the 'Close-ups:' entry and the question for the fresh
critic. A pop candidate is a frame whose change from the one before, inside the crop, is over --pop times the median
step of the window (and over 2/255): a model that disappears or swaps in one frame. It points your eye; it does not
judge (an effect that strikes on purpose, a crackle, also spikes). Every frame is still looked at, by you and the critic.
Needs ffmpeg, numpy and Pillow (as watch_video.py does). The rule: lessons/visual-fixes-are-verified-by-looking.md,
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


def pops(step: list[float], ratio: float, floor: float = 2.0) -> list[int]:
    """Frames whose step is over `ratio` times the window's median step and over `floor`: a one-frame jump. A still
    window has a median near 0, so the floor alone decides there."""
    med = median_step(step)
    return [i for i, s in enumerate(step) if i and s > floor and s > ratio * max(med, 0.25)]


def median_step(step: list[float]) -> float:
    rest = sorted(step[1:])
    return rest[len(rest) // 2] if rest else 0.0


def sheet(fr, pick: list[int], times: list[float], fnums: list[int], marked: set[int], title: str, out: Path,
          cols: int) -> None:
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
    for k, j in enumerate(pick):
        r, c = divmod(k, cols)
        x, y = 6 + c * (w + 6), 32 + r * (h + 24)
        if j in marked:
            d.rectangle((x - 3, y - 3, x + w + 2, y + h + 2), outline=(255, 40, 40), width=3)
        img.paste(Image.fromarray(fr[j]), (x, y))
        d.text((x + 2, y + h + 4), f"{times[j]:.3f}s f{fnums[j]}" + ("  POP?" if j in marked else ""),
               fill=(255, 90, 90) if j in marked else (200, 200, 200), font=font)
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
    step = steps(fr)
    marked = set(pops(step, args.pop))
    times = [args.a + i / fps for i in range(len(fr))]
    fnums = [int(round(t * fps)) for t in times]
    pick = sorted(set(range(0, len(fr), args.every)) | marked | {len(fr) - 1})
    name = re.sub(r"[^\w.-]+", "-", args.claim).strip("-") or "transition"
    stem = f"{name}-strip-{args.a:.2f}-{args.b:.2f}s-every{args.every}f"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cw, ch, cx, cy = crop
    title = (f"{Path(args.clip).name}  {args.a:.2f}-{args.b:.2f} s  every {'' if args.every == 1 else '2nd '}frame "
             f"({fps:.0f} fps, {len(pick)} of {len(fr)})  crop {cw}x{ch}+{cx}+{cy}  "
             f"pops: {', '.join(f'f{fnums[j]}' for j in sorted(marked)) or 'none'}")
    sheet(fr, pick, times, fnums, marked, title, out / f"{stem}.png", args.cols)
    med = median_step(step)
    report = {"clip": args.clip, "from": args.a, "to": args.b, "fps": fps, "every": args.every,
              "crop": {"w": cw, "h": ch, "x": cx, "y": cy}, "frames": len(fr), "median_step": round(med, 3),
              "pops": [{"frame": fnums[j], "t": round(times[j], 3), "step": round(step[j], 2),
                        "times_median": round(step[j] / max(med, 0.25), 1)} for j in sorted(marked)],
              "steps": [round(s, 3) for s in step]}
    (out / f"{stem}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    pop_text = "; ".join(f"f{p['frame']} {p['t']:.3f} s {p['times_median']}x" for p in report["pops"]) or "none"
    print(f"{stem}.png: {len(pick)} frames of {len(fr)} at {fps:.1f} fps, median step {med:.2f}/255, pops: {pop_text}")
    print(f"Close-ups entry: {args.claim}: {stem}.png ({args.a:.2f}-{args.b:.2f} s, every "
          f"{'' if args.every == 1 else '2nd '}frame, pops: {pop_text})")
    print(f"Critic question: In {stem}.png, is {args.object}'s own model on screen in every frame from "
          f"{args.a:.2f} s until its end state at {args.b:.2f} s, getting thinner or smaller a little each frame? Name "
          f"the first frame where it is gone or replaced, and say what the frame before it shows"
          + (f"; look hardest at {', '.join(f'f{p}' for p in (q['frame'] for q in report['pops']))}" if report["pops"]
             else "") + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
