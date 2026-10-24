#!/usr/bin/env python3
"""w1911 review: what does the change cover that the before left clear, and what does it resize?

usage: window_changes.py <before-layout.json> <after-layout.json> [...pairs]

Reads two layout censuses (the tour's *-layout.json) of the same screen and compares the windows (win_overlaps.py's list, the
HUD pieces) pair by pair: a pair whose overlap area is larger after than before (more than 200 px squared) is a NEW COVER, a
window whose height or width changed by more than 2 px is RESIZED, one that moved is MOVED. The orchestrator's review of the first w1911
pack (the Crafting window lifted over Station Core's title, Station Grid cut 45 px short) found these by eye; this finds them
by number. Run it on every before/after pair of a window-placement fix before a still goes to a person; exit 1 when anything
is a new cover or a resize. `ui_layout.py check`'s `Window overlaps:` line says the same of the pairs it knows; this one also
lists resized windows. Every line it prints is either asked for in the person's words or a fork put to them with stills.
"""
import json
import sys

WINDOWS = {
    "Crafting": "/InvAndCraft/UtilityPanel",
    "Inventory": "/InvAndCraft/InventoryPanel",
    "Player Inventory": "/GamePanels/MiniInventory",
    "Cargo Hold": "/CargoEntityPanel/MainPanel",
    "Station Grid": "/StationGridEntityPanel/MainPanel",
    "Station Core": "/StationCoreEntityPanel/MainPanel",
    "Dock column": "/GamePanels/StructuredDock",
}
HUD = {"Station Info": "/BuildInfoPanel/Parent", "Station strip": "/SelectionColumnStrip", "Skip button": "/SkipButton"}


def rect_of(elements, suffix, need_inside):
    best = None
    for e in elements:
        if e["path"].endswith(suffix) and e.get("visible"):
            best = e["rect"]
    if best is None:
        return None
    if need_inside and not any(suffix + "/" in e["path"] and e.get("visible") for e in elements):
        return None
    return best


def area(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def load(path):
    els = json.load(open(path))["elements"]
    out = {}
    for n, s in WINDOWS.items():
        r = rect_of(els, s, True)
        if r:
            out[n] = r
    for n, s in HUD.items():
        r = rect_of(els, s, False)
        if r:
            out[n] = r
    return out


def main():
    args = sys.argv[1:]
    if len(args) < 2 or len(args) % 2:
        sys.exit(__doc__)
    bad = 0
    for i in range(0, len(args), 2):
        before, after = load(args[i]), load(args[i + 1])
        lines = []
        for n in sorted(set(before) & set(after)):
            b, a = before[n], after[n]
            if abs((b[3] - b[1]) - (a[3] - a[1])) > 2 or abs((b[2] - b[0]) - (a[2] - a[0])) > 2:
                lines.append(f"RESIZED {n}: {b[2]-b[0]:.0f}x{b[3]-b[1]:.0f} -> {a[2]-a[0]:.0f}x{a[3]-a[1]:.0f} px")
            elif abs(b[0] - a[0]) > 2 or abs(b[1] - a[1]) > 2:
                lines.append(f"moved   {n}: x {b[0]:.0f} -> {a[0]:.0f}, y {b[1]:.0f} -> {a[1]:.0f}")
        names = sorted(set(before) & set(after))
        for x in range(len(names)):
            for y in range(x + 1, len(names)):
                p, q = names[x], names[y]
                if p in HUD and q in HUD:
                    continue
                ab, aa = area(before[p], before[q]), area(after[p], after[q])
                if aa > ab + 200:
                    lines.append(f"NEW COVER {p} / {q}: {ab:.0f} -> {aa:.0f} px squared")
                elif ab > aa + 200:
                    lines.append(f"less    {p} / {q}: {ab:.0f} -> {aa:.0f} px squared")
        flagged = any(l.startswith(("NEW", "RESIZED")) for l in lines)
        bad += flagged
        print(("FLAG " if flagged else "OK   ") + args[i + 1].split("/")[-1])
        for l in lines:
            print("     " + l)
    sys.exit(1 if bad else 0)


main()
