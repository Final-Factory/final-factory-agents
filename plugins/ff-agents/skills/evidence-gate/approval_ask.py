#!/usr/bin/env python3
"""approval_ask.py: an approval ask explains every change, with cropped, marked before/after stills (w2156).

    python approval_ask.py mark --before <before.png> --after <after.png> --out <dir> [--rect X,Y,W,H] [--pad 48]
    python approval_ask.py check <ask.md>

mark crops the pair to the area that differs (found by pixel difference, or the --rect you give), rings that area in
red on both crops, and writes <dir>/before.png, <dir>/after.png and <dir>/pair.png (side by side, labelled). Each file
carries an "ff-approval-mark" PNG text chunk with the crop, which check reads. It exits 1 when the two stills do not
differ: then there is nothing to show, or the stills are of different screens.

check reads the ask a person will read (the review note you publish and quote in the report, before any
waiting_on_person card). It needs one "## Change <n>: <title>" section per change, each with these parts, in plain
words:

    **Before:**    what the player did and saw, step by step (two or more numbered steps)
    **After:**     what they see now
    **Fixes:**     the problem it fixes
    **Code:**      the file, the method, and the value before and after (old -> new)
    **Unchanged:** what does not change
    **Stills:**    the before/after pair from `mark` (images in the section; each carries the mark chunk)

A part of fewer than MIN_WORDS words is a one-liner and fails. A still that `mark` did not make (a full-screen grab, an
unmarked crop) fails. Prints each miss with its section and exits 1 when there is one.

Why: Ben had to ask twice for the same change to be explained ("You need to explain this change to me more", then
"youre not explaining in detail what youre changing. i dont get it, i've told you like 14 times to explain it to me
better"). Both asks gave one line per change and full-screen stills where the difference was a small corner.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CHUNK = "ff-approval-mark"
MIN_WORDS = 8
MIN_STEPS = 2
DIFF_LEVEL = 24          # per-channel difference that counts as changed
MIN_CROP = (360, 220)    # a crop smaller than this loses its surroundings
MAX_CROP_SHARE = 0.5     # a crop over half the screen hides a small difference as a full-screen still does
RING = (255, 40, 40)
RING_WIDTH = 5
PARTS = ("before", "after", "fixes", "code", "unchanged", "stills")


# ---------------------------------------------------------------------------------------------------------- mark

def diff_box(a, b):
    """Bounding box (x0, y0, x1, y1) of the pixels that differ by more than DIFF_LEVEL, or None."""
    from PIL import ImageChops
    d = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
    return d.point(lambda v: 255 if v > DIFF_LEVEL else 0).getbbox()


def crop_box(box, size, pad):
    x0, y0, x1, y1 = box
    w, h = size
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    for lo, hi, lim, need in ((0, 2, w, MIN_CROP[0]), (1, 3, h, MIN_CROP[1])):
        c = [x0, y0, x1, y1]
        short = need - (c[hi] - c[lo])
        if short > 0:
            c[lo] -= short // 2
            c[hi] += short - short // 2
        x0, y0, x1, y1 = c
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1)


def mark(before: Path, after: Path, out: Path, rect=None, pad=48) -> dict:
    from PIL import Image, ImageDraw
    from PIL.PngImagePlugin import PngInfo
    a, b = Image.open(before).convert("RGB"), Image.open(after).convert("RGB")
    if a.size != b.size:
        raise SystemExit(f"the stills differ in size ({a.size} and {b.size}): take both at one size")
    if rect:
        x, y, w, h = rect
        box = (x, y, x + w, y + h)
    else:
        box = diff_box(a, b)
        if box is None:
            raise SystemExit("the stills do not differ: nothing to show (same screen and state on both sides?)")
    crop = crop_box(box, a.size, pad)
    ring = (box[0] - crop[0] - 8, box[1] - crop[1] - 8, box[2] - crop[0] + 8, box[3] - crop[1] + 8)
    meta = {"source": list(a.size), "crop": list(crop), "ring": list(box)}
    info = PngInfo()
    info.add_text(CHUNK, json.dumps(meta))
    out.mkdir(parents=True, exist_ok=True)
    tiles = []
    for name, img in (("before", a), ("after", b)):
        t = img.crop(crop)
        ImageDraw.Draw(t).ellipse(ring, outline=RING, width=RING_WIDTH)
        t.save(out / f"{name}.png", pnginfo=info)
        tiles.append(t)
    w, h = tiles[0].size
    label = 28
    pair = Image.new("RGB", (w * 2 + 12, h + label), (20, 20, 24))
    d = ImageDraw.Draw(pair)
    for i, (t, name) in enumerate(zip(tiles, ("Before", "After"))):
        pair.paste(t, (i * (w + 12), label))
        d.text((i * (w + 12) + 8, 6), name, fill=(240, 240, 240))
    pair.save(out / "pair.png", pnginfo=info)
    return meta


# --------------------------------------------------------------------------------------------------------- check

def sections(text: str):
    """[(title, body)] for each '## Change ...' section."""
    out = []
    parts = re.split(r"^##\s+", text, flags=re.M)
    for p in parts[1:]:
        title, _, body = p.partition("\n")
        if re.match(r"change\b", title.strip(), re.I):
            out.append((title.strip(), body))
    return out


def split_parts(body: str) -> dict:
    """The labelled parts of a section: '**Before:**', 'Before:' or '### Before' each start one."""
    names = "|".join(PARTS)
    label = re.compile(rf"^\s*(?:[-*]\s*)?(?:\*\*)?({names})\s*:(?:\*\*)?|^#{{3,}}\s*({names})\b.*$", re.I | re.M)
    found = {}
    marks = list(label.finditer(body))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        found.setdefault((m.group(1) or m.group(2)).lower(), body[m.end():end].strip())
    return found


def words(s: str) -> int:
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)
    return len(re.findall(r"[A-Za-z0-9][\w'./-]*", s))


def images(s: str) -> list[str]:
    paths = re.findall(r"!\[[^\]]*\]\(<?([^)>]+?)>?\)", s)
    paths += [p for p in re.findall(r"`([^`]+\.(?:png|jpg|jpeg))`", s, re.I) if p not in paths]
    return paths


def still_problem(path: Path) -> str | None:
    if not path.exists():
        return f"{path}: no such file"
    try:
        from PIL import Image
    except ImportError:
        return "Pillow is not installed: pip install pillow"
    with Image.open(path) as im:
        raw = im.info.get(CHUNK)
    if not raw:
        return (f"{path.name}: not cropped and marked by approval_ask.py mark (a full-screen or unmarked still); "
                f"crop it to the area that differs and ring the difference")
    meta = json.loads(raw)
    sw, sh = meta["source"]
    x0, y0, x1, y1 = meta["crop"]
    r0, q0, r1, q1 = meta["ring"]
    big_diff = (r1 - r0) * (q1 - q0) > MAX_CROP_SHARE / 2 * sw * sh   # a change that really spans the screen
    if (x1 - x0) * (y1 - y0) > MAX_CROP_SHARE * sw * sh and not big_diff:
        return (f"{path.name}: the crop {x1 - x0}x{y1 - y0} is most of the {sw}x{sh} screen: "
                f"crop it to the area that differs (--rect)")
    return None


def check(ask: Path) -> list[str]:
    text = ask.read_text(encoding="utf-8")
    secs = sections(text)
    if not secs:
        return ["no '## Change <n>: <title>' section: give each change its own section with "
                "Before / After / Fixes / Code / Unchanged / Stills"]
    out = []
    for title, body in secs:
        got = split_parts(body)
        for part in PARTS:
            if part not in got:
                out.append(f"{title}: no {part.capitalize()}: part")
                continue
            if part != "stills" and words(got[part]) < MIN_WORDS:
                out.append(f"{title}: {part.capitalize()}: is a one-liner ({words(got[part])} words); "
                           f"say it in full, plain words")
        before = got.get("before", "")
        if before and len(re.findall(r"^\s*\d+[.)]\s+\S", before, re.M)) < MIN_STEPS:
            out.append(f"{title}: Before: needs the player's steps, numbered (1. ... 2. ...)")
        code = got.get("code", "")
        if code:
            if not re.search(r"[\w/\\-]+\.(?:cs|py|ts|js|json|asset|prefab|uss|uxml|shader|md)\b", code):
                out.append(f"{title}: Code: names no file")
            if not re.search(r"\b[A-Za-z_]\w*\s*\(|\bmethod\s+`?[A-Za-z_]\w*", code):
                out.append(f"{title}: Code: names no method")
            if not re.search(r"->|→|\bwas\b.+\bnow\b|\bfrom\b.+\bto\b", code, re.I | re.S):
                out.append(f"{title}: Code: gives no value before and after (old -> new)")
        stills = images(got.get("stills", "")) or images(body)
        if not stills:
            out.append(f"{title}: Stills: no before/after pair")
        for s in stills:
            p = Path(s)
            if not p.is_absolute():
                p = ask.parent / p
            msg = still_problem(p)
            if msg:
                out.append(f"{title}: {msg}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mark")
    m.add_argument("--before", required=True, type=Path)
    m.add_argument("--after", required=True, type=Path)
    m.add_argument("--out", required=True, type=Path)
    m.add_argument("--rect", help="X,Y,W,H of the area that differs, in source pixels")
    m.add_argument("--pad", type=int, default=48)
    c = sub.add_parser("check")
    c.add_argument("ask", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "mark":
        rect = tuple(int(v) for v in args.rect.split(",")) if args.rect else None
        meta = mark(args.before, args.after, args.out, rect, args.pad)
        print(f"crop {meta['crop']} of {meta['source']}, ringed {meta['ring']}: "
              f"{args.out / 'before.png'}, {args.out / 'after.png'}, {args.out / 'pair.png'}")
        return 0
    misses = check(args.ask)
    for line in misses:
        print(line)
    print(f"{len(misses)} miss(es)" if misses else "ok: every change is explained, with a cropped, marked pair")
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
