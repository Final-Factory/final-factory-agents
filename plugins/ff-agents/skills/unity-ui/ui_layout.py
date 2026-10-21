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
  Window     every open window (hud-clusters.json `openedPanels`: the Player Inventory, a Cargo Hold or Station Core or
  overlaps   Station Grid panel, the Station controls strip, a slide-out) against the other windows and against the HUD
             blocks, each pair named with both elements and the overlap rect. An overlap is allowed only when
             hud-clusters.json `windowOverlaps` lists it with the requester's words (or the dock hosts the window as its
             tab); every other one is NOT ALLOWED. A pair in `after` that is not in `before` is new and one left between
             windows the change moved is kept: FAIL (w981: the Station strip stood 11 px over the Player Inventory in the
             Deck's classic layout and `overlaps` counted 0, because a window is not an always-on HUD block).
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

  Covered    every text of an opened screen whose DRAWN glyph bounds (the census `textRect`, which can reach past the
  text      text's RectTransform when it wraps or overflows) lie under an opaque element drawn above it (w727: the
             Technology tab's "Excess Research" label ran half under the hub's tab bar and `Opened panels` said 0, because
             the census held only RectTransform boxes). A text covered after and not before: FAIL; one covered in both is
             listed as standing. Texts clipped by a mask are skipped (the census has no mask rect for the glyphs).

  Moved      every element that moved or resized more than --move-px px (4), grouped into the largest object that
             moved as one, and every object that is gone (w826: #1282 moved the Station Info box to the top left and
             w722/#1282 put the objectives card under the Station strip; Ben: "i didnt tell you to move that"). Listed,
             not judged: the pull request marks each one asked (quoting the requester) or not asked, and pr_evidence.py
             fails it while one is unmarked.

  Pinned     every place Ben fixed himself (hud-pins.json: Station Info over the abilities, the building hover card over
             the minimap, the Player Inventory off the left edge), checked in the after census whatever the before one
             showed, so an earlier PR's move never becomes the new normal (w894). A broken pin: FAIL.

It prints the `Overlaps:`, `Window overlaps:`, `Opened panels:`, `Covered text:`, `Alignment:`, `Style:`, `Pinned:` and `Moved:` lines the
pull request carries (pr_evidence.py reads them) and exits 1 when any of the first six fails, 2 on bad input.

    ui_layout.py pins <census.json> [<census.json> ...]   the `Pinned:` line over every census (w894): take them at
                                               1920x1080, 1280x800 undocked and 1280x800 docked, a station selected

    ui_layout.py moves --pair before-1920.json after-1920.json --pair before-1280.json after-1280.json [--move-px 4]
                                               the `Moved:` line and its list over both standard sizes (w826)

    ui_layout.py options --option A master-1280.json a-1280.json [--option A master-1920.json a-1920.json]
                         --option B master-1280.json b-1280.json ... --named <path fragment> [--named ...]
                                               the `Options:` line (w1429): every option or mock still of a round, each
                                               against master's census on the same screen, BEFORE the person sees it. A
                                               moved, resized or gone object that is not under a --named fragment (the
                                               elements the person's words name), or a broken pin (hud-pins.json) whose
                                               element is not named, puts that option OUT: drop it, never offer it. Exits 1
                                               while one is OUT (w1386: options A/B/C each moved the station controls
                                               after Ben said to keep them where they were).

    ui_layout.py covered-text <census.json>    the texts of opened screens drawn under an opaque element (w727); exits 1 on one

    ui_layout.py shape <census.json> [...] [--repo <game repo>]
                                               the `Shape:` line (w1396): one census judged on its own, the way a player
                                               looks at it. STRETCHED: an Image drawn 2x or more off its sprite's own aspect
                                               (Simple or Filled, not preserveAspect, no 9-slice border; the w1386 On/Off
                                               switch, sprite 225x150, drawn 485x23 in the Deck dock). MOSTLY EMPTY: a window
                                               or dialog under 40 % covered by its content with one empty rectangle of 35 % or
                                               more of it (the w1386 Light Structure panel at 1920x1080: 30 % and 37 %).
                                               WALL OF TEXT: a text of 8 or more lines in a box under 40 % of the screen wide
                                               (w1296's "Content removed" dialog). --repo reads sprite sizes from the game's
                                               PNGs for a census without `spriteSize`. Exits 1 on any finding.

    ui_layout.py overlaps <census.json>        the overlapping HUD block pairs of one census, then every window overlap
                                               (allowed ones with their quote, the rest NOT ALLOWED); exits 1 on one of those
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
# A Slider's fill and handle (Unity's default children `Fill Area`/`Fill`, `Handle Slide Area`/`Handle`) take their rect
# from the slider's value: two censuses of a live bar (a production progress bar) at different moments differ by its
# value, not by a layout move. `moves` leaves them out (w1627: the Dyson platform's Exotic Matter Generation bar's
# `Fill Area` read as moved 50 to 62 px between matched before/after sessions of the same code path).
SLIDER_VALUE = re.compile(r"/(Fill Area|Handle Slide Area)(/|$)")
# A border, frame or outline sprite is hollow: the census has its rect, not its holes, so it cannot cover a text (the Technology
# tab's selected tile: `SelectionFrame`, sprite `TechDependencyBorder`, orange ring over the tile's own cost text; w727).
HOLLOW = re.compile(r"frame|border|outline|highlight|glow|shadow", re.IGNORECASE)


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


def backdrop_patterns(spec: dict | None) -> list[str]:
    """hud-clusters.json `backdrops`: full-screen views the HUD is drawn over (the map). Not an HUD block, not a panel the
    player opens over the HUD: what lies on it is not an overlap with it (w959: the Map Controls always lie on the map view,
    and `Map x MapControls` failed every check that moved them)."""
    return list(((spec or {}).get("backdrops") or {}).get("paths", []))


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


def overlaps(census: dict, depth: int = 2, min_px: float = 16.0, opened: list[str] | None = None,
             backdrops: list[str] | None = None) -> dict:
    """{(blockA, blockB): {"px": area, "example": (pathA, pathB)}} for always-on HUD blocks whose solid elements overlap.
    With `opened` (the openedPanels patterns) an element of a panel the player opens does not count: it may cover the
    HUD (see opened_over_hud, which checks that it does so properly)."""
    pairs: dict[tuple[str, str], dict] = {}
    for a, ba, b, bb, px, _ in _pairs(census, depth, min_px, same_block=False):
        if opened and (opened_prefix(a["path"], opened) or opened_prefix(b["path"], opened)):
            continue
        if backdrops and (opened_prefix(a["path"], backdrops) or opened_prefix(b["path"], backdrops)):
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
        # Every rect per path: siblings can share a name (three ObjectiveItem tips are all TipParent/TipText, w1329).
        rects = out["covered"].setdefault(b["path"], [])
        rect = b.get("visible") or b["rect"]
        if rect not in rects:
            rects.append(rect)
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


def covered_text(census: dict, patterns: list[str], min_share: float = 0.2, min_px: float = 16.0) -> list[dict]:
    """Texts of an opened screen whose drawn glyph bounds (`textRect`) lie under an opaque element drawn above them (w727:
    the Technology tab's "Excess Research 0.0" label wrapped to a second line under the hub's tab bar; every other check
    compared RectTransform boxes, and the label's box was clear of the bar). Returns [{"path", "text", "by", "share", "rect"}].
    A text clipped by a mask is skipped: the census has no mask rect for glyphs that overflow its box."""
    texts = [e for e in census["elements"] if e.get("text") and e.get("textRect") and not any(i in e["path"] for i in IGNORE)
             and opened_prefix(e["path"], patterns) and area(e["textRect"]) >= 4
             and all(abs(a - b) <= 1 for a, b in zip(e.get("visible") or e["rect"], e["rect"]))]
    covers = [e for e in census["elements"] if not e.get("maskOnly") and "Text" not in e.get("kind", "")
              and e.get("alpha", 1.0) >= 0.9 and not any(i in e["path"] for i in IGNORE) and area(e.get("visible") or e["rect"]) >= 4
              and not HOLLOW.search(e["path"].rsplit("/", 1)[-1] + " " + e.get("sprite", ""))]
    found = []
    for t in texts:
        tr = t["textRect"]
        best = None
        for c in covers:
            if above(c, t) is not True:
                continue
            both = inter(tr, c.get("visible") or c["rect"])
            px = area(both) if both[2] > both[0] and both[3] > both[1] else 0.0
            if px >= min_px and px >= min_share * area(tr) and (best is None or px > best[0]):
                best = (px, c, both)
        if best:
            found.append({"path": t["path"], "text": t["text"], "by": best[1]["path"], "share": best[0] / area(tr), "rect": best[2]})
    return found


def covered_key(f: dict):
    return (f["path"], f["text"])


def covered_text_line(f: dict) -> str:
    return (f"{short(f['path'], 3)} \"{f['text']}\": {100 * f['share']:.0f}% of its drawn text is under {short(f['by'], 2)} "
            f"(rect {rect_text(f['rect'])})")


def restored(closed: dict, covered: dict, tolerance: float = 2.0) -> list[str]:
    """The HUD elements an opened panel covered, in the census taken after closing it: each must be there, drawn, at
    the same place (the HUD is back as it was). `covered` maps a path to its rects (or one rect). Siblings that share a
    name are matched by place, not by their order in the census (w1329: three objective tips, all TipParent/TipText,
    listed in another order read as 'not where it was' at the same three places)."""
    now: dict[str, list] = {}
    for e in closed["elements"]:
        if solid(e):
            now.setdefault(e["path"], []).append(e.get("visible") or e["rect"])
    problems = []
    for path, rects in sorted(covered.items()):
        rects = [rects] if rects and not isinstance(rects[0], (list, tuple)) else rects
        there = now.get(path)
        if not there:
            problems.append(f"{short(path, 2)} is gone from the screen after closing the panel")
        elif any(min(max(abs(x - y) for x, y in zip(r, rect)) for r in there) > tolerance for rect in rects):
            problems.append(f"{short(path, 2)} is not where it was after closing the panel")
    return problems


def moved_blocks(before: dict, after: dict, depth: int = 2, tolerance: float = 2.0) -> set[str]:
    """Blocks with an element (matched by path, present on both sides) whose visible rect moved more than tolerance.
    An overlap the change leaves between blocks it moved is the change's to fix, even if it was there before
    (w733: 7f75224fa moved the slide-out toggles and the hotbar apart and left the Blueprint slide-out over the
    hotbar, 14689 -> 3948 px2)."""
    old, now = keyed_visible(before), keyed_visible(after)
    moved = set()
    for key, r in now.items():
        was = old.get(key)
        if was is not None and max(abs(a - b) for a, b in zip(was, r)) > tolerance:
            moved.add(block_of(key[0], depth))
    return moved


def keyed_visible(census: dict) -> dict:
    """{(path, n): visible rect} for every element but the development overlays, siblings that share a path told apart
    by reading order as in keyed(). Keyed by path alone, the 30 `item-slot(Clone)` slots of the Player Inventory
    collapsed into one, every other slot read as moved 300-400 px, and the window overlaps that stood unchanged on
    develop were called kept between windows the change moved (w1004, game PR #1466: `moves` found 0 moves)."""
    by_path: dict[str, list] = {}
    for e in census["elements"]:
        if any(i in e["path"] for i in IGNORE):
            continue
        by_path.setdefault(e["path"], []).append(e.get("visible") or e["rect"])
    out = {}
    for path, rects in by_path.items():
        for i, r in enumerate(sorted(rects, key=lambda r: (round(r[1]), round(r[0])))):
            out[(path, i)] = r
    return out


# ---------------------------------------------------------------------------------------------------------------
# window overlaps (w981)


def window_spec(spec: dict | None) -> dict:
    return (spec or {}).get("windowOverlaps") or {}


def path_has(path: str, pattern: str) -> bool:
    """Whether `pattern` (path components, fnmatch globs; a run anywhere in the path, '(Clone)' ignored) is in `path`."""
    return opened_prefix(path, [pattern]) is not None


def unit_of(path: str, patterns: list[str], backdrops: list[str], depth: int):
    """('W', window path) for an element of a window the player opens, ('H', block path) for always-on HUD, None for a
    backdrop (the map view)."""
    window = opened_prefix(path, patterns)
    if window:
        return "W", window
    if backdrops and opened_prefix(path, backdrops):
        return None
    return "H", block_of(path, depth)


def unit_name(label: str, spec: dict | None) -> str:
    """A person's name for a window or block, then its path under the canvas: 'Player Inventory (GamePanels/MiniInventory)'."""
    plain = under_canvas(label)
    for pattern, name in (window_spec(spec).get("names") or {}).items():
        if path_has(label, pattern):
            return f"{name} ({plain})"
    return plain


def when_holds(when: dict | None, census: dict, rects: dict, label_a: str) -> bool:
    """An allow-list entry's condition, measured on the census. aStandsAbove: the entry's `a` window stands directly over
    the named element (its bottom edge no lower than that element's top edge, sharing some of its width). The element
    not on screen: the condition does not hold (Ben's w873 words allow the strip over the Player Inventory only while it
    stands above Station Info)."""
    if not when:
        return True
    for key, value in when.items():
        if key != "aStandsAbove":
            raise ValueError(f"hud-clusters.json windowOverlaps: unknown condition {key!r}")
        anchor = find(census, value)
        mine = rects.get(label_a)
        if anchor is None or mine is None:
            return False
        if mine[3] > anchor[1] + 4 or min(mine[2], anchor[2]) - max(mine[0], anchor[0]) <= 0:
            return False
    return True


def allowance(spec: dict | None, census: dict, rects: dict, a: dict, la: str, b: dict, lb: str):
    """('hosting' | 'allowed', the words or source) when hud-clusters.json lists the pair of elements, else None."""
    ws = window_spec(spec)
    for host in ws.get("hosting", []):
        for outer, inner in ((a, b), (b, a)):
            if path_has(outer["path"], host["host"]) and any(path_has(inner["path"], t) for t in host["tenants"]):
                return "hosting", host["source"]
    for entry in ws.get("allowed", []):
        for x, y, lx in ((a, b, la), (b, a, lb)):
            if path_has(x["path"], entry["a"]) and path_has(y["path"], entry["b"]) and when_holds(entry.get("when"), census, rects, lx):
                return "allowed", entry["who"][-1]
    return None


def window_overlaps(census: dict, spec: dict | None, depth: int = 2, min_px: float = 16.0) -> list[dict]:
    """Every overlap that involves an open window (w981): window x window and window x always-on HUD block, one entry per
    pair of owners and verdict, {"a", "b" (labels), "kind", "px", "rect" (the union of the overlapping parts), "status"
    ('hosting' | 'allowed' | 'not allowed'), "why" (the quote or source), "example"}. HUD x HUD pairs are `overlaps`';
    a window the dock hosts as a tab is not an overlap with the dock."""
    patterns, backdrops = opened_patterns(spec), backdrop_patterns(spec)
    items = []
    for e in census["elements"]:
        if not solid(e) or area(e.get("visible") or e["rect"]) < 4:
            continue
        unit = unit_of(e["path"], patterns, backdrops, depth)
        if unit:
            items.append((e, unit[0], unit[1]))
    rects: dict[str, list] = {}
    for e, _, label in items:
        r = e.get("visible") or e["rect"]
        rects[label] = union([rects[label], r]) if label in rects else list(r)
    found: dict[tuple, dict] = {}
    for i in range(len(items)):
        a, ka, la = items[i]
        ra = a.get("visible") or a["rect"]
        for j in range(i + 1, len(items)):
            b, kb, lb = items[j]
            if (ka == "H" and kb == "H") or la == lb or la.startswith(lb + "/") or lb.startswith(la + "/"):
                continue
            rb = b.get("visible") or b["rect"]
            if rb[0] >= ra[2] or rb[2] <= ra[0] or rb[1] >= ra[3] or rb[3] <= ra[1]:
                continue
            both = inter(ra, rb)
            px = area(both)
            if px < max(min_px, 0.05 * min(area(ra), area(rb))):
                continue
            verdict = allowance(spec, census, rects, a, la, b, lb)
            status, why = verdict if verdict else ("not allowed", "")
            first, second = sorted(((la, a), (lb, b)), key=lambda t: t[0])
            key = (first[0], second[0], status)
            entry = found.setdefault(key, {"a": first[0], "b": second[0], "px": 0.0, "rect": list(both), "status": status,
                                           "why": why, "kind": "window x window" if ka == kb == "W" else "window x HUD",
                                           "example": (first[1]["path"], second[1]["path"])})
            entry["px"] += px
            entry["rect"] = union([entry["rect"], both])
    return sorted(found.values(), key=lambda v: (v["status"] != "not allowed", -v["px"]))


def moved_units(before: dict, after: dict, spec: dict | None, depth: int = 2, tolerance: float = 2.0) -> set[str]:
    """The windows and blocks (by unit label) with an element, matched by path, that moved over `tolerance`."""
    patterns, backdrops = opened_patterns(spec), backdrop_patterns(spec)
    old, now = keyed_visible(before), keyed_visible(after)
    out = set()
    for key, r in now.items():
        was = old.get(key)
        if was is not None and max(abs(a - b) for a, b in zip(was, r)) > tolerance:
            unit = unit_of(key[0], patterns, backdrops, depth)
            if unit:
                out.add(unit[1])
    return out


def window_diff(before: dict, after: dict, spec: dict | None, depth: int = 2, tolerance: float = 2.0) -> dict:
    """The not-allowed window overlaps of `after` split into new (not in `before`), kept (in both, between windows the
    change moved, the overlap itself changed: theirs to fix) and standing (in both, neither moved or the overlap rect is
    the same within `tolerance`: noted, not this change's). A row added inside a full-screen window moves its inner parts
    but leaves its overlaps with the HUD pixel for pixel; those were called kept (w1058, game PR #1512: the Technology
    screen's five overlaps with the HUD, identical rects before and after, failed pr_evidence.py)."""
    bad_after = [v for v in window_overlaps(after, spec, depth) if v["status"] == "not allowed"]
    bad_before = {(v["a"], v["b"]): v for v in window_overlaps(before, spec, depth) if v["status"] == "not allowed"}
    moved = moved_units(before, after, spec, depth, tolerance)
    new, kept, standing = [], [], []
    for v in bad_after:
        was = bad_before.get((v["a"], v["b"]))
        if was is None:
            new.append(v)
        elif (v["a"] in moved or v["b"] in moved) and                 max(abs(a - b) for a, b in zip(was["rect"], v["rect"])) > tolerance:
            kept.append(v)
        else:
            standing.append(v)
    return {"new": new, "kept": kept, "standing": standing, "before": len(bad_before), "after": len(bad_after)}


def rect_text(r) -> str:
    return f"{round(r[0])},{round(r[1])} to {round(r[2])},{round(r[3])} ({round(r[2] - r[0])}x{round(r[3] - r[1])} px)"


def window_overlap_text(v: dict, spec: dict | None) -> str:
    """One overlap named with both elements and the overlap rect; an allowed one carries its quote or source."""
    text = f"{unit_name(v['a'], spec)}  x  {unit_name(v['b'], spec)}: {v['px']:.0f} px2, overlap rect {rect_text(v['rect'])}"
    if v["status"] == "not allowed":
        return text
    return f"{text}; {'hosted by the dock' if v['status'] == 'hosting' else 'allowed'}: {v['why']}"


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
    moved = [k for k in common if max(abs(d) for d in delta[k]) > move_px and not SLIDER_VALUE.search(k[0])]

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
    gone, new = sorted(blocks_old - blocks_new), sorted(blocks_new - blocks_old)
    reparented = []
    for block in list(gone):
        target = reparent_target(block, old, now, same)
        if target in new:
            reparented.append((block, target))
            gone.remove(block)
            new.remove(target)
    w, h = after.get("screen") or before.get("screen") or [0, 0]
    biggest = lambda b: -max(max(abs(d) for d in b["delta"]), max(abs(d) for d in b["parts"][0]["delta"]))
    layout = layout_of(after)
    if layout_of(before) != layout:
        raise ValueError(f"the before census is {layout_of(before)} and the after one {layout}: compare the same layout")
    return {"moved": sorted(blocks.values(), key=biggest), "gone": gone, "new": new, "reparented": reparented,
            "screen": f"{int(w)}x{int(h)} {layout}"}


def reparent_target(block: str, old: dict, now: dict, same) -> str | None:
    """The block of the after census that `block` (gone from it) stands in under another parent, in the same place: every
    element of it has one in the after census whose path from the canvas ends in its own (or the reverse) and whose
    rect is the same within the tolerance, all in one block. w1487 put the map's arrow back to the player under
    GamePanels so the windows a player opens draw over it: the same arrow in the same place read as gone from the
    screen, and the PR gate has no mark for that but asked (who)."""
    elements = [(k, r) for k, r in old.items() if k[0] == block or k[0].startswith(block + "/")]
    target = None
    for (path, index), rect in elements:
        tail = under_canvas(path)
        hit = next((k for k in now if k not in old and k[1] == index and same(now[k], rect)
                    and (under_canvas(k[0]).endswith("/" + tail) or tail.endswith("/" + under_canvas(k[0])))), None)
        if hit is None:
            return None
        found = block_of(hit[0], 2)
        if target not in (None, found):
            return None
        target = found
    return target


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
        for old_path, new_path in r.get("reparented", []):
            lines.append(f"  (reparented at {r['screen']}, the same place, not counted: {under_canvas(old_path)} -> "
                         f"{under_canvas(new_path)})")
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
# options (w1429)


def is_named(path: str, named: list[str]) -> bool:
    """The object is one the person named, or inside one: a --named fragment matches whole path segments
    ("BlueprintActionBar/SaveNewBlueprint" matches ".../BlueprintActionBar/SaveNewBlueprint/Label", not
    ".../BlueprintActionBar"). An ancestor of a named object is not named: when the whole block moved together, its
    siblings moved too."""
    padded = "/" + path.strip("/") + "/"
    return any("/" + n.strip("/") + "/" in padded for n in named if n.strip("/"))


def option_check(base: dict, after: dict, named: list[str], spec: dict | None = None, move_px: float = 4.0) -> dict:
    """One option still's census against master's on the same screen and layout: what moved that the person did not
    name. Returns {"screen", "unnamed": [line text], "named": [line text]}. Every moved part (moves(): the largest object
    that moved as one) and every gone block outside the named fragments is unnamed; so is a pin of hud-pins.json the
    option breaks while master keeps it, unless its element is named."""
    result = moves(base, after, move_px)
    unnamed, ok = [], []
    for block in result["moved"]:
        for part in block["parts"]:
            text = f"{under_canvas(part['path'])}: {shift(part['delta'])}"
            (ok if is_named(part["path"], named) else unnamed).append(text)
    for path in result["gone"]:
        (ok if is_named(path, named) else unnamed).append(f"{under_canvas(path)}: gone from the screen")
    for pin in (spec or {}).get("pins", []):
        if pin_check(after, pin)[0] == "broken" and pin_check(base, pin)[0] != "broken"                 and not any(n.strip("/").split("/")[-1] == pin["element"] or pin["element"] in n for n in named):
            unnamed.append(f"pin {pin['name']} broken: it belongs {pin['where']}")
    return {"screen": result["screen"], "unnamed": unnamed, "named": ok}


def option_lines(options: dict[str, list[dict]], named: list[str], how: str) -> tuple[list[str], int]:
    """The `Options:` line and one line per option and screen, and the number of options OUT."""
    out = [name for name, checks in options.items() if any(c["unnamed"] for c in checks)]
    lines = [f"Options: {len(options)} option(s), {len(options) - len(out)} keep every element the person did not name in "
             f"place, {len(out)} OUT ({', '.join(out) or 'none'}) ({how}, each against master on the same screen; named: "
             f"{', '.join(named) or 'nothing'})"]
    for name, checks in options.items():
        for c in checks:
            if c["unnamed"]:
                for text in c["unnamed"]:
                    lines.append(f"- {name} {c['screen']}: OUT, moves what the person did not name: {text}")
            else:
                moved = f"; named moved: {'; '.join(c['named'])}" if c["named"] else ""
                lines.append(f"- {name} {c['screen']}: keeps every unnamed element in place{moved}")
    if out:
        lines.append("  An option that moves an element the person did not name is never offered (w1429: Ben, \"getting "
                     "extremely worried you guys moved the fucking station controls panel when i told you not to twelve "
                     "times\"). Drop it; when the named change does not fit without moving something, report the conflict "
                     "and offer only options that keep it in place, or ask.")
    return lines, len(out)


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
    ref = ref_from = None
    for census in (ref_census, before, after):
        if census is not None and ref is None:
            ref = reference(census, ref_fragment)
            ref_from = census
    touched = changed_panels(before, after, touched_fragments)
    summaries, failures = [], []
    if not touched:
        return ["no panel changed colour, alpha or art" + (" and no --touched panel is open" if touched_fragments else "")], []
    if ref is None:
        return [], [f"no reference panel matching '{ref_fragment}' in the census: open the classic panel too, or pass --ref"]
    for e in touched:
        # The reference itself, in the same census: nothing to compare. The same panel taken from the before (or
        # --ref-census) census is its own look on master, which is the reference a spacing or layout change wants
        # (w1418: `--touched Tooltip(Clone) --ref Tooltip(Clone)` printed "Style: nothing checked").
        if e["path"] == ref["path"] and ref_from is after:
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
# shape: what a player calls obviously broken (w1396)
#
# Ben, 2026-10-16, on stills two workers and an orchestrator had passed: "the light panel is really messed up obviously"
# (w1386: the Light Structure's On/Off switch drawn as a 485x23 bar in the Deck dock, the 1920 panel mostly empty) and
# "looks terrible. you can do better" (w1296: a narrow "Content removed" dialog holding a dense block of text). Every
# other check compares two censuses; these judge one, the way a player looks at it.

STRETCH_RATIO = 2.0     # drawn aspect over the sprite's own aspect (or its inverse) at which a Simple image reads as stretched
# A window whose content covers under SPARSE_SHARE of it AND leaves one empty rectangle of HOLE_SHARE or more reads as mostly
# empty, its content crammed into a corner. Coverage alone does not tell (w1396, the w1386 tour's 1920x1080 censuses: the Cargo
# Hold, which looks fine, 24 % covered with a 25 % hole; the Light Structure 30 % with a 37 % hole; the broken stacked circuit
# blocks 28 % with 49 %).
SPARSE_SHARE = 0.40
HOLE_SHARE = 0.35
CONTENT_PAD = 4.0       # px of breathing room counted as filled around each piece of content (scaled to 1080 lines)
WALL_LINES = 8          # a text of this many lines or more ...
# What draws pixels: a hit area or other custom Graphic (`HeaderHitArea`) is a raycast target a player never sees.
DRAWN = re.compile(r"^(Image|RawImage|TextMeshProUGUI|TextMeshPro|Text|TMP_SubMeshUI)$")
WALL_WIDTH = 0.40       # ... in a box narrower than this share of the screen reads as a wall of text


def sprite_sizes(repo: str | Path | None) -> dict:
    """{sprite name: (w, h, has 9-slice border)} for every single-sprite PNG under <repo>/Assets, read from the PNG header and
    its .meta (spriteMode 1). For censuses without the `spriteSize` field (Deck tours before w1396)."""
    found: dict[str, tuple[int, int, bool]] = {}
    ambiguous: set[str] = set()
    if not repo:
        return found
    for png in Path(repo, "Assets").rglob("*.png"):
        meta = png.with_name(png.name + ".meta")
        try:
            head = png.open("rb").read(24)
            text = meta.read_text(encoding="utf-8", errors="replace") if meta.exists() else ""
        except OSError:
            continue
        if head[:8] != b"\x89PNG\r\n\x1a\n" or not re.search(r"^\s*spriteMode: 1\s*$", text, re.MULTILINE):
            continue
        border = re.search(r"spriteBorder: \{x: ([\d.]+), y: ([\d.]+), z: ([\d.]+), w: ([\d.]+)\}", text)
        sliced = bool(border) and any(float(v) > 0 for v in border.groups())
        size = (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"), sliced)
        if found.get(png.stem, size) != size:
            ambiguous.add(png.stem)  # two sprites of one name and different shapes (three arrow.png): which one is drawn is unknown
        found.setdefault(png.stem, size)
    return {k: v for k, v in found.items() if k not in ambiguous}


SPRITE_FILES = (".png", ".psd", ".tga")


def invisible_sprites(repo: str | Path | None, names) -> set[str]:
    """The sprite names among `names` whose image under <repo>/Assets has every pixel fully transparent (alpha 0): a hit
    area that draws nothing (w1468: `Assets/Art/UI/UI2/transparent-block.psd`, 512x512, the tile behind the game's
    TabSettingsButton and MainMenuButton). A name with several files counts only when all of them are transparent. Needs
    Pillow; without it, or without a repo, nothing is skipped."""
    wanted = {n for n in names if n}
    if not repo or not wanted:
        return set()
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        return set()
    verdict: dict[str, bool] = {}
    for path in Path(repo, "Assets").rglob("*"):
        if path.suffix.lower() not in SPRITE_FILES or path.stem not in wanted:
            continue
        try:
            with Image.open(path) as im:
                clear = im.convert("RGBA").getchannel("A").getextrema()[1] == 0
        except (OSError, ValueError):
            clear = False
        verdict[path.stem] = verdict.get(path.stem, True) and clear
    return {n for n, clear in verdict.items() if clear}


def glyph_box(e: dict):
    """Where a text's glyphs are drawn: the census `textRect`, else an estimate from its string and box (left-aligned, a
    character about 0.35 of the box's height wide and the glyphs 0.75 of it tall: measured on the w1386 1920x1080 still,
    "Light Structure", "On/Off" and "Light colour" drew 0.26-0.42 of their box height per character), flagged as estimated."""
    if e.get("textRect"):
        return e["textRect"], False
    r = e.get("visible") or e["rect"]
    text = (e.get("text") or "").strip()
    if not text:
        return None, True
    lines = max(1, e.get("lines") or 1)
    line_h = (r[3] - r[1]) / lines
    w = min(r[2] - r[0], 0.35 * line_h * max(len(t) for t in text.split("\n")) / (1 if lines == 1 else 1))
    top = r[1] + 0.125 * line_h
    return [r[0], top, r[0] + w, top + 0.75 * line_h * lines], True


def coverage(panel_rect, boxes, pad: float, cell: float = 2.0) -> tuple[float, float]:
    """The share of the panel's area that the padded boxes cover, and the share its largest empty rectangle takes (a grid of
    `cell` px; the rectangle by the histogram method)."""
    x0, y0, x1, y1 = panel_rect
    cols, rows = max(1, int((x1 - x0) / cell)), max(1, int((y1 - y0) / cell))
    hit = [bytearray(cols) for _ in range(rows)]
    for b in boxes:
        c0 = max(0, int((b[0] - pad - x0) / cell))
        c1 = min(cols, int(math.ceil((b[2] + pad - x0) / cell)))
        r0 = max(0, int((b[1] - pad - y0) / cell))
        r1 = min(rows, int(math.ceil((b[3] + pad - y0) / cell)))
        for r in range(r0, r1):
            hit[r][c0:c1] = b"\x01" * max(0, c1 - c0)
    covered = sum(sum(row) for row in hit) / float(cols * rows)
    best, heights = 0, [0] * cols
    for row in hit:
        heights = [0 if row[c] else heights[c] + 1 for c in range(cols)]
        stack: list[int] = []
        for c in range(cols + 1):
            h = heights[c] if c < cols else 0
            while stack and heights[stack[-1]] >= h:
                top = heights[stack.pop()]
                left = stack[-1] + 1 if stack else 0
                best = max(best, top * (c - left))
            stack.append(c)
    return covered, best / float(cols * rows)


DIALOG = re.compile(r"Dialog|Modal|Popup", re.IGNORECASE)


def window_root(path: str, patterns: list[str]) -> bool:
    """Whether an element is the background of a window or dialog the player reads as one: an `openedPanels` window
    (a structure panel, the dock, the hub) or a dialog (a component named *Dialog*, *Modal*, *Popup*), the element itself or
    one level under it (`CargoEntityPanel/MainPanel`). The HUD, hover cards, list rows and scroll viewports are not judged
    for emptiness: their ragged rows read as empty to a coverage count and are not (w1396 calibration)."""
    prefix = opened_prefix(path, patterns)
    if prefix is None:
        parts = path.split("/")
        hits = [i for i, part in enumerate(parts) if DIALOG.search(part)]
        if not hits:
            return False
        prefix = "/".join(parts[:hits[0] + 1])
    rest = path[len(prefix):].strip("/")
    return rest.count("/") == 0 and not re.search(r"viewport|scroll|content|row|item", rest, re.IGNORECASE)


def is_panel(e: dict, screen_px: float) -> bool:
    """A drawn background a player reads as a panel or dialog: an opaque-ish Image over 1.5 % and under 60 % of the screen."""
    if e.get("kind") != "Image" or e.get("maskOnly") or e.get("alpha", 1.0) < 0.3 or any(i in e["path"] for i in IGNORE):
        return False
    a = area(e.get("visible") or e["rect"])
    return 0.015 * screen_px <= a <= 0.6 * screen_px and not HOLLOW.search(e.get("sprite") or "")


def shape(census: dict, sprites: dict | None = None, patterns: list[str] | None = None,
          invisible: set[str] | None = None) -> dict:
    """One census judged on its own: stretched sprites, mostly empty windows and dialogs, walls of text (w1396).
    `invisible`: sprite names whose every pixel is transparent (`invisible_sprites`); they draw nothing, so they are never
    stretched (w1468: the game's `transparent-block`, the hit area of its tab and menu buttons, read 45 STRETCHED)."""
    invisible = invisible or set()
    if patterns is None:
        patterns = opened_patterns(json.loads(DEFAULT_CLUSTERS.read_text(encoding="utf-8")))
    sw, sh = (census.get("screen") or [1920, 1080])[:2]
    screen_px = float(sw) * float(sh)
    sprites = sprites or {}
    out = {"stretched": [], "sparse": [], "walls": [], "unknown_sprites": set(), "estimated": False}
    elements = [e for e in census["elements"] if not any(i in e["path"] for i in IGNORE)]

    for e in elements:
        name = e.get("sprite") or ""
        # The aspect is the element's own rect: a mask clips what shows, not the shape the sprite is drawn at (w1486: the
        # Oracle shop's last row, cut in half by its scroll view, rect 43x43, visible 43x21, read STRETCHED on master too).
        # What shows still has to be big enough to judge.
        r, v = e["rect"], e.get("visible") or e["rect"]
        w, h = r[2] - r[0], r[3] - r[1]
        if (not name or e.get("maskOnly") or e.get("alpha", 1.0) < 0.25 or min(w, h) < 6 or name in invisible
                or min(v[2] - v[0], v[3] - v[1]) < 6):
            continue
        if e.get("preserveAspect") or e.get("imageType") == "Tiled":
            continue
        if e.get("spriteSize"):
            nat_w, nat_h = e["spriteSize"]
            sliced = any(v > 0 for v in e.get("spriteBorder") or [])
        elif name in sprites:
            nat_w, nat_h, sliced = sprites[name]
        else:
            out["unknown_sprites"].add(name)
            continue
        if sliced and e.get("imageType", "Sliced") == "Sliced":
            continue  # a 9-slice panel or pill is meant to stretch along its middle
        if not nat_w or not nat_h:
            continue
        ratio = (w / h) / (nat_w / nat_h)
        ratio = max(ratio, 1 / ratio)
        if ratio >= STRETCH_RATIO:
            out["stretched"].append({"path": e["path"], "rect": r, "sprite": name, "native": [nat_w, nat_h],
                                     "ratio": ratio, "type": e.get("imageType", "type not in census")})

    panels_found = [e for e in elements if is_panel(e, screen_px) and window_root(e["path"], patterns)]
    pad = CONTENT_PAD * float(sh) / 1080.0
    for p in panels_found:
        pr = p.get("visible") or p["rect"]
        p_area = area(pr)
        boxes = []
        for e in elements:
            if e is p or not solid(e) or e.get("maskOnly") or not DRAWN.search(e.get("kind", "")):
                continue
            if above(e, p) is False:
                continue
            r = e.get("visible") or e["rect"]
            if "Text" in e.get("kind", ""):
                r, est = glyph_box(e)
                if r is None:
                    continue
                out["estimated"] |= est
            cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
            # A frame or inner background as big as the panel is the panel, not what it holds; a picture (a RawImage: the
            # minimap, a preview) is content whatever its size.
            if not (pr[0] <= cx <= pr[2] and pr[1] <= cy <= pr[3]) or (area(r) >= 0.5 * p_area and e.get("kind") != "RawImage"):
                continue
            boxes.append(inter(r, pr))
        if not boxes:
            continue  # a backdrop with nothing on it (a dimmer, a frame), not a panel holding content
        share, hole = coverage(pr, boxes, pad)
        if share < SPARSE_SHARE and hole >= HOLE_SHARE:
            out["sparse"].append({"path": p["path"], "rect": pr, "share": share, "hole": hole, "pieces": len(boxes)})

    for e in elements:
        if "Text" not in e.get("kind", "") or not e.get("text"):
            continue
        lines = e.get("lines")
        if lines is None:
            continue
        r = e.get("textRect") or e.get("visible") or e["rect"]
        if lines >= WALL_LINES and (r[2] - r[0]) < WALL_WIDTH * float(sw):
            out["walls"].append({"path": e["path"], "rect": r, "lines": lines, "font": e.get("fontSize"),
                                 "width_share": (r[2] - r[0]) / float(sw)})
    texts = [e for e in elements if "Text" in e.get("kind", "")]
    out["lines_measured"] = not texts or any("lines" in e for e in texts)
    return out


def nested_sparse(found: list[dict]) -> list[dict]:
    """A sparse panel inside another sparse panel says the same thing twice: keep the outermost."""
    keep = []
    for f in found:
        if not any(g is not f and g["path"] != f["path"] and f["path"].startswith(g["path"] + "/") for g in found):
            keep.append(f)
    return keep


def shape_lines(results: list[tuple[str, dict]]) -> tuple[list[str], int]:
    stretched = sum(len(r["stretched"]) for _, r in results)
    sparse = sum(len(nested_sparse(r["sparse"])) for _, r in results)
    walls = sum(len(r["walls"]) for _, r in results)
    unknown = sorted(set().union(*(r["unknown_sprites"] for _, r in results))) if results else []
    estimated = any(r["estimated"] for _, r in results)
    lines_measured = all(r["lines_measured"] for _, r in results)
    head = (f"Shape: {stretched} stretched, {sparse} mostly empty, {walls} wall(s) of text over {len(results)} census(es) "
            f"(ui_layout.py shape: a sprite drawn {STRETCH_RATIO:g}x off its own aspect, a window under "
            f"{SPARSE_SHARE * 100:.0f} % covered with one empty rectangle of {HOLE_SHARE * 100:.0f} % or more, {WALL_LINES}+ lines under {WALL_WIDTH * 100:.0f} % of the screen wide)")
    notes = []
    if estimated:
        notes.append("text glyphs estimated (no textRect in the census)")
    if not lines_measured:
        notes.append("walls of text not measured (no `lines` in the census)")
    if unknown:
        notes.append(f"{len(unknown)} sprite(s) of unknown size (give --repo or take the census with `spriteSize`)")
    if notes:
        head += "; " + "; ".join(notes)
    out = [head]
    for label, r in results:
        for s in r["stretched"]:
            out.append(f"  STRETCHED {label} {short(s['path'], 3)}: sprite {s['sprite']} {s['native'][0]}x{s['native'][1]} drawn "
                       f"{s['rect'][2] - s['rect'][0]:.0f}x{s['rect'][3] - s['rect'][1]:.0f} at {rect_text(s['rect'])}, "
                       f"{s['ratio']:.1f}x off its aspect ({s['type']})")
        for s in nested_sparse(r["sparse"]):
            out.append(f"  MOSTLY EMPTY {label} {short(s['path'], 3)}: {s['share'] * 100:.0f} % covered by {s['pieces']} "
                       f"piece(s), its largest empty rectangle {s['hole'] * 100:.0f} % of it, at {rect_text(s['rect'])}")
        for s in r["walls"]:
            out.append(f"  WALL OF TEXT {label} {short(s['path'], 3)}: {s['lines']} lines"
                       f"{' at ' + str(s['font']) + ' pt' if s['font'] else ''} in a box {s['width_share'] * 100:.0f} % of "
                       f"the screen wide at {rect_text(s['rect'])}")
    return out, stretched + sparse + walls


# ---------------------------------------------------------------------------------------------------------------
# commands


def run_check(args) -> int:
    before, after = load(args.before), load(args.after)
    spec = json.loads(Path(args.clusters).read_text(encoding="utf-8"))
    patterns = opened_patterns(spec)
    backdrops = backdrop_patterns(spec)
    failed = False

    ob = overlaps(before, args.block_depth, opened=patterns, backdrops=backdrops)
    oa = overlaps(after, args.block_depth, opened=patterns, backdrops=backdrops)
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

    wd = window_diff(before, after, spec, args.block_depth, args.tolerance)
    allowed = [v for v in window_overlaps(after, spec, args.block_depth) if v["status"] != "not allowed"]
    print(f"Window overlaps: {wd['after']} not allowed after, {wd['before']} before, {len(wd['new'])} new, {len(wd['kept'])} kept "
          f"between windows the change moved, {len(wd['standing'])} standing; {len(allowed)} allow-listed with the requester's "
          f"words (hud-clusters.json windowOverlaps) (ui_layout.py, whole screen, open windows against the HUD and each other)")
    for label, rows in (("NEW", wd["new"]), ("KEPT", wd["kept"]), ("STANDING", wd["standing"])):
        for v in rows[:15]:
            print(f"  {label}: {window_overlap_text(v, spec)}")
    for v in allowed[:15]:
        print(f"  ALLOWED: {window_overlap_text(v, spec)}")
    failed |= bool(wd["new"]) or bool(wd["kept"])

    problems = over["under"] + over["blocked"] + over["cut"]
    if args.closed:
        gone = restored(load(args.closed), over["covered"], args.tolerance) if over["covered"] else []
        problems += gone
        back = (f"{'no' if gone else 'yes'} ({sum(len(r) for r in over['covered'].values())} covered HUD element(s) checked in "
                f"{Path(args.closed).name})")
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

    cb = {covered_key(f) for f in covered_text(before, patterns)}
    ca = covered_text(after, patterns)
    new_cov = [f for f in ca if covered_key(f) not in cb]
    print(f"Covered text: {len(ca)} text(s) of opened screens under an opaque element after, {len(cb)} before, "
          f"{len(new_cov)} new (ui_layout.py, drawn glyph bounds: needs `textRect` in the census"
          + ("" if any(e.get("textRect") for e in after["elements"]) else "; NOT in this census: not measured") + ")")
    for label, rows in (("NEW", new_cov), ("STANDING", [f for f in ca if covered_key(f) in cb])):
        for f in rows[:15]:
            print(f"  {label}: {covered_text_line(f)}")
    failed |= bool(new_cov)

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


def run_options(args) -> int:
    spec = json.loads(Path(args.pins).read_text(encoding="utf-8"))
    options: dict[str, list[dict]] = {}
    for name, base, after in args.option:
        options.setdefault(name, []).append(option_check(load(base), load(after), args.named, spec, args.move_px))
    lines, out = option_lines(options, args.named, "ui_layout.py options")
    for line in lines:
        print(line)
    return 1 if out else 0


def run_overlaps(args) -> int:
    census = load(args.census)
    spec = json.loads(Path(args.clusters).read_text(encoding="utf-8"))
    pairs = overlaps(census, args.block_depth, opened=opened_patterns(spec), backdrops=backdrop_patterns(spec))
    print(f"{len(pairs)} overlapping block pairs between always-on HUD blocks (block depth {args.block_depth})")
    for (a, b), v in sorted(pairs.items(), key=lambda kv: -kv[1]["px"]):
        print(f"  {short(a)}  x  {short(b)}: {v['px']:.0f} px2, e.g. {short(v['example'][0], 2)} / {short(v['example'][1], 2)}")
    windows = window_overlaps(census, spec, args.block_depth)
    bad = [v for v in windows if v["status"] == "not allowed"]
    print(f"{len(bad)} window overlap(s) not allowed, {len(windows) - len(bad)} allow-listed (open windows against the HUD "
          f"blocks and each other, hud-clusters.json windowOverlaps)")
    for v in windows:
        print(f"  {'NOT ALLOWED' if v['status'] == 'not allowed' else 'ALLOWED'}: {window_overlap_text(v, spec)}")
    return 1 if bad else 0


def run_covered_text(args) -> int:
    spec = json.loads(Path(args.clusters).read_text(encoding="utf-8"))
    found = covered_text(load(args.census), opened_patterns(spec))
    print(f"{len(found)} text(s) of opened screens drawn under an opaque element above them")
    for f in found:
        print(f"  {covered_text_line(f)}")
    return 1 if found else 0


def run_shape(args) -> int:
    sprites = sprite_sizes(args.repo)
    censuses = [(f"{Path(c).parent.name}/{Path(c).name.split('.')[0]}", load(c)) for c in args.census]
    results = [(label, shape(census, sprites)) for label, census in censuses]
    # w1468: a stretched sprite whose every pixel is transparent draws nothing; with --repo, look and drop it.
    invisible = invisible_sprites(args.repo, {s["sprite"] for _, r in results for s in r["stretched"]})
    if invisible:
        results = [(label, shape(census, sprites, invisible=invisible)) for label, census in censuses]
    lines, flagged = shape_lines(results)
    if invisible:
        lines.append(f"  not judged: {', '.join(sorted(invisible))}: every pixel transparent (a hit area that draws nothing)")
    print("\n".join(lines))
    return 1 if flagged else 0


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
    w = sub.add_parser("options", help="every option still of a round against master: moves only what the person named (w1429)")
    w.add_argument("--option", nargs=3, action="append", required=True, metavar=("NAME", "MASTER", "OPTION"),
                   help="an option's name, master's census and the option's census on the same screen (repeat per screen)")
    w.add_argument("--named", action="append", default=[],
                   help="a path fragment of an element the person's words name (repeat); everything else stays put")
    w.add_argument("--pins", default=str(DEFAULT_PINS))
    w.add_argument("--move-px", type=float, default=4.0)
    o = sub.add_parser("overlaps", help="the overlapping block pairs of one census")
    o.add_argument("census")
    o.add_argument("--clusters", default=str(DEFAULT_CLUSTERS))
    t = sub.add_parser("covered-text", help="texts of opened screens drawn under an opaque element (w727)")
    t.add_argument("census")
    t.add_argument("--clusters", default=str(DEFAULT_CLUSTERS))
    s = sub.add_parser("shape", help="stretched sprites, mostly empty panels, walls of text: the 'Shape:' line (w1396)")
    s.add_argument("census", nargs="+")
    s.add_argument("--repo", help="the game repo: sprite sizes for a census without `spriteSize` (Deck tours before w1396)")
    k = sub.add_parser("clusters", help="cluster edges of one census or tour log")
    k.add_argument("census")
    k.add_argument("--clusters", default=str(DEFAULT_CLUSTERS))
    for p in (c, o):
        p.add_argument("--block-depth", type=int, default=2)
    args = ap.parse_args(argv)
    try:
        return {"check": run_check, "overlaps": run_overlaps, "clusters": run_clusters, "covered-text": run_covered_text, "moves": run_moves, "options": run_options, "pins": run_pins, "shape": run_shape}[args.cmd](args)
    except (ValueError, OSError, KeyError) as error:
        print(f"ui_layout: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
