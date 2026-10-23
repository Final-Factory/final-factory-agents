#!/usr/bin/env python3
"""ui_look: how a UI still looks, judged on its own: the colour checks a script can make, and the critic's input (w1399).

Ben rejected three UI changes on 2026-10-16 for flaws a person sees at a glance, after the worker and the orchestrator had
passed them on numbers that compare two things (before and after, a panel against the Inventory). Two of them were colour:
the Command Core's active stop tinted the controls inside it ("the active stop color is bleeding into a bunch of the
panel's elements, it looks bad, like its washing everything out") and a pale cyan button ("the add stop bright blue is also
painful on the eyes"; w1334, game PR #1817). These look at the pixels a player sees:

    ui_look.py colour <still.png>[::<census.json>] [...] [--before <still.png>[::<census.json>] ...] [--rect x0,y0,x1,y1 ...]
                      [--same x0,y0,x1,y1:x0,y0,x1,y1 ...]
        The `Colour:` line the pull request carries (evidence-gate checklists/ui.md item 31, pr_evidence.py):
        LOUD FILL      a flat fill over 0.1 % of the screen at CIELAB L* 60 or more and C* 25 or more: a large light, coloured
                       area that outshouts a dark panel (w1334's Add stop, #57B2D0, L* 68, C* 30; master's own buttons are
                       L* 49 to 56). White and grey are not judged (on this game's panels they are icons, the logo and text),
                       and a progress or met-condition fill (an Image named *Fill*, *Progress*, *Bar*, drawn Filled) is
                       status colour by design.
        BLEED          a selected or active row of a list whose controls take on its colour. With a census: a see-through
                       control (alpha under 0.95) with the same colour settings as its twin in a plain row but drawn more
                       than delta E 5 away from it, toward the row's tint, or a see-through overlay drawn over the row's
                       controls. On a still alone, give each pair of regions that must look the same with --same.
        LOW CONTRAST   a text of an opened window under 3:1 (WCAG 2) against what is drawn behind it (needs a census for
                       where the texts are; the text colour is the census colour or the drawn glyphs, whichever is
                       stronger, so anti-aliasing never fails a text by itself). APCA Lc is printed beside it.
        A finding the --before still also shows is STANDING: listed, not counted. Exits 1 on any counted finding.
        Regions: --rect, else every opened window and dialog in the census (hud-clusters.json `openedPanels`, names with
        Dialog/Modal/Popup), else its panels; with no census at all, the whole still.

    ui_look.py pack --after <still.png>[::<census.json>|@x0,y0,x1,y1] [...] [--before <still.png> ...] [--ref <png> ...]
                    [--repo <game repo>] [--brief <brief.txt>] [--words "<quote>" ...] --out <dir>
        The design critic's whole input (unity-ui critic.md), built here so the worker's account of the change never
        reaches it: each still whole (halved while it would be over 500 KB, which Claude Code re-encodes as JPEG) and each
        window at its own pixels and 2x, the reference panels (default <repo>/docs/ui-style/ref/ref-*.png), and the person's
        quoted words in b/, which the prompt opens only after the stills are judged alone. Prints the pack id.

    ui_look.py family <still.png>::<census.json>[#<window>] [--ref <still.png>::<census.json>[#<window>] ...] [--json <out>]
        The `Family:` line (evidence-gate checklists/ui.md item 33): the window against the game's other windows (Ben,
        w1761: "the UI needs to be consistent and clean"). Each window is measured the same way:
        MIXED CORNERS   more distinct corner radii than any reference window (2 at least), read off the pixels of every
                        drawn shape: w1761's letter circles, rounded rows and Add Calculation button.
        NESTED CORNERS  a rounded shape within 4 px (or its parent's radius) of a rounded parent's edge whose radius is not
                        about the parent's less the gap: "a circle around each letter, which is right next to the rounded
                        border of the item".
        SMALL HEADER    the header (the largest text in the window's top) under 0.9x the reference headers' font size,
                        scaled by the screen heights: "the header font seems smaller than other headers".
        HEADER TWO LINES the header wraps (w1296: "fits on one line so its not pushing up against the top").
        CRAMPED <EDGE>  the gap from the content (texts, controls) to an edge under 0.75x the reference windows' and 3 px
                        or more less: "make the bottom padding a few more pixels too it feels crammed".
        References: --ref, else the other windows open in the same census. Exits 1 on any finding.

    ui_look.py crops <still.png> --out <dir> [--census <census.json>] [--rect x0,y0,x1,y1 ...] [--name <prefix>]
        Crops at the panel's own pixels (and 2x for a small one), for a critic that wants to look closer.

Rects are image pixels from the top-left corner (as the census writes them). Stills are PNG (the tour's shots); Pillow
decodes them faster when it is installed, and the script runs without it.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ui_layout as ul  # noqa: E402  (the census helpers: load, openedPanels, lab, delta_e)

# ---------------------------------------------------------------------------------------------------------------
# thresholds (w1399; calibrated in tests/test_ui_look.py on the w1334, w1386 and w1296 stills and on master's panels)

LOUD_AREA = 0.001       # a fill of this share of the screen or more (2,074 px at 1920x1080: a 150x14 bar, a 70x30 button)
LOUD_L = 60.0           # ... at CIELAB L* this or more ...
LOUD_C = 25.0           # ... and chroma C* this or more is loud on a dark panel (w1334's Add stop: L* 68, C* 30;
                        # master's buttons L* 49-56, the Technology tiles 56-64: calibration in the w1399 proof)
FLAT_RANGE = 14         # a cell whose channels vary less than this is part of a flat fill
FLAT_JOIN = 6.0         # neighbouring flat cells within this delta E of the region's colour join it
BLEED_DE = 5.0          # a control in the selected row this far off its twin in a plain row has taken on the row's colour
ROW_TINT_DE = 4.0       # the selected row's own fill this far off a plain row's: it is tinted
CONTRAST_FAIL = 3.0     # WCAG 2 ratio under which a text fails (3:1 is the floor for large text and UI parts)
CONTRAST_NOTE = 4.5     # ... and under which normal-size text is listed as weak


# ---------------------------------------------------------------------------------------------------------------
# images: PNG in and out, Pillow when it is there


class Still:
    """An RGB image: width, height and a flat bytes of r, g, b."""

    def __init__(self, width: int, height: int, data: bytes | bytearray, name: str = ""):
        self.width, self.height, self.data, self.name = width, height, bytes(data), name

    def px(self, x: int, y: int) -> tuple[int, int, int]:
        i = 3 * (y * self.width + x)
        return self.data[i], self.data[i + 1], self.data[i + 2]

    def crop(self, rect) -> "Still":
        x0, y0, x1, y1 = clamp_rect(rect, self.width, self.height)
        rows = [self.data[3 * (y * self.width + x0):3 * (y * self.width + x1)] for y in range(y0, y1)]
        return Still(x1 - x0, y1 - y0, b"".join(rows), self.name)

    def halved(self) -> "Still":
        """Half size, each pixel the mean of a 2x2 block: a whole-screen still small enough to stay a PNG (Claude Code
        re-encodes an image over 500 KB as a lower-quality JPEG; w1399 research)."""
        w, h = self.width // 2, self.height // 2
        out = bytearray(3 * w * h)
        d, W = self.data, self.width
        for y in range(h):
            r0, r1 = 3 * (2 * y) * W, 3 * (2 * y + 1) * W
            for x in range(w):
                i, j = r0 + 6 * x, r1 + 6 * x
                k = 3 * (y * w + x)
                for c in range(3):
                    out[k + c] = (d[i + c] + d[i + 3 + c] + d[j + c] + d[j + 3 + c] + 2) // 4
        return Still(w, h, out, self.name)

    def scaled(self, factor: int) -> "Still":
        """Nearest-neighbour zoom by a whole factor (UI pixels stay crisp)."""
        out = bytearray()
        for y in range(self.height):
            row = self.data[3 * y * self.width:3 * (y + 1) * self.width]
            wide = b"".join(row[3 * x:3 * x + 3] * factor for x in range(self.width))
            out += wide * factor
        return Still(self.width * factor, self.height * factor, out, self.name)


def clamp_rect(rect, width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = (int(round(v)) for v in rect)
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    return max(0, x0), max(0, y0), min(width, x1), min(height, y1)


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_png(path: str | Path) -> Still:
    """An 8-bit RGB or RGBA, non-interlaced PNG (what Unity's ScreenCapture and the tour write), without Pillow."""
    blob = Path(path).read_bytes()
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG (give the tour's .png shots; a .jpg needs Pillow)")
    pos, idat, width = 8, [], 0
    height = depth = ctype = interlace = 0
    while pos < len(blob):
        length, kind = struct.unpack(">I4s", blob[pos:pos + 8])
        chunk = blob[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"IDAT":
            idat.append(chunk)
        elif kind == b"IEND":
            break
        pos += 12 + length
    if depth != 8 or ctype not in (2, 6) or interlace:
        raise ValueError(f"{path}: an 8-bit RGB or RGBA PNG without interlace is needed (depth {depth}, colour type {ctype})")
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(b"".join(idat))
    stride = width * bpp
    prev = bytearray(stride)
    out = bytearray()
    pos = 0
    for _ in range(height):
        kind = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if kind == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif kind == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif kind == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                upleft = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prev[i], upleft)) & 0xFF
        if bpp == 4:
            out += b"".join(bytes(line[i:i + 3]) for i in range(0, stride, 4))
        else:
            out += line
        prev = line
    return Still(width, height, out, Path(path).stem)


def load_still(path: str | Path) -> Still:
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        return read_png(path)
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        return Still(rgb.width, rgb.height, rgb.tobytes(), Path(path).stem)


def write_png(path: str | Path, still: Still) -> None:
    rows = b"".join(b"\x00" + still.data[3 * y * still.width:3 * (y + 1) * still.width] for y in range(still.height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", still.width, still.height, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------------------------------------------------------
# colour


def lch(rgb) -> tuple[float, float, float]:
    """CIELAB lightness L* (0-100), chroma C* and hue angle (degrees)."""
    L, a, b = ul.lab(rgb)
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def hex_of(rgb) -> str:
    return "#" + "".join(f"{int(round(v)):02X}" for v in rgb[:3])


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    """WCAG 2 relative luminance."""
    r, g, b = (_lin(float(v)) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def apca_lc(text, background) -> float:
    """APCA-W3 0.0.98G-4g lightness contrast Lc of a text colour on a background (negative: light text on dark)."""
    def y(rgb):
        r, g, b = ((float(v) / 255.0) ** 2.4 for v in rgb[:3])
        y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
        return y if y > 0.022 else y + (0.022 - y) ** 1.414
    yt, yb = y(text), y(background)
    if abs(yb - yt) < 0.0005:
        return 0.0
    if yb > yt:
        sapc = (yb ** 0.56 - yt ** 0.57) * 1.14
        return 0.0 if sapc < 0.1 else (sapc - 0.027) * 100
    sapc = (yb ** 0.65 - yt ** 0.62) * 1.14
    return 0.0 if sapc > -0.1 else (sapc + 0.027) * 100


def blend(top, alpha: float, under):
    return tuple(alpha * t + (1 - alpha) * u for t, u in zip(top[:3], under[:3]))


def dominant(still: Still, rect=None, step: int = 1, bin_size: int = 8):
    """The most common colour in a rect (pixels binned by bin_size per channel, the bin's mean returned) and its share."""
    x0, y0, x1, y1 = clamp_rect(rect or (0, 0, still.width, still.height), still.width, still.height)
    bins: dict[tuple[int, int, int], list[int]] = {}
    count = 0
    for y in range(y0, y1, step):
        base = 3 * y * still.width
        for x in range(x0, x1, step):
            i = base + 3 * x
            r, g, b = still.data[i], still.data[i + 1], still.data[i + 2]
            key = (r // bin_size, g // bin_size, b // bin_size)
            acc = bins.get(key)
            if acc is None:
                bins[key] = [r, g, b, 1]
            else:
                acc[0] += r
                acc[1] += g
                acc[2] += b
                acc[3] += 1
            count += 1
    if not count:
        return None, 0.0
    r, g, b, n = max(bins.values(), key=lambda v: v[3])
    return (r / n, g / n, b / n), n / count


# ---------------------------------------------------------------------------------------------------------------
# regions: where the UI under review is


def window_rects(census: dict, patterns: list[str] | None = None) -> list[tuple[str, list[float]]]:
    """The rect of every opened window and dialog in a census: per window (an `openedPanels` match or a component named
    *Dialog*/*Modal*/*Popup*), the box around its drawn Images (a full-screen dimmer behind a dialog left out)."""
    if patterns is None:
        patterns = ul.opened_patterns(json.loads(ul.DEFAULT_CLUSTERS.read_text(encoding="utf-8")))
    sw, sh = (census.get("screen") or [1920, 1080])[:2]
    boxes: dict[str, list[float]] = {}
    for e in census.get("elements", []):
        if e.get("kind") not in ("Image", "RawImage") or e.get("maskOnly") or e.get("alpha", 1.0) < 0.2:
            continue
        if any(i in e["path"] for i in ul.IGNORE):
            continue
        prefix = ul.opened_prefix(e["path"], patterns)
        if prefix is None:
            parts = e["path"].split("/")
            hits = [i for i, p in enumerate(parts) if ul.DIALOG.search(p)]
            if not hits:
                continue
            prefix = "/".join(parts[:hits[0] + 1])
        r = e.get("visible") or e["rect"]
        if ul.area(r) < 400 or ul.area(r) > 0.6 * sw * sh:
            continue
        b = boxes.get(prefix)
        boxes[prefix] = list(r) if b is None else [min(b[0], r[0]), min(b[1], r[1]), max(b[2], r[2]), max(b[3], r[3])]
    return list(boxes.items())


# ---------------------------------------------------------------------------------------------------------------
# LOUD FILL


def flat_fills(still: Still, rect, cell: int = 2) -> list[dict]:
    """Flat regions inside a rect: cells of cell x cell pixels whose channels vary less than FLAT_RANGE, joined with their
    flat neighbours of nearly the same colour. Each region: its rect, pixel area and mean colour."""
    x0, y0, x1, y1 = clamp_rect(rect, still.width, still.height)
    cols, rows = (x1 - x0) // cell, (y1 - y0) // cell
    if cols <= 0 or rows <= 0:
        return []
    means: list = [None] * (cols * rows)
    data, width = still.data, still.width
    span = 3 * cols * cell
    for cy in range(rows):
        lines = [data[3 * (y * width + x0):3 * (y * width + x0) + span] for y in range(y0 + cy * cell, y0 + cy * cell + cell)]
        for cx in range(cols):
            a = 3 * cx * cell
            block = b"".join(line[a:a + 3 * cell] for line in lines)
            rs, gs, bs = block[0::3], block[1::3], block[2::3]
            if max(rs) - min(rs) < FLAT_RANGE and max(gs) - min(gs) < FLAT_RANGE and max(bs) - min(bs) < FLAT_RANGE:
                n = len(rs)
                means[cy * cols + cx] = (sum(rs) / n, sum(gs) / n, sum(bs) / n)
    cache: dict = {}

    def lab_of(m):
        key = (int(m[0]), int(m[1]), int(m[2]))
        found = cache.get(key)
        if found is None:
            found = cache[key] = ul.lab(key)
        return found
    labs = [lab_of(m) if m is not None else None for m in means]
    seen = bytearray(cols * rows)
    regions = []
    for start in range(cols * rows):
        if seen[start] or labs[start] is None:
            continue
        seed = labs[start]
        stack, members = [start], []
        seen[start] = 1
        while stack:
            k = stack.pop()
            members.append(k)
            cx, cy = k % cols, k // cols
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if 0 <= nx < cols and 0 <= ny < rows:
                    j = ny * cols + nx
                    if not seen[j] and labs[j] is not None and math.dist(labs[j], seed) <= FLAT_JOIN:
                        seen[j] = 1
                        stack.append(j)
        if len(members) < 8:
            continue
        xs = [k % cols for k in members]
        ys = [k // cols for k in members]
        mean = tuple(sum(means[k][ch] for k in members) / len(members) for ch in range(3))
        regions.append({"rect": [x0 + min(xs) * cell, y0 + min(ys) * cell, x0 + (max(xs) + 1) * cell, y0 + (max(ys) + 1) * cell],
                        "area": len(members) * cell * cell, "colour": mean})
    return regions


def loud_fills(still: Still, rects, screen_px: float | None = None) -> list[dict]:
    """Flat fills large, bright and saturated enough to outshout a dark panel. White and grey are left out: on this game's
    panels the big white shapes are icons, the logo and text (w1399 sweep of master's Esc menu), not fills."""
    screen_px = screen_px or float(still.width * still.height)
    cell = max(1, int(round(still.height / 540.0)))
    found = []
    for rect in rects:
        for region in flat_fills(still, rect, cell):
            if region["area"] < LOUD_AREA * screen_px:
                continue
            L, C, h = lch(region["colour"])
            if L >= LOUD_L and C >= LOUD_C:
                found.append(dict(region, L=L, C=C, share=region["area"] / screen_px, why="bright and saturated"))
    return found


# ---------------------------------------------------------------------------------------------------------------
# BLEED


def _centre(r):
    return (r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0


def _inside(r, box) -> bool:
    cx, cy = _centre(r)
    return box[0] <= cx <= box[2] and box[1] <= cy <= box[3]


def list_rows(census: dict) -> list[list[dict]]:
    """Rows of a list: two or more Images with the same path (clones under one parent) and about the same width, each
    the row's own background. Each group sorted top to bottom."""
    groups: dict[str, list[dict]] = {}
    for e in census.get("elements", []):
        if e.get("kind") != "Image" or e.get("maskOnly") or any(i in e["path"] for i in ul.IGNORE):
            continue
        groups.setdefault(e["path"], []).append(e)
    out = []
    for path, rows in groups.items():
        rows = [r for r in rows if ul.area(r.get("visible") or r["rect"]) >= 600]
        if len(rows) < 2:
            continue
        widths = [(r.get("visible") or r["rect"])[2] - (r.get("visible") or r["rect"])[0] for r in rows]
        if max(widths) - min(widths) > 0.1 * max(widths):
            continue
        out.append(sorted(rows, key=lambda r: (r.get("visible") or r["rect"])[1]))
    return out


def _colour_key(e: dict):
    return tuple(int(v) for v in ul.rgba(e.get("color") or "#FFFFFFFF"))


def _see_through(e: dict) -> bool:
    """Drawn with alpha under 0.95 (its own colour's alpha, or a CanvasGroup's): what is behind it shows through."""
    own = ul.rgba(e.get("color") or "#FFFFFFFF")[3] / 255.0
    return min(own, float(e.get("alpha", 1.0))) < 0.95


def bleed_in_census(census: dict, still: Still, label: str = "") -> list[dict]:
    """A selected or active row whose colour the controls inside it take on (w1334 round 2). A list is two or more rows of
    one path (clones under one parent); the selected row is the one whose own colour differs from the others' (at most a
    third of them, all in one colour). Inside it, a control can only take the row's colour two ways, and both are found:

    - it is see-through (alpha under 0.95) and has the same colour settings as its twin in a plain row (same path, same
      place in the row), yet is drawn more than BLEED_DE away from it, toward the row's tint. A control the code recolours
      on purpose (a lit number, a red remove button) has another colour setting, so it is a state mark, not a bleed;
    - an overlay: a see-through Image the plain row has not, covering most of the row and drawn above its controls
      (Material's rule: the state layer goes between the container and its content, never over the content)."""
    found = []
    elements = census.get("elements", [])
    for rows in list_rows(census):
        keys = [_colour_key(r) for r in rows]
        common = max(set(keys), key=keys.count)
        odd = [r for r, k in zip(rows, keys) if k != common]
        plain = [r for r, k in zip(rows, keys) if k == common]
        if not odd or not plain or len(odd) * 3 > len(rows) + 1 or len({_colour_key(r) for r in odd}) > 1:
            continue
        for row in odd:
            rr = row.get("visible") or row["rect"]
            twin = min(plain, key=lambda p: abs((p.get("visible") or p["rect"])[1] - rr[1]))
            tr = twin.get("visible") or twin["rect"]
            row_col, _ = dominant(still, rr, step=2)
            twin_col, _ = dominant(still, tr, step=2)
            if row_col is None or twin_col is None:
                continue
            tint = [a - b for a, b in zip(ul.lab(row_col), ul.lab(twin_col))]
            row_shift = math.hypot(tint[1], tint[2]) if ul.delta_e(row_col, twin_col) >= ROW_TINT_DE else 0.0
            controls = []
            inside = [e for e in elements if e is not row and e.get("kind") in ("Image", "RawImage")
                      and e["path"].startswith(row["path"] + "/") and _inside(e.get("visible") or e["rect"], rr)]
            twin_inside = [m for m in elements if m is not twin and m["path"].startswith(twin["path"] + "/")
                           and _inside(m.get("visible") or m["rect"], tr)]
            for e in inside:
                er = e.get("visible") or e["rect"]
                if ul.area(er) < 80:
                    continue
                off = (er[0] - rr[0], er[1] - rr[1])
                mates = [m for m in twin_inside if m["path"] == e["path"]]
                mate = min(mates, key=lambda m: math.dist(off, ((m.get("visible") or m["rect"])[0] - tr[0],
                                                               (m.get("visible") or m["rect"])[1] - tr[1]))) if mates else None
                mr = (mate.get("visible") or mate["rect"]) if mate else None
                if mate is None or math.dist(off, (mr[0] - tr[0], mr[1] - tr[1])) > 8:
                    # Not in the plain row: an overlay over most of the row, drawn above the controls, tints them all.
                    if _see_through(e) and ul.area(er) >= 0.6 * ul.area(rr):
                        over = [c for c in inside if c is not e and c.get("depth", 0) < e.get("depth", 0)
                                and ul.area(c.get("visible") or c["rect"]) >= 80]
                        if over:
                            controls.append({"path": e["path"], "rect": er, "de": 0.0, "now": None, "plain": None,
                                             "alpha": e.get("alpha", 1.0), "overlay": len(over)})
                    continue
                if not _see_through(e) or _colour_key(e) != _colour_key(mate) or e.get("sprite") != mate.get("sprite"):
                    continue
                a, _ = dominant(still, er)
                b, _ = dominant(still, mr)
                if a is None or b is None:
                    continue
                de = ul.delta_e(a, b)
                la, lb = ul.lab(a), ul.lab(b)
                move = (la[1] - lb[1], la[2] - lb[2])
                toward = row_shift > 0 and (move[0] * tint[1] + move[1] * tint[2]) > 0.5 * math.hypot(*move) * row_shift
                if de > BLEED_DE and (toward or row_shift == 0):
                    controls.append({"path": e["path"], "rect": er, "de": de, "now": a, "plain": b,
                                     "alpha": min(ul.rgba(e.get("color") or "#FFFFFFFF")[3] / 255.0, e.get("alpha", 1.0))})
            if controls:
                found.append({"label": label, "row": row["path"], "rect": rr, "row_colour": row.get("color"),
                              "plain_colour": twin.get("color"), "row_de": ul.delta_e(row_col, twin_col), "controls": controls})
    return found


def same_pairs(still: Still, pairs: list[tuple[list[float], list[float]]], label: str = "") -> list[dict]:
    """--same A:B: two regions that must look the same (a control in the active row and its twin in a plain row)."""
    found = []
    for a_rect, b_rect in pairs:
        a, _ = dominant(still, a_rect)
        b, _ = dominant(still, b_rect)
        if a is None or b is None:
            continue
        de = ul.delta_e(a, b)
        if de > BLEED_DE:
            found.append({"label": label, "row": "--same", "rect": a_rect, "row_colour": None, "plain_colour": None,
                          "row_de": de, "controls": [{"path": f"{fmt_rect(a_rect)} vs {fmt_rect(b_rect)}", "rect": a_rect,
                                                       "de": de, "now": a, "plain": b, "alpha": None}]})
    return found


# ---------------------------------------------------------------------------------------------------------------
# LOW CONTRAST


TAG = re.compile(r"<[^>]+>")


def text_contrast(census: dict, still: Still, rects, label: str = "") -> tuple[list[dict], list[dict]]:
    """Every text inside the regions against what is drawn behind it. Returns (fails under CONTRAST_FAIL, weak ones)."""
    fails, weak = [], []
    for e in census.get("elements", []):
        if "Text" not in e.get("kind", "") or any(i in e["path"] for i in ul.IGNORE):
            continue
        text = TAG.sub("", e.get("text") or "").strip()
        if not text or e.get("alpha", 1.0) < 0.2:
            continue
        r = e.get("textRect") or e.get("visible") or e["rect"]
        if ul.area(r) < 40 or not any(_inside(r, box) for box in rects):
            continue
        bg, share = dominant(still, r)
        if bg is None:
            continue
        # The drawn glyphs: the pixels furthest from the background's luminance (anti-aliased edges sit between).
        x0, y0, x1, y1 = clamp_rect(r, still.width, still.height)
        lb = luminance(bg)
        far = sorted((abs(luminance(still.px(x, y)) - lb), still.px(x, y)) for y in range(y0, y1) for x in range(x0, x1))
        core = [p for _, p in far[-max(1, len(far) // 30):]]
        drawn = tuple(sum(p[c] for p in core) / len(core) for c in range(3))
        census_col = ul.rgba(e.get("color") or "#FFFFFFFF")
        stated = blend(census_col, e.get("alpha", 1.0), bg)
        best = max((contrast_ratio(drawn, bg), drawn), (contrast_ratio(stated, bg), stated))
        ratio, colour = best
        item = {"label": label, "path": e["path"], "text": text[:30], "rect": r, "ratio": ratio, "lc": apca_lc(colour, bg),
                "fg": colour, "bg": bg}
        if ratio < CONTRAST_FAIL:
            fails.append(item)
        elif ratio < CONTRAST_NOTE and (r[3] - r[1]) < 24 * still.height / 1080.0:
            weak.append(item)
    return fails, weak


# ---------------------------------------------------------------------------------------------------------------
# reporting


def fmt_rect(r) -> str:
    return f"{r[0]:.0f},{r[1]:.0f} {r[2]:.0f},{r[3]:.0f}"


def colour_report(results: list[dict], measured: dict) -> tuple[list[str], int]:
    loud = [f for r in results for f in r["loud"]]
    bleed = [f for r in results for f in r["bleed"]]
    fails = [f for r in results for f in r["fails"]]
    weak = [f for r in results for f in r["weak"]]
    head = (f"Colour: {len(loud)} loud fill(s), {len(bleed)} state tint(s) bleeding into controls, {len(fails)} low-contrast "
            f"text(s)")
    head += (f" over {len(results)} still(s) (ui_look.py colour: a fill over {LOUD_AREA * 100:g} % of the screen at L* "
             f"{LOUD_L:g}+ and C* {LOUD_C:g}+; a control in a selected row over delta E {BLEED_DE:g} off "
             f"its twin in a plain row; text under {CONTRAST_FAIL:g}:1")
    head += ")"
    standing = {k: [f for r in results for f in r.get("standing", {}).get(k, [])] for k in ("loud", "bleed", "fails")}
    if any(standing.values()):
        head += (f"; standing (on the before still too, not counted): {len(standing['loud'])} loud, "
                 f"{len(standing['bleed'])} bleeding, {len(standing['fails'])} low-contrast")
    notes = []
    if not measured.get("before"):
        notes.append("no before still: what master already had is counted too")
    if not measured.get("bleed"):
        notes.append("state tints not measured (no census with list rows, no --same)")
    if not measured.get("contrast"):
        notes.append("contrast not measured (no census)")
    if measured.get("whole"):
        notes.append("no census: the whole still was checked for loud fills (give --rect or the census)")
    if measured.get("no_panel"):
        notes.append("a census with no window or panel: loud fills not measured there (give --rect)")
    if notes:
        head += "; " + "; ".join(notes)
    lines = [head]
    for kind, items in standing.items():
        for f in items[:6]:
            what = {"loud": lambda f: f"{hex_of(f['colour'])} fill at {fmt_rect(f['rect'])}",
                    "bleed": lambda f: f"{ul.short(f['row'], 2)}",
                    "fails": lambda f: f"\"{f['text']}\" {f['ratio']:.1f}:1"}[kind](f)
            lines.append(f"  standing {kind} {f['label']}: {what}")
    for f in loud:
        lines.append(f"  LOUD FILL {f['label']}: {f['rect'][2] - f['rect'][0]:.0f}x{f['rect'][3] - f['rect'][1]:.0f} at "
                     f"{fmt_rect(f['rect'])}, {hex_of(f['colour'])} L* {f['L']:.0f} C* {f['C']:.0f}, {f['share'] * 100:.2f} % "
                     f"of the screen ({f['why']})")
    for f in bleed:
        where = f"{ul.short(f['row'], 2)} (its own colour {f['row_colour']} against {f['plain_colour']}, drawn delta E " \
                f"{f['row_de']:.1f})" if f["row"] != "--same" else "--same"
        lines.append(f"  BLEED {f['label']}: {where}")
        for c in f["controls"][:8]:
            if c.get("overlay"):
                lines.append(f"    {ul.short(c['path'], 3)}: a see-through overlay (alpha {c['alpha']:.2f}) over "
                             f"{c['overlay']} control(s) of the row; a state layer goes under the content")
                continue
            lines.append(f"    {ul.short(c['path'], 3)}: {hex_of(c['now'])} against {hex_of(c['plain'])} in the plain row, "
                         f"delta E {c['de']:.1f}" + (f", alpha {c['alpha']:.2f}" if c.get("alpha") is not None else ""))
        if len(f["controls"]) > 8:
            lines.append(f"    ... and {len(f['controls']) - 8} more")
    for f in fails:
        lines.append(f"  LOW CONTRAST {f['label']}: \"{f['text']}\" {f['ratio']:.1f}:1 (APCA Lc {f['lc']:.0f}), "
                     f"{hex_of(f['fg'])} on {hex_of(f['bg'])} at {fmt_rect(f['rect'])}")
    for f in weak[:12]:
        lines.append(f"  weak (listed, not counted) {f['label']}: \"{f['text']}\" {f['ratio']:.1f}:1 (APCA Lc {f['lc']:.0f})")
    return lines, len(loud) + len(bleed) + len(fails)


def parse_rect(text: str) -> list[float]:
    parts = [float(v) for v in re.split(r"[,\s]+", text.strip()) if v]
    if len(parts) != 4:
        raise ValueError(f"a rect is x0,y0,x1,y1, got {text!r}")
    return parts


def panel_rects(census: dict) -> list[list[float]]:
    """With no opened window in a census: every drawn panel (an Image over 2 % of the screen, alpha 0.5 or more, under 60 %
    of it), so a full-screen menu is checked and the game world behind the HUD is not."""
    sw, sh = (census.get("screen") or [1920, 1080])[:2]
    out = []
    for e in census.get("elements", []):
        if e.get("kind") != "Image" or e.get("maskOnly") or e.get("alpha", 1.0) < 0.5 or any(i in e["path"] for i in ul.IGNORE):
            continue
        r = e.get("visible") or e["rect"]
        if 0.02 * sw * sh <= ul.area(r) <= 0.6 * sw * sh:
            out.append(list(r))
    return out


PROGRESS = re.compile(r"(^|/)[^/]*(Fill|Progress|Bar|Meter)[^/]*$", re.IGNORECASE)


def progress_fill(census: dict, rect) -> bool:
    """Whether a fill is a progress or status bar (an Image named *Fill*, *Progress*, *Bar*, *Meter*, or drawn Filled)
    covering most of it: status colour there is by design (Factorio fills a met train condition green, FFF #279)."""
    for e in census.get("elements", []):
        if e.get("kind") != "Image" or not (PROGRESS.search(e["path"]) or e.get("imageType") == "Filled"):
            continue
        r = e.get("visible") or e["rect"]
        if ul.inter(r, rect) and ul.area(ul.inter(r, rect)) >= 0.6 * ul.area(rect):
            return True
    return False


def judge(still: Still, census: dict | None, rects: list, label: str, same: list, measured: dict) -> dict:
    """Every colour finding on one still."""
    if not rects and census:
        rects = [r for _, r in window_rects(census)] or panel_rects(census)
    if not rects and census is None:
        rects = [[0, 0, still.width, still.height]]
        measured["whole"] = True
    screen = census.get("screen") if census else None
    screen_px = float(screen[0] * screen[1]) if screen else float(still.width * still.height)
    loud = [dict(f, label=label) for f in loud_fills(still, rects, screen_px)] if rects else []
    if census:
        loud = [f for f in loud if not progress_fill(census, f["rect"])]
    unique = []
    for f in loud:  # a fill inside two overlapping window rects (the dock and its window) is one fill
        if not any(_iou(f["rect"], g["rect"]) >= 0.8 for g in unique):
            unique.append(f)
    loud = unique
    if not rects:
        measured["no_panel"] = True
    bleed = []
    if census:
        bleed += bleed_in_census(census, still, label)
        measured["bleed"] = measured.get("bleed") or bool(list_rows(census))
    if same:
        bleed += same_pairs(still, same, label)
        measured["bleed"] = True
    fails, weak = ([], [])
    if census and rects:
        fails, weak = text_contrast(census, still, rects, label)
        measured["contrast"] = True
    return {"label": label, "loud": loud, "bleed": bleed, "fails": fails, "weak": weak}


def _iou(a, b) -> float:
    i = ul.area(ul.inter(a, b)) if ul.inter(a, b) else 0.0
    u = ul.area(a) + ul.area(b) - i
    return i / u if u else 0.0


def split_standing(after: dict, before: dict) -> dict:
    """What the before still already had is STANDING (listed, not counted): a loud fill in the same place and colour, a
    bleed in the same row and control, a low-contrast text of the same element and words. What is left is this change's.
    A fill counts as standing when the before had one at least as loud in the same place, whatever its hue."""
    standing = {"loud": [], "bleed": [], "fails": []}
    keep = {"loud": [], "bleed": [], "fails": []}
    for f in after["loud"]:
        same = any(_iou(f["rect"], g["rect"]) >= 0.5 and g["L"] >= f["L"] - 3 and g["C"] >= f["C"] - 3 for g in before["loud"])
        (standing if same else keep)["loud"].append(f)
    for f in after["bleed"]:
        names = {c["path"] for c in f["controls"]}
        same = any(g["row"] == f["row"] and names <= {c["path"] for c in g["controls"]} for g in before["bleed"])
        (standing if same else keep)["bleed"].append(f)
    for f in after["fails"]:
        same = any(g["path"] == f["path"] and g["text"] == f["text"] for g in before["fails"])
        (standing if same else keep)["fails"].append(f)
    return dict(after, loud=keep["loud"], bleed=keep["bleed"], fails=keep["fails"], standing=standing)


def run_colour(args) -> int:
    def split(spec: str):
        still, _, census = spec.partition("::")
        return still, census or None
    stills = [split(s) for s in args.still]
    censuses = [ul.load(c) for c in (args.census or [])]
    befores = [split(s) for s in (args.before or [])]
    same = []
    for spec in args.same or []:
        a, b = spec.split(":")
        same.append((parse_rect(a), parse_rect(b)))
    results, measured = [], {}
    for i, (path, census_path) in enumerate(stills):
        still = load_still(path)
        census = ul.load(census_path) if census_path else (
            censuses[i] if i < len(censuses) else (censuses[0] if len(censuses) == 1 else None))
        rects = [parse_rect(r) for r in args.rect or []]
        result = judge(still, census, list(rects), Path(path).stem, same, measured)
        if i < len(befores):
            b_path, b_census = befores[i]
            before = judge(load_still(b_path), ul.load(b_census) if b_census else census, list(rects), Path(b_path).stem,
                           same, {})
            result = split_standing(result, before)
            measured["before"] = True
        results.append(result)
    lines, flagged = colour_report(results, measured)
    print("\n".join(lines))
    return 1 if flagged else 0


def run_crops(args) -> int:
    still = load_still(args.still)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = args.name or Path(args.still).stem
    rects = [("rect", parse_rect(r)) for r in args.rect or []]
    if not rects and args.census:
        rects = [(ul.short(p, 1).split("/")[-1], r) for p, r in window_rects(ul.load(args.census))]
    written = []
    full = out / f"{name}-full.png"
    write_png(full, still)
    written.append(str(full))
    for i, (what, rect) in enumerate(rects):
        x0, y0, x1, y1 = clamp_rect([rect[0] - 12, rect[1] - 12, rect[2] + 12, rect[3] + 12], still.width, still.height)
        panel = still.crop((x0, y0, x1, y1))
        tag = re.sub(r"[^A-Za-z0-9]+", "-", what).strip("-").lower() or f"panel{i}"
        tiles = []
        step = 1400
        for ty in range(0, panel.height, step):
            for tx in range(0, panel.width, step):
                tiles.append(panel.crop((tx, ty, min(panel.width, tx + step + 100), min(panel.height, ty + step + 100))))
        for j, tile in enumerate(tiles):
            p = out / f"{name}-{tag}{'' if len(tiles) == 1 else f'-{j + 1}'}.png"
            write_png(p, tile)
            written.append(str(p))
            if max(tile.width, tile.height) <= 750:
                z = out / f"{name}-{tag}{'' if len(tiles) == 1 else f'-{j + 1}'}-2x.png"
                write_png(z, tile.scaled(2))
                written.append(str(z))
    print("\n".join(written))
    return 0


# ---------------------------------------------------------------------------------------------------------------
# FAMILY: does the window look like one of the game's other windows (w1818)

CORNER_ROWS = 24        # pixel rows from each corner the radius fit reads (a radius over 24 px reads as 24)
CORNER_DE = 8.0         # a shape at least this far (delta E) from what is drawn around it has corners that can be read
RADIUS_SAME = 1.5       # two radii this close in px, or within 20 % of each other, are one radius
RADIUS_ROUND = 1.5      # a corner under this radius is square
NEST_GAP = 4.0          # a rounded shape this close (px) to its rounded parent's edge, or nearer than the parent's radius,
NEST_OFF = 2.5          # sits tight inside it, and a radius this far from (the parent's radius less the gap) is not nested
HEADER_SMALL = 0.9      # a header font under this share of the reference windows' header font is smaller (w1761)
EDGE_CRAMPED = 0.75     # an edge gap under this share of the reference windows' gap and at least EDGE_MIN_DIFF px under
EDGE_MIN_DIFF = 3.0     # it is cramped (Ben, w1761: "make the bottom padding a few more pixels too it feels crammed")


def _coverage(p, inside, outside) -> float:
    """How much of a pixel is the shape: its distance from the colour around the shape over the shape's own distance
    from it, so a border drawn lighter than both the fill and the background (the Fleet panel's number fields) counts
    as the shape's edge."""
    n = math.dist(inside, outside)
    return min(1.0, math.dist(p, outside) / n) if n else 0.0


def corner_radius(still: Still, rect, corner: str) -> float | None:
    """The radius of one corner of a drawn shape, in screen px, read off the pixels: in each of the first rows from the
    corner, how far in the shape starts (the sum of the uncovered share of each pixel up to the first fully covered one),
    fitted to a circle's edge, r - sqrt(r^2 - (r - k - 0.5)^2). None when the shape is too small or too close in colour
    to what is around it."""
    x0, y0, x1, y1 = (int(round(v)) for v in rect)
    w, h = x1 - x0, y1 - y0
    left, top = corner[1] == "l", corner[0] == "t"
    ox, oy = (x0 - 2 if left else x1 + 1), (y0 - 2 if top else y1 + 1)
    if w < 8 or h < 8 or not (0 <= ox < still.width and 0 <= oy < still.height) or x0 < 0 or y0 < 0 or \
            x1 > still.width or y1 > still.height:
        return None

    def at(dx, dy):
        return still.px(x0 + dx if left else x1 - 1 - dx, y0 + dy if top else y1 - 1 - dy)
    outside = still.px(ox, oy)
    samples = [at(w // 2, 2), at(w // 2, 3), at(2, h // 2), at(3, h // 2)]
    inside = tuple(sorted(s[c] for s in samples)[1] for c in range(3))
    if ul.delta_e(inside, outside) < CORNER_DE:
        return None
    rows = min(CORNER_ROWS, h // 2)
    span = min(CORNER_ROWS + 2, w // 2)
    xs = []
    for k in range(rows):
        uncovered = 0.0
        for dx in range(span):
            cov = _coverage(at(dx, k), inside, outside)
            uncovered += 1.0 - cov
            if cov >= 0.95:
                break
        else:
            continue
        xs.append((k, uncovered))
    if len(xs) < 3:
        return None
    best, best_err = 0.0, float("inf")
    for step in range(int(4 * min(rows, span)) + 1):
        r = step / 4
        err = 0.0
        for k, x in xs:
            dy = r - k - 0.5
            err += (x - (r - math.sqrt(r * r - dy * dy) if dy > 0 else 0.0)) ** 2
        if err < best_err - 1e-9:
            best, best_err = r, err
    return best


def shape_radius(still: Still, rect) -> float | None:
    """A shape's corner radius: the median of its readable corners (two or more), so one corner under an icon or a
    neighbour does not decide it."""
    rs = sorted(r for r in (corner_radius(still, rect, c) for c in ("tl", "tr", "bl", "br")) if r is not None)
    if len(rs) < 2:
        return None
    return rs[len(rs) // 2] if len(rs) % 2 else (rs[len(rs) // 2 - 1] + rs[len(rs) // 2]) / 2


def radius_groups(radii: list[float]) -> list[float]:
    """The distinct radii among rounded corners: values within RADIUS_SAME px or 20 % of the group's first are one."""
    groups: list[list[float]] = []
    for r in sorted(r for r in radii if r >= RADIUS_ROUND):
        if groups and (r - groups[-1][0] <= RADIUS_SAME or r <= 1.2 * groups[-1][0]):
            groups[-1].append(r)
        else:
            groups.append([r])
    return [round(sum(g) / len(g), 1) for g in groups]


def _window_prefix(census: dict, fragment: str) -> str:
    """The census path of the window a fragment names: every path holding it, cut just after the segment it ends in."""
    hits = [e["path"] for e in census.get("elements", []) if fragment in e["path"]]
    if not hits:
        raise ValueError(f"no element in the census has {fragment!r} in its path")
    p = min(hits, key=len)
    cut = p.find(fragment) + len(fragment)
    nxt = p.find("/", cut)
    return p if nxt < 0 else p[:nxt]


def window_family(still: Still, census: dict, prefix: str) -> dict:
    """One window measured for the family check: its header (font size, lines, gap to the top), the gap from its content
    (texts and controls) to each edge, and the corner radius of every drawn shape in it, read off the pixels."""
    sw, sh = (census.get("screen") or [still.width, still.height])[:2]
    members = [e for e in census.get("elements", [])
               if (e["path"] == prefix or e["path"].startswith(prefix + "/")) and not e.get("maskOnly")
               and e.get("alpha", 1.0) >= 0.2 and not any(i in e["path"] for i in ul.IGNORE)
               and ul.area(e.get("visible") or e["rect"]) > 0]
    images = [e for e in members if e.get("kind") in ("Image", "RawImage")]
    boxes = [e.get("visible") or e["rect"] for e in images if 400 <= ul.area(e.get("visible") or e["rect"]) <= 0.6 * sw * sh]
    if not boxes:
        raise ValueError(f"{prefix}: no drawn image to box the window with")
    win = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
    wh = win[3] - win[1]
    texts = [e for e in members if "Text" in e.get("kind", "") and (e.get("text") or "").strip()]
    top_texts = [e for e in texts if (e.get("textRect") or e["rect"])[1] - win[1] <= max(60.0, 0.2 * wh)]
    header = None
    if top_texts:
        h = max(top_texts, key=lambda e: (e.get("fontSize") or 0, -(e.get("textRect") or e["rect"])[1]))
        tr = h.get("textRect") or h["rect"]
        header = {"path": h["path"], "text": h.get("text", ""), "fontSize": h.get("fontSize"), "lines": h.get("lines"),
                  "top": round(tr[1] - win[1], 1), "canvasOrder": h.get("canvasOrder")}
    content = [e.get("textRect") or e.get("visible") or e["rect"] for e in texts] + \
              [e.get("visible") or e["rect"] for e in members if e.get("selectable")]
    edges = None
    if content:
        edges = {"left": round(min(r[0] for r in content) - win[0], 1), "top": round(min(r[1] for r in content) - win[1], 1),
                 "right": round(win[2] - max(r[2] for r in content), 1),
                 "bottom": round(win[3] - max(r[3] for r in content), 1)}
    shapes = []
    for e in images:
        r = e.get("visible") or e["rect"]
        if not e.get("sprite") or e.get("alpha", 1.0) < 0.5 or min(r[2] - r[0], r[3] - r[1]) < 8:
            continue
        rad = shape_radius(still, r)
        if rad is not None:
            shapes.append({"path": e["path"], "rect": [round(v, 1) for v in r], "radius": rad,
                           "circle": rad >= 0.45 * min(r[2] - r[0], r[3] - r[1])})
    nested = []
    for c in shapes:
        parents = [p for p in shapes if p is not c and p["radius"] >= 2 and ul.area(p["rect"]) > ul.area(c["rect"])
                   and p["rect"][0] - 1 <= c["rect"][0] and p["rect"][1] - 1 <= c["rect"][1]
                   and c["rect"][2] <= p["rect"][2] + 1 and c["rect"][3] <= p["rect"][3] + 1]
        if not parents or c["radius"] < RADIUS_ROUND:
            continue
        p = min(parents, key=lambda q: ul.area(q["rect"]))
        gap = min(c["rect"][0] - p["rect"][0], c["rect"][1] - p["rect"][1], p["rect"][2] - c["rect"][2],
                  p["rect"][3] - c["rect"][3])
        if gap > max(NEST_GAP, p["radius"]):
            continue
        want = max(0.0, p["radius"] - max(gap, 0.0))
        if abs(c["radius"] - want) > max(NEST_OFF, 0.35 * max(c["radius"], p["radius"])):
            nested.append({"inner": c["path"], "inner_radius": c["radius"], "circle": c["circle"], "outer": p["path"],
                           "outer_radius": p["radius"], "gap": round(gap, 1)})
    return {"window": prefix, "rect": [round(v, 1) for v in win], "screen": [sw, sh], "header": header, "edges": edges,
            "shapes": shapes, "radii": radius_groups([s["radius"] for s in shapes]), "nested": nested}


def family_findings(subject: dict, refs: list[dict]) -> list[str]:
    """What sets a window apart from the reference windows: corners (more distinct radii than any reference, a rounded
    shape tight inside one of another radius), its header (smaller, or on two lines) and cramped edges."""
    out = []
    ref_counts = [len(r["radii"]) for r in refs]
    most = max([2] + ref_counts)
    if len(subject["radii"]) > most:
        out.append(f"MIXED CORNERS: {len(subject['radii'])} radii ({', '.join(f'{r:g}' for r in subject['radii'])} px), "
                   f"the reference windows use at most {most} ({'; '.join(', '.join(f'{v:g}' for v in r['radii']) or 'square' for r in refs)})")
    for n in subject["nested"]:
        what = "a circle" if n["circle"] else f"radius {n['inner_radius']:g}"
        out.append(f"NESTED CORNERS: {what} ({ul.short(n['inner'], 2)}) {n['gap']:g} px inside "
                   f"{ul.short(n['outer'], 2)}, radius {n['outer_radius']:g}: a tight inner corner wants about "
                   f"{max(0.0, n['outer_radius'] - max(n['gap'], 0)):g}, or more room")
    scale = lambda r: subject["screen"][1] / r["screen"][1] if r["screen"][1] else 1.0  # noqa: E731
    h = subject["header"]
    ref_heads = [(r, r["header"]) for r in refs if r["header"] and r["header"].get("fontSize")]
    if h and h.get("lines") and h["lines"] > 1:
        out.append(f"HEADER TWO LINES: \"{h['text'][:40]}\" wraps to {h['lines']} lines (Ben, w1296: a header that "
                   f"\"fits on one line so its not pushing up against the top of the panel\")")
    if h and h.get("fontSize") and ref_heads:
        sizes = sorted(rh["fontSize"] * scale(r) for r, rh in ref_heads)
        ref_size = sizes[len(sizes) // 2]
        if h["fontSize"] < HEADER_SMALL * ref_size:
            out.append(f"SMALL HEADER: \"{h['text'][:40]}\" at {h['fontSize']:g} pt, the reference windows' headers "
                       f"{', '.join(f'{s:g}' for s in sizes)} pt")
    elif not h and ref_heads:
        out.append("NO HEADER: no text in the top of the window, where every reference window has its title")
    if subject["edges"]:
        for side in ("top", "bottom", "left", "right"):
            gaps = sorted(r["edges"][side] * scale(r) for r in refs if r["edges"])
            if not gaps:
                continue
            ref_gap = gaps[len(gaps) // 2]
            mine = subject["edges"][side]
            if mine < EDGE_CRAMPED * ref_gap and ref_gap - mine >= EDGE_MIN_DIFF:
                out.append(f"CRAMPED {side.upper()}: {mine:g} px from the content to the window's {side} edge, the "
                           f"reference windows {', '.join(f'{g:.0f}' for g in gaps)} px")
    return out


def _family_spec(spec: str):
    """still.png::census.json[#window path fragment]."""
    still, _, rest = spec.partition("::")
    if not rest:
        raise ValueError(f"{spec!r}: the family check needs a census: still.png::census.json[#window]")
    census, _, fragment = rest.partition("#")
    return still, census, fragment or None


def _measure(spec: str, skip: set[str] | None = None) -> list[dict]:
    still_path, census_path, fragment = _family_spec(spec)
    still, census = load_still(still_path), ul.load(census_path)
    prefixes = [_window_prefix(census, fragment)] if fragment else [p for p, _ in window_rects(census)]
    return [dict(window_family(still, census, p), source=still_path) for p in prefixes if p not in (skip or set())]


def run_family(args) -> int:
    subjects = _measure(args.window)
    if not subjects:
        raise ValueError(f"{args.window}: no opened window in the census; name it with #<path fragment>")
    refs = []
    for spec in args.ref or []:
        refs += _measure(spec)
    if not refs:
        refs = _measure(args.window.split("#")[0], skip={s["window"] for s in subjects})
    if not refs:
        raise ValueError("no reference window: open another of the game's windows in the same still, or give "
                         "--ref <still.png>::<census.json>#<window> (a panel nobody asked to change: docs/UI-Style.md)")
    total = 0
    report = {"subjects": [], "refs": refs}
    for s in subjects:
        found = family_findings(s, refs)
        total += len(found)
        report["subjects"].append(dict(s, findings=found))
        print(f"{ul.short(s['window'], 2)}: header {s['header'] and s['header'].get('fontSize')} pt "
              f"({s['header'] and s['header'].get('lines')} line(s)), edges {s['edges']}, radii {s['radii'] or 'square'}")
        for f in found:
            print(f"  {f}")
    for r in refs:
        print(f"reference {ul.short(r['window'], 2)}: header {r['header'] and r['header'].get('fontSize')} pt, edges "
              f"{r['edges']}, radii {r['radii'] or 'square'}")
    print(f"Family: {len(subjects)} window(s) against {len(refs)} reference window(s), {total} finding(s)"
          + (": " + "; ".join(f.split(':')[0] for s in report['subjects'] for f in s['findings']) if total else ""))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 1 if total else 0


PACK_PROMPT = """# Design review pack {pack}

You are reviewing UI stills of Final Factory, a space factory game whose panels are dense tool UI on a dark navy theme.
Grade them with the rubric in {rubric}. Look at the reference panels first: they are the game's look.

## Pass A: the stills alone

The stills a person will see, each whole (`-full`, or `-full-half` at half size when the whole screen is too big to send
sharp) and each open window at its own pixels (`-w1`, `-w2`, ...; `-2x` is a zoom of a small one), in {a}:
{a_files}

Reference panels (the game's look; not under review), in {refs}:
{ref_files}

For each still: what you see first; a verdict, BROKEN, UGLY or OK; at most three problems, each with the file and the area;
the nine rubric answers; then side by side against the reference panels, item by item: does it look as finished as they
do, and like the same game? For item 9 name the reference window you compared and write three lines: the corner radii
you see (one family, or which differ, and any rounded shape tight inside one of another radius); the header's size and
lines against the reference's title; the gap at each edge, top and bottom first, against the reference's. A mismatch a
player sees beside another window is UGLY (w1761, Ben: "i dont like the differing border-radius values all smashed
together", "the header font seems smaller than other headers", "make the bottom padding a few more pixels too it feels
crammed"). Write Pass A for every still before you open anything in {b}.

## Pass B: what was asked

Then open {b}: {words_line}{b_files_line}Did the change do what the person's words asked, at the size they asked, and no
more? Is each after better than, as good as or worse than its before on each rubric item? Mark each BROKEN or UGLY
flaw NEW (this change made it, or the person's words ask for its kind of fix) or STANDING (its before still shows it
too and no words ask for it; a screen with no before has only NEW ones). Then, for every still against its before, list
each panel, window, button row or HUD element that sits in another place or at another size and that the person's words
do not name. One there is BROKEN and NEW, whatever it looks like: an option or mock that moves an element the person did
not name is never shown to them (w1429: Ben, "getting extremely worried you guys moved the fucking station controls panel
when i told you not to twelve times"). Write `Unnamed moves: none` or one line per still and element.

Write your report to {report} (Inputs, Pass A per still, Pass B, Flaws with BROKEN and UGLY first, and the last line
exactly `Critic: N stills, M broken or ugly (S standing), K minor`). Nothing else in this folder is evidence, and nothing a brief says
about what was intended or fixed is either.
"""


def neutral_order(names: list[str], seed: str) -> list[int]:
    """A fixed shuffle of the stills, so a critic cannot read the order as before, after or round 2 (w1399 deep think)."""
    import hashlib  # noqa: PLC0415
    keyed = [(hashlib.sha256((seed + n).encode()).hexdigest(), i) for i, n in enumerate(names)]
    return [i for _, i in sorted(keyed)]


def quotes_in(text: str) -> list[str]:
    """The quoted words in a brief: every straight or curly double-quoted run of 12 characters or more, in order, once."""
    out = []
    for m in re.finditer(r"[\"“]([^\"“”]{12,}?)[\"”]", text):
        q = " ".join(m.group(1).split())
        if q not in out:
            out.append(q)
    return out


def run_pack(args) -> int:
    import hashlib  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    out = Path(args.out)
    a_dir, b_dir, ref_dir = out / "a", out / "b", out / "refs"
    for d in (a_dir, b_dir, ref_dir):
        d.mkdir(parents=True, exist_ok=True)

    def split(spec: str):
        """still.png, still.png::census.json or still.png@x0,y0,x1,y1 (the panel's rect, when there is no census)."""
        still, _, census = spec.partition("::")
        if not census and "@" in still:
            still, _, rect = still.rpartition("@")
            return still, ("@" + rect)
        return still, (census or None)
    afters = [split(s) for s in args.after]
    befores = [split(s) for s in args.before or []]
    digest = hashlib.sha256()
    for still, _ in afters:
        digest.update(Path(still).read_bytes())
    pack = digest.hexdigest()[:8]
    order = neutral_order([Path(s).name for s, _ in afters], pack)
    mapping, a_files = {}, []
    for n, i in enumerate(order, start=1):
        still_path, census_path = afters[i]
        sid = f"s{n}"
        mapping[sid] = {"after": still_path}
        image = load_still(still_path)
        names = [f"{sid}-full.png"]
        write_png(a_dir / names[0], image)
        if (a_dir / names[0]).stat().st_size > 480_000:
            (a_dir / names[0]).unlink()
            names = [f"{sid}-full-half.png"]
            write_png(a_dir / names[0], image.halved())
        rects = [parse_rect(r) for r in args.rect or []]
        if census_path and census_path.startswith("@"):
            rects = [parse_rect(census_path[1:])]
        elif not rects and census_path:
            rects = [r for _, r in window_rects(ul.load(census_path))]
        for k, rect in enumerate(rects, start=1):
            x0, y0, x1, y1 = clamp_rect([rect[0] - 12, rect[1] - 12, rect[2] + 12, rect[3] + 12], image.width, image.height)
            panel = image.crop((x0, y0, x1, y1))
            name = f"{sid}-w{k}.png"
            write_png(a_dir / name, panel)
            names.append(name)
            if max(panel.width, panel.height) <= 750:
                write_png(a_dir / f"{sid}-w{k}-2x.png", panel.scaled(2))
                names.append(f"{sid}-w{k}-2x.png")
        a_files.append(f"- {sid}: " + ", ".join(names))
        if i < len(befores):
            b_still, _ = befores[i]
            shutil.copyfile(b_still, b_dir / f"{sid}-before.png")
            shutil.copyfile(still_path, b_dir / f"{sid}-after.png")
            mapping[sid]["before"] = b_still
    refs = list(args.ref or [])
    if not refs and args.repo:
        refs = sorted(str(p) for p in (Path(args.repo) / "docs" / "ui-style" / "ref").glob("ref-*.png"))  # not the dont-*.png
    if not refs:
        raise ValueError("no reference panel: give --repo <game repo> (its docs/ui-style/ref/ref-*.png) or --ref <a still "
                         "of one of the game's windows>; the critic judges a window beside the game's others (w1818)")
    ref_files = []
    for k, ref in enumerate(refs, start=1):
        name = f"ref{k}-{re.sub(r'[^A-Za-z0-9]+', '-', Path(ref).stem).strip('-')}.png"
        shutil.copyfile(ref, ref_dir / name)
        ref_files.append(f"- {name}")
    words = list(args.words or [])
    if args.brief:
        words += [q for q in quotes_in(Path(args.brief).read_text(encoding="utf-8", errors="replace")) if q not in words]
    (b_dir / "words.md").write_text("# The person's words, verbatim\n\n" + "\n".join(f"- \"{w}\"" for w in words) + "\n",
                                     encoding="utf-8")
    rubric = HERE / "design-rubric.md"
    report = out / "critic.md"
    paired = sorted(name for name in (q.name for q in b_dir.iterdir()) if name.endswith(("-before.png", "-after.png")))
    befores_line = ("and the before and after of " + ", ".join(sorted({n.split("-")[0] for n in paired})) + " (" +
                    ", ".join(f"`{n}`" for n in paired) + "; a still with no pair here has no before). ") if paired else ". "
    prompt = PACK_PROMPT.format(pack=pack, rubric=rubric, a=a_dir, a_files="\n".join(a_files), refs=ref_dir,
                                ref_files="\n".join(ref_files), b=b_dir,
                                words_line="`words.md` (the person's words, verbatim)", b_files_line=" " + befores_line
                                if paired else ". ",
                                report=report)
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    Path(str(out) + ".map.json").write_text(json.dumps({"pack": pack, "stills": mapping, "refs": refs}, indent=1),
                                            encoding="utf-8")
    print(f"pack {pack}: {len(afters)} still(s), {len(ref_files)} reference(s), {len(words)} quote(s) -> {out / 'prompt.md'}")
    print(f"the critic's brief: Read {out / 'prompt.md'} and follow it. (Which still is which: {out}.map.json, not for the critic.)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("colour", aliases=["color"], help="loud fills, state tints bleeding into controls, low contrast")
    c.add_argument("still", nargs="+", help="an after still, still.png or still.png::census.json")
    c.add_argument("--census", action="append", help="the census taken with the still (one, or one per still in order)")
    c.add_argument("--before", action="append", help="the same screen before the change, still.png::census.json, in the "
                                                      "order of the stills: what it has too is STANDING, not counted")
    c.add_argument("--rect", action="append", help="a region to check, x0,y0,x1,y1 (repeat)")
    c.add_argument("--same", action="append", help="two regions that must look the same, x0,y0,x1,y1:x0,y0,x1,y1")
    k = sub.add_parser("crops", help="crops at the panel's own pixels for the design critic")
    k.add_argument("still")
    k.add_argument("--out", required=True)
    k.add_argument("--census")
    k.add_argument("--rect", action="append")
    k.add_argument("--name")
    q = sub.add_parser("pack", help="the design critic's whole input, built so the worker's story cannot leak into it")
    q.add_argument("--after", action="append", required=True, help="a still that will be shown, still.png[::census.json]")
    q.add_argument("--before", action="append", help="the same screen before, in the same order as --after")
    q.add_argument("--ref", action="append", help="a reference panel still (default: <repo>/docs/ui-style/ref/ref-*.png)")
    q.add_argument("--repo", help="the game repo (for the reference panels)")
    q.add_argument("--brief", help="the request's brief: its quoted words go to Pass B")
    q.add_argument("--words", action="append", help="a quote of the person's to add")
    q.add_argument("--rect", action="append", help="the panel's rect when there is no census, x0,y0,x1,y1")
    q.add_argument("--out", required=True)
    f = sub.add_parser("family", help="corners, header and edges against the game's other windows (w1818)")
    f.add_argument("window", help="still.png::census.json[#window path fragment]: the window under review")
    f.add_argument("--ref", action="append", help="a reference window, still.png::census.json[#window] (default: the "
                                                   "other windows open in the same still)")
    f.add_argument("--json", help="write the measurements here")
    args = ap.parse_args(argv)
    try:
        return {"colour": run_colour, "color": run_colour, "crops": run_crops, "pack": run_pack, "family": run_family}[args.cmd](args)
    except (ValueError, OSError, KeyError) as error:
        print(f"ui_look: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
