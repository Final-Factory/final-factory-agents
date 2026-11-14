#!/usr/bin/env python3
"""still_moves: what changed between two stills of one screen, outside the region the person named (w4153).

usage: still_moves.py <before.png> <after.png> [--named x0,y0,x1,y1 ...] [--tolerance 12] [--min-pixels 12] [--top 20]

A uGUI screen has a layout census, and `ui_layout.py options` reads from it what an option or a mock moved. A screen with no
census (a web page: an FF Factory portal screen, or a mock drawn into one) has only its pixels, so this compares them. Take
the before and the after still of the same screen at the same size, on the same data and a fixed clock; name each rectangle
the person's words ask to change (where the new panel goes), in the still's own pixels; every block of pixels that differs
anywhere else is listed as a box, largest first.

    Moves: none outside the named region            exit 0
    Moves: OUT, 2 blocks changed outside ...        exit 1, one CHANGED line per block
    Sizes differ                                    exit 2: take both stills at one size

A CHANGED block is an element that moved, grew, shrank, appeared or went: look at that box in both stills. Every line is
answered before a person sees the mock: it is the page's own state (the current row's mark, when the two stills are of two
routes), or the element is put back, or the move goes to the person as a question in words (evidence-gate checklists/ui.md,
item 32). It cannot tell a move from a repaint, so freeze what changes by itself (the clock, a caret, a video) and take both
stills from one run of the backend: many blocks of a few hundred pixels are texts that count time ("waiting 3 h"), taken in
two runs. w4153: two rounds of portal mocks went to the critic with the sidebar's block grown (the list under it 74 px
lower) and a panel the person had not named shrunk from 787 to 590 px; the critic found both by eye, and this finds them
first (on those stills at 1280 px: `CHANGED 8,445-271,568` and `CHANGED 14,578-263,751`, both gone in the last round).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ui_look  # noqa: E402  (load_still: Pillow when it is installed, its own PNG reader otherwise)

CELL = 8  # changed pixels are grouped by 8 px cells; cells that touch, corners included, are one block


def rect_arg(text: str) -> tuple[int, int, int, int]:
    try:
        x0, y0, x1, y1 = (int(v) for v in text.replace(" ", "").split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"a rectangle is x0,y0,x1,y1 in pixels, not {text!r}") from None
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def changed_pixels(before, after, named, tolerance: int):
    """Yields (x, y) of every pixel that differs by more than the tolerance on a channel, outside the named rectangles."""
    w = before.width
    for y in range(before.height):
        a = before.data[3 * y * w:3 * (y + 1) * w]
        b = after.data[3 * y * w:3 * (y + 1) * w]
        if a == b:
            continue
        spans = [(x0, x1) for x0, y0, x1, y1 in named if y0 <= y < y1]
        for x in range(w):
            i = 3 * x
            if a[i:i + 3] == b[i:i + 3]:
                continue
            if max(abs(a[i] - b[i]), abs(a[i + 1] - b[i + 1]), abs(a[i + 2] - b[i + 2])) <= tolerance:
                continue
            if any(x0 <= x < x1 for x0, x1 in spans):
                continue
            yield x, y


def blocks(pixels) -> list[list[int]]:
    """Groups changed pixels into blocks of touching cells: [x0, y0, x1, y1, pixels that differ], largest first."""
    cells: dict[tuple[int, int], list[int]] = {}
    for x, y in pixels:
        c = cells.setdefault((x // CELL, y // CELL), [x, y, x + 1, y + 1, 0])
        c[0], c[1], c[2], c[3], c[4] = min(c[0], x), min(c[1], y), max(c[2], x + 1), max(c[3], y + 1), c[4] + 1
    out, seen = [], set()
    for start in cells:
        if start in seen:
            continue
        seen.add(start)
        box, stack = list(cells[start]), [start]
        while stack:
            cx, cy = stack.pop()
            for n in ((nx, ny) for nx in (cx - 1, cx, cx + 1) for ny in (cy - 1, cy, cy + 1)):
                if n in cells and n not in seen:
                    seen.add(n)
                    stack.append(n)
                    c = cells[n]
                    box = [min(box[0], c[0]), min(box[1], c[1]), max(box[2], c[2]), max(box[3], c[3]), box[4] + c[4]]
        out.append(box)
    return sorted(out, key=lambda b: -b[4])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--named", type=rect_arg, action="append", default=[], metavar="x0,y0,x1,y1",
                    help="a rectangle the person's words ask to change, in the still's pixels; repeat for more")
    ap.add_argument("--tolerance", type=int, default=12, help="a channel may differ by this much (0-255) and count as the same")
    ap.add_argument("--min-pixels", type=int, default=12, help="a block with fewer changed pixels is left out")
    ap.add_argument("--top", type=int, default=20, help="how many blocks to list")
    args = ap.parse_args(argv)
    before, after = ui_look.load_still(args.before), ui_look.load_still(args.after)
    what = f"{Path(args.before).name} -> {Path(args.after).name}"
    if (before.width, before.height) != (after.width, after.height):
        print(f"Sizes differ: {before.width}x{before.height} against {after.width}x{after.height} ({what}). "
              "Take both stills at one size.")
        return 2
    found = [b for b in blocks(changed_pixels(before, after, args.named, args.tolerance)) if b[4] >= args.min_pixels]
    named = ", ".join(f"{x0},{y0}-{x1},{y1}" for x0, y0, x1, y1 in args.named) or "nothing: the stills must match"
    if not found:
        print(f"Moves: none outside the named region ({what}, {before.width}x{before.height}; named {named})")
        return 0
    print(f"Moves: OUT, {len(found)} block{'' if len(found) == 1 else 's'} changed outside the named region ({what}, "
          f"{before.width}x{before.height}; named {named})")
    for x0, y0, x1, y1, n in found[:args.top]:
        print(f"  CHANGED {x0},{y0}-{x1},{y1} ({x1 - x0}x{y1 - y0} px, {n} pixels differ)")
    if len(found) > args.top:
        print(f"  ... and {len(found) - args.top} smaller blocks")
    return 1


if __name__ == "__main__":
    sys.exit(main())
