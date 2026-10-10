#!/usr/bin/env python3
"""ui_layout: does a UI change leave the rest of the screen as it was? (w733)

Compares two layout censuses (layout-census.md: every visible UI element with its screen rect, colour,
alpha, sprite and drawing order) taken before and after a change, same save, size and open screens:

    ui_layout.py check --before before.json --after after.json [--closed closed.json] [--clusters hud-clusters.json]
                       [--ref InventoryPanel] [--shot after.png --ref-shot before.png] [--block-depth 2]

  Overlaps   always-on HUD blocks (an element's ancestor --block-depth levels under its canvas, 2: GamePanels/X)
             whose visible parts overlap. A pair in `after` that is not in `before` is a new overlap: FAIL. A pair that
             was there before and is still there, between blocks the change moved, is kept: FAIL too. Elements of a
             panel the player opens on purpose and can close (hud-clusters.json `openedPanels`: Blueprints, Inventory,
             the slide-outs, the Station panel, the hub) are not HUD: they may cover it (w742, Ben).
  Opened     what an opened panel over the HUD must still do: draw on top of what it covers, take the clicks over
  panels     every raycast target it covers, stay inside the screen, and (with --closed, a census taken after closing
             it) leave the covered HUD exactly where it was. Any failure: FAIL.
  Alignment  every cluster (an anchor and its members, by object name) measured edge by edge against
             its anchor; a change over --tolerance px (2) between before and after: FAIL.
  Style      every panel (an Image over 2 % of the screen) that is new or changed colour, alpha or
             sprite, and every panel under a --touched fragment, against the reference panel (--ref, a
             path fragment, from --ref-census or the before census): a delta E over 10 (sampled from
             --shot/--ref-shot inside each panel's rect when given, which is what a player sees), an
             alpha off by more than 0.2 on the same art, or different art without screenshots: FAIL.

  Moved      every element that moved or resized more than --move-px px (4), grouped into the largest object that
             moved as one, and every object that is gone (w826: #1282 moved the Station Info box to the top left and
             w722/#1282 put the objectives card under the Station strip; Ben: "i didnt tell you to move that"). Listed,
             not judged: the pull request marks each one asked (quoting the requester) or not asked, and pr_evidence.py
             fails it while one is unmarked.

  Pinned     every place Ben fixed himself (hud-pins.json: Station Info over the abilities, the building hover card over
             the minimap, the Player Inventory off the left edge), checked in the after census whatever the before one
             showed, so an earlier PR's move never becomes the new normal (w894). A broken pin: FAIL.

It prints the `Overlaps:`, `Opened panels:`, `Alignment:`, `Style:`, `Pinned:` and `Moved:` lines the pull request
carries (pr_evidence.py reads them) and exits 1 when any of the first five fails, 2 on bad input.

    ui_layout.py pins <census.json> [<census.json> ...]   the `Pinned:` line over every census (w894): take them at
                                               1920x1080, 1280x800 undocked and 1280x800 docked, a station selected

    ui_layout.py moves --pair before-1920.json after-1920.json --pair before-1280.json after-1280.json [--move-px 4]
                                               the `Moved:` line and its list over both standard sizes (w826)

    ui_layout.py overlaps <census.json>        the overlapping block pairs of one census
    ui_layout.py clusters <census.json|tour.log> [--clusters ...]   cluster edges of one census or a
                                               Deck-tour log's `rect:` lines (built players)

Standard library only; Pillow for --shot sampling.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CLUSTERS = HERE / "hud-clusters.json"
DEFAULT_PINS = HERE / "hud-pins.json"
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


def strip_clone(name: str) -> str:
    return re.sub(r"\s*\(Clone\)$", "", name)


def opened_prefix(path: str, patterns: list[str]) -> str | None:
    """The part of `path` up to the end of the first match of an `openedPanels` pattern, or None when the element is
    always-on HUD. A pattern is path components (fnmatch globs); it matches a run of components anywhere in the path,
    so "InventoryPanel" does not match "TopInfoPanel/..." and "*EntityPanel" matches every structure panel."""
    parts = [strip_clone(p) for p in path.split("/")]
    best = None
    for pattern in patterns:
        want = pattern.strip("/").split("/")
        for i in range(len(parts) - len(want) + 1):
            if all(fnmatch.fnmatchcase(parts[i + j], want[j]) for j in range(len(want))):
                end = i + len(want)
                best = end if best is None else min(best, end)
                break
    return None if best is None else "/".join(path.split("/")[:best])


def opened_patterns(spec: dict | None) -> list[str]:
    return list(((spec or {}).get("openedPanels") or {}).get("paths", []))


def _pairs(census: dict, depth: int, min_px: float, same_block: bool):
    """Every two solid elements whose visible rects overlap enough to count: (a, block a, b, block b, px2, rect)."""
    items = [(e, block_of(e["path"], depth)) for e in census["elements"] if solid(e) and area(e.get("visible") or e["rect"]) >= 4]
    for i in range(len(items)):
        a, ba = items[i]
        ra = a.get("visible") or a["rect"]
        for j in range(i + 1, len(items)):
            b, bb = items[j]
            if not same_block and (ba == bb or ba.startswith(bb + "/") or bb.startswith(ba + "/")):
                continue
            rb = b.get("visible") or b["rect"]
            if rb[0] >= ra[2] or rb[2] <= ra[0] or rb[1] >= ra[3] or rb[3] <= ra[1]:
                continue
            both = inter(ra, rb)
            px = area(both)
            if px < max(min_px, 0.05 * min(area(ra), area(rb))):
                continue
            yield a, ba, b, bb, px, both


def overlaps(census: dict, depth: int = 2, min_px: float = 16.0, opened: list[str] | None = None) -> dict:
    """{(blockA, blockB): {"px": area, "example": (pathA, pathB)}} for always-on HUD blocks whose solid elements overlap.
    With `opened` (the openedPanels patterns) an element of a panel the player opens does not count: it may cover the
    HUD (see opened_over_hud, which checks that it does so properly)."""
    pairs: dict[tuple[str, str], dict] = {}
    for a, ba, b, bb, px, _ in _pairs(census, depth, min_px, same_block=False):
        if opened and (opened_prefix(a["path"], opened) or opened_prefix(b["path"], opened)):
            continue
        key = tuple(sorted((ba, bb)))
        entry = pairs.setdefault(key, {"px": 0.0, "example": (a["path"], b["path"])})
        entry["px"] += px
    return pairs


def short(path: str, keep: int = 3) -> str:
    parts = path.split("/")
    return "/".join(parts[-keep:]) if len(parts) > keep else path


def above(a: dict, b: dict) -> bool | None:
    """Whether a is drawn over b (canvas sorting order, then the canvas renderer's absolute depth), None when the
    census did not record the order (a tour log)."""
    if "depth" not in a or "depth" not in b:
        return None
    return (a.get("canvasOrder", 0), a["depth"]) > (b.get("canvasOrder", 0), b["depth"])


def opened_over_hud(census: dict, patterns: list[str], depth: int = 2, min_px: float = 16.0) -> dict:
    """What a panel the player opened does to the HUD it covers (w742, Ben: "Put the slide out back just make it appear
    over the hot bar. The user can then close it to show the hotbar again" and "the blueprint panel showing over
    objectives is fine since its a temporarily opened panel"). Covering the HUD is allowed; the panel must

      under      draw on top of every HUD element it covers (a panel UNDER the HUD shows the HUD through it),
      blocked    take the clicks over every raycast target it covers (a raycasting element of the panel above it),
      cut        stand inside the screen (an element past the edge that no mask clips).

    Returns {"pairs": {(panel, hud block): {...}}, "under": [...], "blocked": [...], "cut": [...], "covered": {path: rect},
    "measured": bool} with one line per problem."""
    out = {"pairs": {}, "under": [], "blocked": [], "cut": [], "covered": {}, "measured": True}
    if not patterns:
        return out
    solids = [e for e in census["elements"] if solid(e) and area(e.get("visible") or e["rect"]) >= 4]
    panel = [(e, opened_prefix(e["path"], patterns)) for e in solids]
    panel = [(e, p) for e, p in panel if p]
    panel_paths = {e["path"] for e, _ in panel}
    for a, ba, b, bb, px, region in _pairs(census, depth, min_px, same_block=True):
        if (a["path"] in panel_paths) == (b["path"] in panel_paths):
            continue
        if a["path"] not in panel_paths:
            a, b = b, a
        label = opened_prefix(a["path"], patterns)
        hud_block = block_of(b["path"], depth)
        entry = out["pairs"].setdefault((label, hud_block), {"px": 0.0, "example": (a["path"], b["path"])})
        entry["px"] += px
        out["covered"][b["path"]] = b.get("visible") or b["rect"]
        order = above(a, b)
        if order is None:
            out["measured"] = False
            continue
        if not order:
            out["under"].append(f"{short(label, 2)} under {short(hud_block, 1)}: {short(a['path'], 2)} is drawn below "
                                f"{short(b['path'], 2)} (canvas {a.get('canvasOrder', 0)}/{b.get('canvasOrder', 0)}, depth "
                                f"{a['depth']}/{b['depth']})")
            continue
        if b.get("raycast"):
            catchers = [c for c, _ in panel if c.get("raycast") and above(c, b)
                        and area(inter(c.get("visible") or c["rect"], region)) >= 0.9 * area(region)]
            if not catchers:
                out["blocked"].append(f"{short(hud_block, 1)}: {short(b['path'], 2)} takes clicks under {short(label, 2)}: "
                                      f"no raycast target of the panel covers it")
    w, h = census.get("screen") or [0, 0]
    if w and h:
        for e, label in panel:
            r, v = e["rect"], e.get("visible") or e["rect"]
            over = max(-r[0], -r[1], r[2] - w, r[3] - h)
            clipped = [max(r[0], 0), max(r[1], 0), min(r[2], w), min(r[3], h)]
            if over > 2 and max(abs(x - y) for x, y in zip(clipped, v)) <= 1:
                out["cut"].append(f"{short(label, 2)}: {short(e['path'], 2)} reaches {over:.0f} px past the screen edge "
                                  f"(rect {[round(x) for x in r]} on {w}x{h})")
    out["under"] = sorted(set(out["under"]))
    out["blocked"] = sorted(set(out["blocked"]))
    out["cut"] = sorted(set(out["cut"]))
    return out


def restored(closed: dict, covered: dict, tolerance: float = 2.0) -> list[str]:
    """The HUD elements an opened panel covered, in the census taken after closing it: each must be there, drawn, at
    the same place (the HUD is back as it was)."""
    now = {e["path"]: e.get("visible") or e["rect"] for e in closed["elements"] if solid(e)}
    problems = []
    for path, rect in sorted(covered.items()):
        r = now.get(path)
        if r is None:
            problems.append(f"{short(path, 2)} is gone from the screen after closing the panel")
        elif max(abs(x - y) for x, y in zip(r, rect)) > tolerance:
            problems.append(f"{short(path, 2)} is not where it was after closing the panel")
    return problems


def moved_blocks(before: dict, after: dict, depth: int = 2, tolerance: float = 2.0) -> set[str]:
    """Blocks with an element (matched by path, present on both sides) whose visible rect moved more than tolerance.
    An overlap the change leaves between blocks it moved is the change's to fix, even if it was there before
    (w733: 7f75224fa moved the slide-out toggles and the hotbar apart and left the Blueprint slide-out over the
    hotbar, 14689 -> 3948 px2)."""
    old = {e["path"]: e.get("visible") or e["rect"] for e in before["elements"]}
    moved = set()
    for e in after["elements"]:
        r = old.get(e["path"])
        if r is None or any(i in e["path"] for i in IGNORE):
            continue
        now = e.get("visible") or e["rect"]
        if max(abs(a - b) for a, b in zip(r, now)) > tolerance:
            moved.add(block_of(e["path"], depth))
    return moved


# ---------------------------------------------------------------------------------------------------------------
# moves (w826)


def under_canvas(path: str) -> str:
    """The path from the canvas's first child on: what a person reads as the element's name."""
    parts = path.split("/")
    return "/".join(parts[canvas_index(parts) + 1:]) or path


def keyed(census: dict) -> dict:
    """{(path, n): rect} for every element but the development overlays. Elements that share a path (unnamed siblings)
    are told apart by their place in reading order, top to bottom and left to right, on each side."""
    by_path: dict[str, list] = {}
    for e in census["elements"]:
        if any(i in e["path"] for i in IGNORE):
            continue
        by_path.setdefault(e["path"], []).append(e["rect"])
    out = {}
    for path, rects in by_path.items():
        for i, r in enumerate(sorted(rects, key=lambda r: (round(r[1]), round(r[0])))):
            out[(path, i)] = r
    return out


def moves(before: dict, after: dict, move_px: float = 4.0) -> dict:
    """What moved between two censuses of the same save, size and open screens (w826).

    Every element whose rect (the RectTransform's, not the clipped part) changed more than move_px on any edge is
    grouped into the highest object in its path whose every element changed by the same amount (within move_px): the
    Station Info box moving as a whole is one part, not its forty texts; an element that changed by a different amount
    from its siblings is its own part (a box that grew). Parts are reported per HUD block (block depth 2: GamePanels/X,
    what a person calls an element), with the block's outer rect. Returns {"moved": [{"path", "delta", "before",
    "after", "elements", "parts"}], "gone": [path], "new": [path], "screen": "WxH"}; "gone" and "new" are blocks with
    no element on the other side."""
    old, now = keyed(before), keyed(after)
    common = [k for k in now if k in old]
    delta = {k: [now[k][i] - old[k][i] for i in range(4)] for k in common}
    moved = [k for k in common if max(abs(d) for d in delta[k]) > move_px]

    def under(prefix: str):
        return [k for k in common if k[0] == prefix or k[0].startswith(prefix + "/")]

    def same(a, b):
        return max(abs(x - y) for x, y in zip(a, b)) <= move_px

    units: dict[str, dict] = {}
    for k in moved:
        if any((k[0] == p or k[0].startswith(p + "/")) and same(u["delta"], delta[k]) for p, u in units.items()):
            continue
        parts = k[0].split("/")
        start = canvas_index(parts) + 1
        unit = k[0]
        for end in range(min(start + 2, len(parts)), len(parts) + 1):  # never above a block (GamePanels/X)
            prefix = "/".join(parts[:end])
            if all(same(delta[j], delta[k]) for j in under(prefix)):
                unit = prefix
                break
        keys = under(unit)
        units[unit] = {"path": unit, "delta": delta[k], "elements": len(keys),
                       "before": union([old[j] for j in keys]), "after": union([now[j] for j in keys])}
    # One line per HUD block (GamePanels/X: the Station Info box, the Station strip, the hover card), which is what a
    # person calls an element: its outer rect before and after, and the parts that moved inside it.
    blocks: dict[str, dict] = {}
    for unit in units.values():
        block = block_of(unit["path"], 2)
        if block not in blocks:
            keys = under(block)
            b, a = union([old[j] for j in keys]), union([now[j] for j in keys])
            blocks[block] = {"path": block, "delta": [a[i] - b[i] for i in range(4)], "before": b, "after": a,
                             "elements": len(keys), "parts": []}
        blocks[block]["parts"].append(unit)
    for block in blocks.values():
        block["parts"].sort(key=lambda u: -max(abs(d) for d in u["delta"]))
    blocks_old = {block_of(k[0], 2) for k in old}
    blocks_new = {block_of(k[0], 2) for k in now}
    w, h = after.get("screen") or before.get("screen") or [0, 0]
    biggest = lambda b: -max(max(abs(d) for d in b["delta"]), max(abs(d) for d in b["parts"][0]["delta"]))
    layout = layout_of(after)
    if layout_of(before) != layout:
        raise ValueError(f"the before census is {layout_of(before)} and the after one {layout}: compare the same layout")
    return {"moved": sorted(blocks.values(), key=biggest),
            "gone": sorted(blocks_old - blocks_new), "new": sorted(blocks_new - blocks_old),
            "screen": f"{int(w)}x{int(h)} {layout}"}


def layout_of(census: dict) -> str:
    """'docked' when the structured layout's dock is on screen (w894: the Deck's default with a building selected, where
    Station Info and the hover card were stacked top left and no check looked), else 'undocked'. A census may say it
    itself with a "layout" key."""
    if census.get("layout"):
        return str(census["layout"])
    docked = any("/StructuredDock/" in "/" + e["path"] + "/" or "/StructuredStation/" in "/" + e["path"] + "/"
                 for e in census["elements"])
    return "docked" if docked else "undocked"


def shift(d) -> str:
    dx, dy, dw, dh = (d[0] + d[2]) / 2, (d[1] + d[3]) / 2, d[2] - d[0], d[3] - d[1]
    size = "" if max(abs(dw), abs(dh)) <= 1 else f", size {dw:+.0f} x {dh:+.0f} px"
    return f"x {dx:+.0f}, y {dy:+.0f} px{size}"


def describe_move(block: dict) -> str:
    """The block's outer rect before and after, then what moved inside it (the largest part first)."""
    b, a = block["before"], block["after"]
    outer = "outer rect unchanged" if max(abs(d) for d in block["delta"]) <= 1 else shift(block["delta"])
    text = (f"{outer} (was {round(b[0])},{round(b[1])} {round(b[2] - b[0])}x{round(b[3] - b[1])}, now {round(a[0])},"
            f"{round(a[1])} {round(a[2] - a[0])}x{round(a[3] - a[1])})")
    parts = block.get("parts") or []
    inner = [u for u in parts if u["path"] != block["path"]]
    if len(inner) > 1:
        text += f"; {len(inner)} parts moved inside"
    differs = [u for u in inner if max(abs(x - y) for x, y in zip(u["delta"], block["delta"])) > 1]
    if differs:
        largest = differs[0]
        text += f"{',' if len(inner) > 1 else ';'} largest {largest['path'][len(block['path']) + 1:]} {shift(largest['delta'])}"
    return text


