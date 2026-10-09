#!/usr/bin/env python3
"""ui_layout: does a UI change leave the rest of the screen as it was? (w733)

Compares two layout censuses (layout-census.md: every visible UI element with its screen rect, colour,
alpha, sprite and drawing order) taken before and after a change, same save, size and open screens:

    ui_layout.py check --before before.json --after after.json [--clusters hud-clusters.json]
                       [--ref InventoryPanel] [--shot after.png --ref-shot before.png] [--block-depth 2]

  Overlaps   HUD blocks (an element's ancestor --block-depth levels under its canvas, 2: GamePanels/X) whose visible
             parts overlap. A pair in `after` that is not in `before` is a new overlap: FAIL.
  Alignment  every cluster (an anchor and its members, by object name) measured edge by edge against
             its anchor; a change over --tolerance px (2) between before and after: FAIL.
  Style      every panel (an Image over 2 % of the screen) that is new or changed colour, alpha or
             sprite, and every panel under a --touched fragment, against the reference panel (--ref, a
             path fragment, from --ref-census or the before census): a delta E over 10 (sampled from
             --shot/--ref-shot inside each panel's rect when given, which is what a player sees), an
             alpha off by more than 0.2 on the same art, or different art without screenshots: FAIL.

It prints the `Overlaps:`, `Alignment:` and `Style:` lines the pull request carries (pr_evidence.py
reads them) and exits 1 when any check fails, 2 on bad input.

    ui_layout.py overlaps <census.json>        the overlapping block pairs of one census
    ui_layout.py clusters <census.json|tour.log> [--clusters ...]   cluster edges of one census or a
                                               Deck-tour log's `rect:` lines (built players)

Standard library only; Pillow for --shot sampling.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CLUSTERS = HERE / "hud-clusters.json"
TOUR_RECT = re.compile(r"->\s+(?P<path>.+?)\s+active\s+(?P<active>\w+)\s+screen x\s+(?P<x0>-?[\d.]+)\.\.(?P<x1>-?[\d.]+)\s+"
                       r"y\s+(?P<y0>-?[\d.]+)\.\.(?P<y1>-?[\d.]+)\s+of\s+(?P<w>\d+)x(?P<h>\d+)")


# ---------------------------------------------------------------------------------------------------------------
# loading


def load(path: str | Path) -> dict:
    """A census JSON, or a Deck-tour log whose `rect:` lines become elements (cluster checks only)."""
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    if text.lstrip().startswith("{"):
        data = json.loads(text)
        data.setdefault("elements", [])
        return data
    elements, screen = [], None
    for m in TOUR_RECT.finditer(text):
        w, h = int(m["w"]), int(m["h"])
        screen = [w, h]
        if m["active"].lower() != "true":
            continue
        x0, x1, y0, y1 = (float(m[k]) for k in ("x0", "x1", "y0", "y1"))
        rect = [x0, h - y1, x1, h - y0]
        elements.append({"path": m["path"].strip(), "kind": "Rect", "rect": rect, "visible": rect, "alpha": 1.0})
    if not elements:
        raise ValueError(f"{p}: neither a census JSON nor a tour log with rect: lines")
    return {"screen": screen, "elements": elements, "source": "tour log"}


def area(r) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def inter(a, b):
    return [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]


def union(rects):
    return [min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects)]


# ---------------------------------------------------------------------------------------------------------------
# overlaps


def canvas_index(parts: list[str]) -> int:
    """Where the canvas sits in a path: the first component that names one, else the root."""
    for i, part in enumerate(parts):
        if "canvas" in part.lower():
            return i
    return 0


def block_of(path: str, depth: int) -> str:
    parts = path.split("/")
    start = canvas_index(parts)
    return "/".join(parts[:min(len(parts), start + 1 + depth)])


IGNORE = ("[Graphy]", "DebugInfo", "AgentControlIndicator")  # development overlays, not in a release build


def solid(e) -> bool:
    """An element a player sees as a thing: a control, a text, or a graphic that is not nearly transparent. A mask
    that does not draw its own graphic (a scroll view's viewport) is not one, nor a development overlay."""
    if e.get("maskOnly") or any(i in e["path"] for i in IGNORE):
        return False
    return e.get("selectable") or "Text" in e.get("kind", "") or e.get("alpha", 1.0) >= 0.25


def overlaps(census: dict, depth: int = 2, min_px: float = 16.0) -> dict:
    """{(blockA, blockB): {"px": area, "example": (pathA, pathB)}} for blocks whose solid elements overlap."""
    items = [(e, block_of(e["path"], depth)) for e in census["elements"] if solid(e) and area(e.get("visible") or e["rect"]) >= 4]
    pairs: dict[tuple[str, str], dict] = {}
    for i in range(len(items)):
        a, ba = items[i]
        ra = a.get("visible") or a["rect"]
        for j in range(i + 1, len(items)):
            b, bb = items[j]
            if ba == bb or ba.startswith(bb + "/") or bb.startswith(ba + "/"):
                continue
            rb = b.get("visible") or b["rect"]
            if rb[0] >= ra[2] or rb[2] <= ra[0] or rb[1] >= ra[3] or rb[3] <= ra[1]:
                continue
            px = area(inter(ra, rb))
            if px < max(min_px, 0.05 * min(area(ra), area(rb))):
                continue
            key = tuple(sorted((ba, bb)))
            entry = pairs.setdefault(key, {"px": 0.0, "example": (a["path"], b["path"])})
            entry["px"] += px
    return pairs


def short(path: str, keep: int = 3) -> str:
    parts = path.split("/")
    return "/".join(parts[-keep:]) if len(parts) > keep else path


# ---------------------------------------------------------------------------------------------------------------
# clusters


def find(census: dict, name: str):
    """The union of the visible rects of everything at or under the object named `name` (a name or a path tail)."""
    name = name.strip("/")
    hits = [e.get("visible") or e["rect"] for e in census["elements"]
            if e["path"] == name or e["path"].endswith("/" + name) or ("/" + name + "/") in ("/" + e["path"] + "/")]
    hits = [r for r in hits if area(r) > 0]
    return union(hits) if hits else None


def cluster_edges(census: dict, spec: dict) -> dict:
    """{cluster: {"anchor": rect, "members": {name: {"left","right","top","bottom","gapLeft","gapAbove"}}}}."""
    out = {}
    for cluster in spec.get("clusters", []):
        anchor = find(census, cluster["anchor"])
        members = {}
        for name in cluster["members"]:
            r = find(census, name)
            if r is None or anchor is None:
                members[name] = None
                continue
            members[name] = {
                "left": r[0] - anchor[0], "right": r[2] - anchor[2], "top": r[1] - anchor[1], "bottom": r[3] - anchor[3],
                "gapLeft": anchor[0] - r[2], "gapAbove": anchor[1] - r[3],
            }
        out[cluster["name"]] = {"anchor": anchor, "members": members,
                                "edges": cluster.get("edges", ["left", "right", "top", "bottom"])}
    return out


def drift(before: dict, after: dict, tolerance: float) -> tuple[float, list[str]]:
    """The largest edge change between two cluster_edges results, and one line per change over tolerance."""
    worst, lines = 0.0, []
    for name, b in before.items():
        a = after.get(name)
        if a is None:
            continue
        if b["anchor"] and a["anchor"]:
            for i, edge in enumerate(("left", "top", "right", "bottom")):
                d = a["anchor"][i] - b["anchor"][i]
                worst = max(worst, abs(d))
                if abs(d) > tolerance:
                    lines.append(f"{name}: the anchor's {edge} edge moved {d:+.0f} px on screen")
        for member, mb in b["members"].items():
            ma = a["members"].get(member)
            if (mb is None) != (ma is None):
                lines.append(f"{name}: {member} {'appeared' if mb is None else 'is gone'}")
                continue
            if mb is None:
                continue
            for edge in b.get("edges", ("left", "right", "top", "bottom")):
                d = ma[edge] - mb[edge]
                worst = max(worst, abs(d))
                if abs(d) > tolerance:
                    lines.append(f"{name}: {member}'s {edge} edge moved {d:+.0f} px against the anchor "
                                 f"(gap left of the anchor {mb['gapLeft']:.0f} -> {ma['gapLeft']:.0f} px)")
    return worst, lines


# ---------------------------------------------------------------------------------------------------------------
# style


def rgba(hex_colour: str):
    h = hex_colour.lstrip("#")
    h = (h + "FF")[:8] if len(h) == 6 else h
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4, 6))


