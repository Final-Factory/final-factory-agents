#!/usr/bin/env python3
"""build_claim_check.py: does every "X is in build Y" claim in a report rest on a run of that build? (w1770)

    python build_claim_check.py <report.md> [--done]

A build claim is a sentence that names a build players run (a build number like "Build 111", a version like 1.0.0.112,
a Steam branch: development, pre-release, default, public, main, or the pre-1.0 / 1.0 build) and says something is, or
is not, in it ("has", "contains", "includes", "carries", "ships", "is in", "not in", "missing", "lacks", "reached").
Each one must carry its basis in the same sentence:

  * a run: "measured" (or "ran", "launched", "played") with what was opened, e.g. "measured: ran Build 111 from
    pre-release, opened Load: both tabs show"; or
  * a guess that names the build to run: "guess (from git): Build 111 contains #1760; to check, run Build 111 and open
    Load".

A claim resting on a grep, git (`merge-base`, ancestry, a branch's files) or a past report and no run is flagged, and so
is a claim with no basis at all. Prints each flagged sentence with its line and exits 1 when there is one.

--done adds the DONE lines of a player-facing fix: `Ships in: <Steam branch>, <build, version or "the next ... bump">`
and `pre-1.0: <cherry-pick needed (wNNN or PR) | #PR | not needed: why>`.

Why (w1770, 2026-10-22): #1760's Saves/Autosaves tabs were reported done on master without saying master is the 1.0
build; then an orchestrator told Ben the 1.0 development build "still has the tabs" from a code grep, and w1765 closed
with "pre-1.0 and Build 111 already contain the tabs and filter (#1760) ... checked with git". Ben's playtesters on
development had no tabs. Lesson: lessons/whats-in-a-players-build-is-checked-by-running-it.md.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BUILD = re.compile(
    r"\bbuild\s*#?\d{2,}\b"                                   # Build 111
    r"|\b\d+\.\d+\.\d+\.\d+\b"                                # 1.0.0.112
    r"|\b(?:development|pre-release|prerelease|default|public|main)\s+(?:steam\s+)?(?:branch|build)\b"
    r"|\bsteam\s+(?:development|pre-release|default|public|main)\b"
    r"|\bpre-1\.0\b(?:\s+(?:build|line|branch))?"
    r"|\b1\.0\s+(?:development\s+)?build\b"
    r"|\bon\s+(?:development|pre-release|default)\b", re.I)
PRESENCE = re.compile(
    r"\b(?:has|have|had|contains?|contained|includes?|included|carr(?:y|ies|ied)|ships?|shipped|reach(?:es|ed)?"
    r"|lacks?|lacked|missing|is in|are in|was in|were in|isn't in|aren't in|not in|already in|in it|in them)\b", re.I)
RUN = re.compile(r"\b(?:measured|ran|launched|played|run of|running)\b", re.I)
GUESS = re.compile(r"\bguess", re.I)
TO_RUN = re.compile(r"\brun\b|\blaunch\b|\bplay\b", re.I)
WEAK = re.compile(r"\bgit\b|\bgrep\b|merge-base|ancestor|ancestry|\bthe code\b|in the source|\bbranch's files\b", re.I)
SHIPS_IN = re.compile(r"^\W*ships in:\s*(.+)$", re.I | re.M)
PRE10 = re.compile(r"^\W*pre-1\.0:\s*(.+)$", re.I | re.M)
BRANCH = re.compile(r"\b(?:development|pre-release|default|public|main|pre-1\.0)\b", re.I)
WHICH_BUILD = re.compile(r"\bbuild\s*#?\d+|\b\d+\.\d+\.\d+\.\d+\b|\bbump\b|\bbuildid\b", re.I)
PRE10_ANSWER = re.compile(r"cherry-pick|#\d+|\bw\d{3,}\b|not needed|no cherry-pick", re.I)


def sentences(text: str) -> list[tuple[int, str]]:
    """(line, sentence) for each sentence outside code blocks and code spans; a sentence ends at '.', '!', '?' + space,
    a blank line, or a line break before a list marker or a 'Ships in:' / 'pre-1.0:' line."""
    out, line = [], 1
    text = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    for block in re.split(r"(\n\s*\n|\n(?=\s*(?:[-*+]|\d+\.)\s)|\n(?=\W*(?:ships in|pre-1\.0):))", text, flags=re.I):
        if not block.strip():
            line += block.count("\n")
            continue
        body = re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), block)
        start = 0
        for m in re.finditer(r"[.!?](?=\s|$)", body):
            out.append((line + body.count("\n", 0, start), body[start:m.end()].strip()))
            start = m.end()
        if body[start:].strip():
            out.append((line + body.count("\n", 0, start), body[start:].strip()))
        line += block.count("\n")
    return out


def claim_problem(sentence: str) -> str | None:
    if not (BUILD.search(sentence) and PRESENCE.search(sentence)):
        return None
    if re.match(r"\W*(?:ships in|pre-1\.0):", sentence, re.I):
        return None                                           # the --done lines say where it will ship, not what a run saw
    if GUESS.search(sentence):
        return None if TO_RUN.search(sentence) else "a guess that names no build to run"
    if RUN.search(sentence):
        return None
    if WEAK.search(sentence):
        return "rests on code or git, not a run of the build: run it and open the feature, or label it a guess naming the build to run"
    return "no basis: say what you ran and opened (measured), or label it a guess naming the build to run"


def done_problems(text: str) -> list[str]:
    out = []
    ships = SHIPS_IN.search(text)
    if not ships:
        out.append("no 'Ships in: <Steam branch>, <build or bump>' line: which build players run carries the fix")
    elif not (BRANCH.search(ships.group(1)) and WHICH_BUILD.search(ships.group(1))):
        out.append(f"'Ships in: {ships.group(1).strip()}' names no Steam branch and build (or the bump that will carry it)")
    pre = PRE10.search(text)
    if not pre:
        out.append("no 'pre-1.0: ...' line: does the pre-1.0 line need a cherry-pick")
    elif not PRE10_ANSWER.search(pre.group(1)):
        out.append(f"'pre-1.0: {pre.group(1).strip()}' says neither 'cherry-pick needed (...)', a PR, nor 'not needed: <why>'")
    return out


def check(text: str, done: bool = False) -> list[str]:
    out = [f"line {line}: {why}: \"{s if len(s) <= 200 else s[:197] + '...'}\""
           for line, s in sentences(text) if (why := claim_problem(s))]
    return out + (done_problems(text) if done else [])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report")
    ap.add_argument("--done", action="store_true", help="a player-facing fix's DONE: also needs 'Ships in:' and 'pre-1.0:'")
    args = ap.parse_args(argv)
    problems = check(Path(args.report).read_bytes().decode("utf-8", errors="replace"), args.done)
    print(f"build_claim_check: {len(problems)} problem(s) in {Path(args.report).name}")
    for p in problems:
        print(f"  {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