MARK = "mark: ?"


def moved_lines(results: list[dict], move_px: float, how: str) -> list[str]:
    """The `Moved:` line and one list line per move and per gone object, each ending in the mark the PR replaces."""
    sizes = ", ".join(r["screen"] for r in results)
    count = sum(len(r["moved"]) + len(r["gone"]) for r in results)
    lines = [f"Moved: {count} element move(s) over {move_px:.0f} px at {sizes} ({how}, the same save and screens before "
             f"and after); mark each below asked (who): \"their words naming it\", from the brief, or put it back (w894)"]
    for r in results:
        for unit in r["moved"]:
            lines.append(f"- {r['screen']} {under_canvas(unit['path'])}: {describe_move(unit)}: {MARK}")
        for path in r["gone"]:
            lines.append(f"- {r['screen']} {under_canvas(path)}: gone from the screen: {MARK}")
        if r["new"]:
            lines.append(f"  (new at {r['screen']}, not counted: {', '.join(under_canvas(p) for p in r['new'][:8])})")
    return lines


# ---------------------------------------------------------------------------------------------------------------
# pins (w894)


def pin_check(census: dict, pin: dict) -> tuple[str, str]:
    """('ok' | 'broken' | 'not shown', what was measured) for one pin of hud-pins.json in one census.

    above        the element's bottom edge at most maxGap x H above the anchor's top edge, not below it, and over it
                 (sharing some of its width). When the anchor is not on screen (the dock hides the ability row and the
                 minimap), the element stands in the anchor's own region instead (region: minBottom x H for its bottom
                 edge, its centre between centerXMin and centerXMax x W, or its right edge past minRight x W).
    offLeftEdge  the element's left edge at least minLeft x W from the screen's left edge."""
    w, h = census.get("screen") or [0, 0]
    r = find(census, pin["element"])
    if r is None:
        return "not shown", f"{pin['element']} is not on screen"
    at = f"{round(r[0])},{round(r[1])} {round(r[2] - r[0])}x{round(r[3] - r[1])}"
    if pin["rule"] == "offLeftEdge":
        need = pin["minLeft"] * w
        if r[0] < need:
            return "broken", f"left edge at {r[0]:.0f} px, less than {need:.0f} px from the screen's edge ({at})"
        return "ok", f"left edge at {r[0]:.0f} px ({at})"
    if pin["rule"] != "above":
        raise ValueError(f"hud-pins.json: unknown rule {pin['rule']!r}")
    anchor = find(census, pin["anchor"])
    if anchor is not None:
        gap = anchor[1] - r[3]
        over = min(r[2], anchor[2]) - max(r[0], anchor[0])
        if gap < -2 or gap > pin["maxGap"] * h or over <= 0:
            return "broken", (f"bottom edge {gap:.0f} px above {pin['anchor'].split('/')[-1]}'s top edge (0 to "
                              f"{pin['maxGap'] * h:.0f} px), {max(over, 0):.0f} px of its width shared ({at})")
        return "ok", f"{gap:.0f} px above {pin['anchor'].split('/')[-1]} ({at})"
    region = pin["region"]
    problems = []
    if r[3] < region["minBottom"] * h:
        problems.append(f"bottom edge at {r[3]:.0f} px, above {region['minBottom'] * h:.0f}")
    centre = (r[0] + r[2]) / 2
    if "centerXMin" in region and not region["centerXMin"] * w <= centre <= region["centerXMax"] * w:
        problems.append(f"centre at x {centre:.0f}, outside {region['centerXMin'] * w:.0f}..{region['centerXMax'] * w:.0f}")
    if "minRight" in region and r[2] < region["minRight"] * w:
        problems.append(f"right edge at {r[2]:.0f} px, left of {region['minRight'] * w:.0f}")
    where = f"{pin['anchor'].split('/')[-1]} not on screen, so its region"
    if problems:
        return "broken", f"{where}: {'; '.join(problems)} ({at})"
    return "ok", f"{where} ({at})"