def lab(rgb):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(float(v)) for v in rgb[:3])
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def delta_e(a, b) -> float:
    return math.dist(lab(a), lab(b))


def panels(census: dict, min_share: float = 0.02) -> dict:
    w, h = census.get("screen") or [1, 1]
    out = {}
    for e in census["elements"]:
        if e.get("kind") not in ("Image", "RawImage") or e.get("alpha", 0) < 0.1 or e.get("maskOnly")                 or any(i in e["path"] for i in IGNORE):
            continue
        if area(e.get("visible") or e["rect"]) < min_share * w * h:
            continue
        out[e["path"]] = e
    return out


def changed_panels(before: dict | None, after: dict, touched: list[str] | None = None) -> list[dict]:
    """Panels that are new or changed colour, alpha or art since `before`, plus every panel whose path contains one
    of the `touched` fragments (the windows the change is about), changed or not."""
    pa = panels(after)
    forced = [dict(e, why="touched") for p, e in pa.items() if any(t.lower() in p.lower() for t in touched or [])]
    if before is None:
        return forced
    pb = panels(before)
    result = []
    for path, e in pa.items():
        old = pb.get(path)
        if old is None:
            result.append(dict(e, why="new"))
            continue
        if old.get("sprite") != e.get("sprite") or abs(old.get("alpha", 1) - e.get("alpha", 1)) > 0.05 or \
                delta_e(rgba(old["color"]), rgba(e["color"])) > 2:
            result.append(dict(e, why=f"was {old['color']} alpha {old.get('alpha', 1):.2f} sprite '{old.get('sprite', '')}'"))
    seen = {e["path"] for e in result}
    return result + [e for e in forced if e["path"] not in seen]


