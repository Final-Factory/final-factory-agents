#!/usr/bin/env python3
"""Check the evidence-gate lessons (w741): each has its frontmatter, names its incident (a request or a PR), and is
indexed in the skill; and there are at most MAX of them, so a new lesson merges or retires one instead of piling up
(the skill said "past about twenty, merge or retire" and held 26 when this check came in).

    python3 scripts/check_lessons.py [--root <repo>]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MAX = 26
SKILL = Path("plugins/ff-agents/skills/evidence-gate")


def problems(root: Path) -> list[str]:
    skill = root / SKILL
    index = (skill / "SKILL.md").read_text(encoding="utf-8")
    lessons = sorted((skill / "lessons").glob("*.md"))
    out = []
    if len(lessons) > MAX:
        out.append(f"{len(lessons)} lessons, more than {MAX}: extend or merge one instead of adding "
                   f"(lessons/lessons-belong-in-the-harness-repo.md)")
    for p in lessons:
        text = p.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not m:
            out.append(f"{p.name}: no frontmatter")
            continue
        head = m.group(1)
        name = re.search(r"^name:\s*(\S+)", head, re.M)
        if not name or name.group(1) != p.stem:
            out.append(f"{p.name}: frontmatter name must be {p.stem}")
        for key in ("description", "date"):
            if not re.search(rf"^{key}:\s*\S", head, re.M):
                out.append(f"{p.name}: no {key} in the frontmatter")
        if not re.search(r"\bw\d{2,}\b|#\d{2,}|\b20\d\d-\d\d-\d\d\b", text[m.end():]):
            out.append(f"{p.name}: names no incident (a request like w704, a PR like #1263, or its date)")
        if f"lessons/{p.name}" not in index:
            out.append(f"{p.name}: not indexed in evidence-gate/SKILL.md")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    found = problems(Path(ap.parse_args(argv).root))
    for line in found:
        print(f"::error::{line}")
    print(f"lessons: {'FAIL' if found else 'OK'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
