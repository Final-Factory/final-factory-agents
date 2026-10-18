#!/usr/bin/env python3
"""Check every skill's and role's frontmatter description reaches the listing whole (w1479).

Claude Code reads `description:` as YAML. In a plain (unquoted) scalar, " #" starts a comment, so everything after
it is dropped: ci-release's "... as Max in #dev-patch-notes. ... Never start it on your own initiative ..." reached
every session as "... as Max in", without its triggers or its guard. A description that holds " #" or ": " must be
quoted. Stdlib only (the runner image has no PyYAML).

    python3 scripts/check_frontmatter.py [--root <repo>]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def description(text: str) -> str | None:
    """The raw `description:` value of the frontmatter, or None when there is none."""
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None
    for line in m.group(1).splitlines():
        if line.startswith("description:"):
            return line[len("description:"):].strip()
    return None


def problem(value: str) -> str | None:
    """Why this plain scalar does not survive YAML whole, or None."""
    if not value or value[0] in "\"'|>":
        return None  # quoted or a block scalar: YAML keeps it whole
    if " #" in value:
        return "' #' starts a YAML comment: the rest of the description is dropped (quote it)"
    if ": " in value:
        return "': ' inside a plain scalar is a YAML error (quote it)"
    return None


def problems(root: Path) -> list[str]:
    out = []
    for p in sorted([*root.glob("plugins/*/skills/*/SKILL.md"), *root.glob("plugins/*/agents/*.md")]):
        d = description(p.read_text(encoding="utf-8"))
        if d is None:
            out.append(f"{p.relative_to(root)}: no description in its frontmatter")
            continue
        why = problem(d)
        if why:
            out.append(f"{p.relative_to(root)}: {why}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    found = problems(Path(ap.parse_args().root))
    for f in found:
        print(f"::error::{f}")
    print(f"{len(found)} problem(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