def pinned_lines(censuses: list[tuple[str, dict]], spec: dict, how: str) -> tuple[list[str], int]:
    """The `Pinned:` line and one line per broken or missing pin, and the number broken."""
    pins = spec.get("pins", [])
    states = [f"{int((c.get('screen') or [0, 0])[0])}x{int((c.get('screen') or [0, 0])[1])} {layout_of(c)}" for _, c in censuses]
    broken, missing, details = 0, 0, []
    for (name, census), state in zip(censuses, states):
        for pin in pins:
            verdict, what = pin_check(census, pin)
            if verdict == "broken":
                broken += 1
                details.append(f"  BROKEN {state} ({name}): {pin['name']} (GamePanels/{pin['element']}): {what}; it belongs "
                               f"{pin['where']}. {pin['who'][-1]}")
            elif verdict == "not shown":
                missing += 1
                details.append(f"  NOT SHOWN {state} ({name}): {pin['name']}: take the census with it up")
    head = (f"Pinned: {len(pins)} pin(s) in {len(censuses)} census(es) ({', '.join(states)}): {broken} broken, {missing} "
            f"not shown ({how}, hud-pins.json: {', '.join(p['name'] for p in pins)})")
    return [head] + details, broken


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
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        # w807: a bare "ModuleNotFoundError: No module named 'PIL'" cost a turn on a Mac with no Pillow anywhere.
        raise SystemExit("ui_layout.py needs Pillow to sample --shot/--ref-shot: python3 -m venv <your temp dir>/pil && "
                         "<your temp dir>/pil/bin/pip install pillow, then run this script with <your temp dir>/pil/bin/python")
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
    patterns = opened_patterns(spec)
    failed = False

    ob, oa = overlaps(before, args.block_depth, opened=patterns), overlaps(after, args.block_depth, opened=patterns)
    new = {k: v for k, v in oa.items() if k not in ob}
    moved = moved_blocks(before, after, args.block_depth, args.tolerance)
    kept = {k: v for k, v in oa.items() if k in ob and (k[0] in moved or k[1] in moved)}
    over = opened_over_hud(after, patterns, args.block_depth)
    print(f"Overlaps: {len(ob)} block pairs before, {len(oa)} after, {len(new)} new, {len(kept)} kept between blocks "
          f"the change moved (ui_layout.py, whole screen, block depth {args.block_depth}); {len(over['pairs'])} "
          f"opened-panel pair(s) over the HUD, not counted here")
    for (a, b), v in sorted(new.items(), key=lambda kv: -kv[1]["px"])[:15]:
        print(f"  NEW: {short(a)}  x  {short(b)}: {v['px']:.0f} px2, e.g. {short(v['example'][0], 2)} under {short(v['example'][1], 2)}")
    for (a, b), v in sorted(kept.items(), key=lambda kv: -kv[1]["px"])[:15]:
        print(f"  KEPT: {short(a)}  x  {short(b)}: {ob[(a, b)]['px']:.0f} -> {v['px']:.0f} px2: the change moved one of "
              f"them and left them overlapping")
    failed |= bool(new) or bool(kept)

    problems = over["under"] + over["blocked"] + over["cut"]
    if args.closed:
        gone = restored(load(args.closed), over["covered"], args.tolerance) if over["covered"] else []
        problems += gone
        back = f"{'no' if gone else 'yes'} ({len(over['covered'])} covered HUD element(s) checked in {Path(args.closed).name})"
    else:
        gone, back = [], "not checked: pass --closed, a census taken after closing the panel"
    print(f"Opened panels: {len(over['pairs'])} opened panel pair(s) over the HUD (allowed: Ben, w732 and w742), "
          f"{len(over['under'])} under the HUD, {len(over['blocked'])} not clickable, {len(over['cut'])} cut off by the "
          f"screen edge, HUD restored on close: {back}"
          + ("" if over["measured"] else "; draw order not in the census: on-top and clickable NOT measured"))
    for (a, b), v in sorted(over["pairs"].items(), key=lambda kv: -kv[1]["px"])[:15]:
        print(f"  OPENED OVER HUD: {short(a, 2)}  x  {short(b, 1)}: {v['px']:.0f} px2, e.g. {short(v['example'][0], 2)} over "
              f"{short(v['example'][1], 2)}")
    for kind, lines in (("UNDER", over["under"]), ("NOT CLICKABLE", over["blocked"]), ("CUT OFF", over["cut"]),
                        ("NOT RESTORED", gone)):
        for line in lines[:15]:
            print(f"  {kind}: {line}")
    failed |= bool(problems)

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

    lines, broken = pinned_lines([(Path(args.after).name, after)], json.loads(Path(args.pins).read_text(encoding="utf-8")),
                                 "ui_layout.py check")
    for line in lines:
        print(line)
    failed |= broken > 0

    for line in moved_lines([moves(before, after, args.move_px)], args.move_px, "ui_layout.py check"):
        print(line)
    return 1 if failed else 0