def reference(census: dict, fragment: str):
    """The largest panel whose path contains the fragment."""
    cands = [e for e in panels(census, 0.005).values() if fragment.lower() in e["path"].lower()]
    return max(cands, key=lambda e: area(e.get("visible") or e["rect"])) if cands else None


def sample(shot, rect):
    """The median colour of a screenshot inside a rect (image pixels, top-left origin)."""
    from PIL import Image  # noqa: PLC0415
    with Image.open(shot) as image:
        x0, y0, x1, y1 = (int(round(v)) for v in rect)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(image.width, x1), min(image.height, y1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            return None
        crop = image.convert("RGB").crop((x0, y0, x1, y1)).resize((max(1, (x1 - x0) // 4), max(1, (y1 - y0) // 4)))
        pixels = sorted(crop.getdata(), key=lambda p: sum(p))
        return pixels[len(pixels) // 2]


def style(before: dict | None, after: dict, ref_fragment: str, shot=None, ref_shot=None, ref_census: dict | None = None,
          touched_fragments: list[str] | None = None, max_delta: float = 10.0,
          max_alpha: float = 0.2) -> tuple[list[str], list[str]]:
    """(one summary per checked panel, failures). The reference panel comes from ref_census (a census with the
    classic panel open), else before, else after."""
    ref = None
    for census in (ref_census, before, after):
        if census is not None and ref is None:
            ref = reference(census, ref_fragment)
    touched = changed_panels(before, after, touched_fragments)
    summaries, failures = [], []
    if not touched:
        return ["no panel changed colour, alpha or art" + (" and no --touched panel is open" if touched_fragments else "")], []
    if ref is None:
        return [], [f"no reference panel matching '{ref_fragment}' in the census: open the classic panel too, or pass --ref"]
    for e in touched:
        if e["path"] == ref["path"]:
            continue
        name = short(e["path"])
        da = e.get("alpha", 1) - ref.get("alpha", 1)
        if shot and ref_shot:
            mine, theirs = sample(shot, e.get("visible") or e["rect"]), sample(ref_shot, ref.get("visible") or ref["rect"])
            de = delta_e(mine, theirs) if mine and theirs else float("nan")
            how = "on screen"
        else:
            de = delta_e(rgba(e["color"]), rgba(ref["color"]))
            how = "tint"
        art = "same art" if (e.get("sprite") or "") == (ref.get("sprite") or "") else \
            f"art '{e.get('sprite') or 'flat fill'}' vs '{ref.get('sprite') or 'flat fill'}'"
        summaries.append(f"{name} ({e['why']}) vs {short(ref['path'])}: delta E {de:.1f} ({how}), alpha "
                         f"{e.get('alpha', 1):.2f} vs {ref.get('alpha', 1):.2f}, {art}")
        if de > max_delta:
            failures.append(f"{name}: delta E {de:.1f} against the reference panel (> {max_delta:.0f})")
        if art == "same art" and abs(da) > max_alpha:
            failures.append(f"{name}: alpha {e.get('alpha', 1):.2f} against the reference's {ref.get('alpha', 1):.2f} "
                            f"({'more opaque' if da > 0 else 'more see-through'} than the game's panels)")
        if art != "same art" and not (shot and ref_shot):
            failures.append(f"{name}: {art}: compare the screenshots (--shot/--ref-shot) or reuse the reference's sprite")
    return summaries, failures


# ---------------------------------------------------------------------------------------------------------------
# commands


def run_check(args) -> int:
    before, after = load(args.before), load(args.after)
    spec = json.loads(Path(args.clusters).read_text(encoding="utf-8"))
    failed = False

    ob, oa = overlaps(before, args.block_depth), overlaps(after, args.block_depth)
    new = {k: v for k, v in oa.items() if k not in ob}
    print(f"Overlaps: {len(ob)} block pairs before, {len(oa)} after, {len(new)} new (ui_layout.py, whole screen, "
          f"block depth {args.block_depth})")
    for (a, b), v in sorted(new.items(), key=lambda kv: -kv[1]["px"])[:15]:
        print(f"  NEW: {short(a)}  x  {short(b)}: {v['px']:.0f} px2, e.g. {short(v['example'][0], 2)} under {short(v['example'][1], 2)}")
    failed |= bool(new)

    worst, lines = drift(cluster_edges(before, spec), cluster_edges(after, spec), args.tolerance)
    names = ", ".join(c["name"] for c in spec.get("clusters", []))
    print(f"Alignment: max drift {worst:.0f} px over the clusters ({names}); tolerance {args.tolerance:.0f} px")
    for line in lines[:20]:
        print(f"  DRIFT: {line}")
    failed |= bool(lines)

    ref_census = load(args.ref_census) if args.ref_census else None
    summaries, failures = style(before, after, args.ref, args.shot, args.ref_shot, ref_census, args.touched)
    print("Style: " + ("; ".join(summaries) if summaries else "nothing checked"))
    for f in failures:
        print(f"  STYLE: {f}")
    failed |= bool(failures)
    return 1 if failed else 0


def run_overlaps(args) -> int:
    pairs = overlaps(load(args.census), args.block_depth)
    print(f"{len(pairs)} overlapping block pairs (block depth {args.block_depth})")
    for (a, b), v in sorted(pairs.items(), key=lambda kv: -kv[1]["px"]):
        print(f"  {short(a)}  x  {short(b)}: {v['px']:.0f} px2, e.g. {short(v['example'][0], 2)} / {short(v['example'][1], 2)}")
    return 0


def run_clusters(args) -> int:
    census = load(args.census)
    spec = json.loads(Path(args.clusters).read_text(encoding="utf-8"))
    for name, c in cluster_edges(census, spec).items():
        print(f"{name}: anchor {c['anchor']}")
        for member, m in c["members"].items():
            print(f"  {member}: " + ("not on screen" if m is None else
                                    ", ".join(f"{k} {v:+.0f}" for k, v in m.items())))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="before against after: overlaps, alignment, style")
    c.add_argument("--before", required=True)
    c.add_argument("--after", required=True)
    c.add_argument("--clusters", default=str(DEFAULT_CLUSTERS))
    c.add_argument("--ref", default="InventoryPanel", help="path fragment of the classic reference panel")
    c.add_argument("--shot", help="a screenshot taken with the after census")
    c.add_argument("--ref-shot", help="a screenshot with the reference panel (usually the before one)")
    c.add_argument("--ref-census", help="a census with the reference panel open (default: the before census)")
    c.add_argument("--touched", action="append", default=[],
                   help="a path fragment of a window the change is about: always style-checked (repeatable)")
    c.add_argument("--tolerance", type=float, default=2.0)
    o = sub.add_parser("overlaps", help="the overlapping block pairs of one census")
    o.add_argument("census")
    k = sub.add_parser("clusters", help="cluster edges of one census or tour log")
    k.add_argument("census")
    k.add_argument("--clusters", default=str(DEFAULT_CLUSTERS))
    for p in (c, o):
        p.add_argument("--block-depth", type=int, default=2)
    args = ap.parse_args(argv)
    try:
        return {"check": run_check, "overlaps": run_overlaps, "clusters": run_clusters}[args.cmd](args)
    except (ValueError, OSError, KeyError) as error:
        print(f"ui_layout: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
