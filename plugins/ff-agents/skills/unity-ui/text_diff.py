#!/usr/bin/env python3
"""text_diff: texts that no longer fit after a font-size change, from two layout censuses (w761).

The census (layout-census.md) records how each TextMesh Pro text lays out: font size, line count, overflow,
ellipsis, rendered and box width. This compares two censuses of the same screen (before and after a change) and
lists every text with the same string that

- takes more lines after than before (a label that broke onto a second line, "Component / s"),
- overflows its box or is cut with an ellipsis only after ("Rename fold..."),
- is wider than its box after, without wrapping, while it fitted before.

w761: the Deck text floor (#1282) raised about 300 texts from 14 to 15/16 pt on every screen; three desktop labels
stopped fitting and nobody had compared them. Look at each line this prints at full size: a flag is a finding until
you have looked.

    text_diff.py before.json after.json                 one pair
    text_diff.py --dir <folder> <before-prefix> <after-prefix>
                                                        every <before-prefix><state>.json with an
                                                        <after-prefix><state>.json beside it

Exit 1 when any text is flagged. Standard library only.
"""
import argparse
import collections
import glob
import json
import os
import sys


def texts(path):
    """path -> {element path: [text elements, in census order]} for the elements that carry layout fields."""
    with open(path, encoding="utf-8") as f:
        census = json.load(f)
    out = collections.defaultdict(list)
    for element in census.get("elements", []):
        if "lines" in element:
            out[element["path"]].append(element)
    return out


def wider_than_box(element):
    return element.get("wrap", "") == "NoWrap" and element.get("renderedW", 0) > element.get("rectW", 0) + 1


def compare(before, after):
    """[(path, text, [reasons])] for texts with the same string that fit before and not after."""
    b, a = texts(before), texts(after)
    flagged = []
    for path in sorted(set(b) & set(a)):
        for eb, ea in zip(b[path], a[path]):
            if (eb.get("text") or "") != (ea.get("text") or "") or not (ea.get("text") or "").strip():
                continue  # live text (counters) changed, or nothing to lay out
            reasons = []
            if ea["lines"] > eb["lines"] and eb["lines"] > 0:
                reasons.append(f"lines {eb['lines']} -> {ea['lines']}")
            if ea.get("overflowing") and not eb.get("overflowing"):
                reasons.append("overflows its box")
            if ea.get("truncated") and not eb.get("truncated"):
                reasons.append("cut off (ellipsis or truncate)")
            if wider_than_box(ea) and not wider_than_box(eb):
                reasons.append(f"wider than its box ({ea['renderedW']} > {ea['rectW']})")
            if reasons:
                size = f"{eb.get('fontSize')} -> {ea.get('fontSize')} pt"
                flagged.append((path, ea.get("text", ""), [size] + reasons))
    return flagged


def report(before, after, flagged):
    print(f"{os.path.basename(before)} -> {os.path.basename(after)}: {len(flagged)} text(s) no longer fit")
    for path, text, reasons in flagged:
        print(f"  {path[-100:]}  {text[:40]!r}: {'; '.join(reasons)}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--dir", help="a folder of censuses: compare <before-prefix>X.json with <after-prefix>X.json")
    args = parser.parse_args(argv)
    pairs = []
    if args.dir:
        if len(args.paths) != 2:
            parser.error("--dir needs <before-prefix> <after-prefix>")
        bp, ap = args.paths
        for before in sorted(glob.glob(os.path.join(args.dir, bp + "*.json"))):
            state = os.path.basename(before)[len(bp):]
            after = os.path.join(args.dir, ap + state)
            if os.path.exists(after):
                pairs.append((before, after))
    elif len(args.paths) == 2:
        pairs.append(tuple(args.paths))
    else:
        parser.error("give before.json after.json, or --dir <folder> <before-prefix> <after-prefix>")
    total = 0
    for before, after in pairs:
        flagged = compare(before, after)
        report(before, after, flagged)
        total += len(flagged)
    print(f"text_diff: {len(pairs)} pair(s), {total} text(s) no longer fit")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