def run_pins(args) -> int:
    lines, broken = pinned_lines([(Path(c).name, load(c)) for c in args.census],
                                 json.loads(Path(args.pins).read_text(encoding="utf-8")), "ui_layout.py pins")
    for line in lines:
        print(line)
    return 1 if broken else 0


def run_moves(args) -> int:
    results = [moves(load(b), load(a), args.move_px) for b, a in args.pair]
    for line in moved_lines(results, args.move_px, "ui_layout.py moves"):
        print(line)
    return 0


def run_overlaps(args) -> int:
    census = load(args.census)
    spec = json.loads(Path(args.clusters).read_text(encoding="utf-8"))
    pairs = overlaps(census, args.block_depth, opened=opened_patterns(spec))
    print(f"{len(pairs)} overlapping block pairs between always-on HUD blocks (block depth {args.block_depth})")
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
    c.add_argument("--closed", help="a census taken after closing the opened panel again: the HUD it covered must be back")
    c.add_argument("--clusters", default=str(DEFAULT_CLUSTERS))
    c.add_argument("--ref", default="InventoryPanel", help="path fragment of the classic reference panel")
    c.add_argument("--shot", help="a screenshot taken with the after census")
    c.add_argument("--ref-shot", help="a screenshot with the reference panel (usually the before one)")
    c.add_argument("--ref-census", help="a census with the reference panel open (default: the before census)")
    c.add_argument("--touched", action="append", default=[],
                   help="a path fragment of a window the change is about: always style-checked (repeatable)")
    c.add_argument("--tolerance", type=float, default=2.0)
    c.add_argument("--move-px", type=float, default=4.0, help="an element moving more than this is listed on 'Moved:'")
    m = sub.add_parser("moves", help="what moved, over several sizes: the 'Moved:' line and its list (w826)")
    m.add_argument("--pair", nargs=2, action="append", required=True, metavar=("BEFORE", "AFTER"),
                   help="a before and an after census at one size (repeat: 1920x1080, then 1280x800 at 0.8)")
    m.add_argument("--move-px", type=float, default=4.0)
    q = sub.add_parser("pins", help="every census against the places Ben fixed (hud-pins.json): the 'Pinned:' line (w894)")
    q.add_argument("census", nargs="+")
    q.add_argument("--pins", default=str(DEFAULT_PINS))
    c.add_argument("--pins", default=str(DEFAULT_PINS))
    o = sub.add_parser("overlaps", help="the overlapping block pairs of one census")
    o.add_argument("census")
    o.add_argument("--clusters", default=str(DEFAULT_CLUSTERS))
    k = sub.add_parser("clusters", help="cluster edges of one census or tour log")
    k.add_argument("census")
    k.add_argument("--clusters", default=str(DEFAULT_CLUSTERS))
    for p in (c, o):
        p.add_argument("--block-depth", type=int, default=2)
    args = ap.parse_args(argv)
    try:
        return {"check": run_check, "overlaps": run_overlaps, "clusters": run_clusters, "moves": run_moves, "pins": run_pins}[args.cmd](args)
    except (ValueError, OSError, KeyError) as error:
        print(f"ui_layout: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
