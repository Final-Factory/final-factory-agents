#!/usr/bin/env python3
"""copy_check.py: flag public copy that may read as machine-written (w1926). Flags only, never a pass.

    python copy_check.py <file> [<file> ...]      # .md, .txt or .html
    python copy_check.py -                        # read stdin

Prints each flag with the lines it is about. It looks for what a word lint misses:

- rhythm: three sentences in a row of nearly the same length, sentence lengths that barely vary across the copy, or
  three or more paragraphs of nearly the same word count (the w1825 feature paragraphs were all 34 to 36 words);
- parallel openings: three of six sentences or list items in a row that start with the same two words
  (or, in prose, the same first word that is not a small one like "The");
- explainer lines: a sentence about the page or the list itself ("newest first", "below you'll find");
- stock phrases: taglines, marketing words and recycled constructions;
- em dashes, more than one per 120 words.

Exit 1 when there is a flag, 0 when there is none. No flags is NOT a pass: the w1825 copy that Ben called "LLM speak"
had passed a word lint clean, and the 2026-10-02 lines he sent back ("I make Final Factory", "build one space
factory") were awkward, not stock. A fresh critic that reads only the copy decides (evidence-gate,
checklists/public-copy.md).
"""
from __future__ import annotations

import html
import re
import statistics
import sys
from pathlib import Path

MIN_SENTENCES = 3       # a run this long of near-equal sentences is a flag
SENTENCE_SPREAD = 0.35  # max/min-1 of word counts at or below this counts as near-equal (8, 7, 6 words is 0.33)
MIN_VARIANCE_SENTENCES = 6
MIN_CV = 0.3            # stdev/mean of sentence length across the copy
MIN_PARAGRAPHS = 3
PARAGRAPH_WORDS = 15    # paragraphs shorter than this are labels, not prose
PARAGRAPH_SPREAD = 0.12
MIN_OPENINGS = 3
OPENING_WINDOW = 6     # sentences or list items in a row
EM_DASH_WORDS = 120

# Lines about the page or the list rather than about the game. Matched on a whole sentence, case aside.
EXPLAINER = [
    r"\bnewest first\b", r"\boldest first\b", r"\bin (?:reverse )?chronological order\b",
    r"\b(?:below|here) (?:you(?:'|’)ll|you will|you can) find\b",
    r"\bthis (?:page|section|site|list|post) (?:is|has|shows|covers|lists|collects|contains)\b",
    r"\bon this (?:page|site)\b", r"\bin one place\b", r"\bat a glance\b", r"\bkeep (?:reading|scrolling)\b",
    r"\bread on\b", r"\blisted (?:below|here)\b", r"\b(?:older|earlier|previous) (?:updates|posts|builds|versions) "
    r"(?:are|live|can be found)\b", r"\bevery (?:build|update|release|patch) since\b",
    r"\bfor more (?:details|information|info)\b", r"\blearn more\b",
]

# Taglines, marketing words and recycled constructions. Kept short on purpose: a long list turns into a pass/fail
# word lint, and that is the failure this tool exists for.
STOCK = [
    r"\bimmersive\b", r"\bseamless(?:ly)?\b", r"\bunleash\b", r"\bunlock (?:the|your|a whole)\b", r"\bempower", r"\bembark\b",
    r"\bjourney\b", r"\bdelve\b", r"\btapestry\b", r"\bvibrant\b", r"\bbreathtaking\b", r"\bgame[- ]?changer\b",
    r"\brevolutionar", r"\bnext level\b", r"\bdive (?:in|into)\b", r"\bwhether you(?:'|’)re\b",
    r"\beverything you need\b", r"\blook no further\b", r"\bthe ultimate\b", r"\bbuilt for\b", r"\bdesigned for\b",
    r"\bhandcrafted\b", r"\bstunning\b", r"\bepic\b", r"\bawait(?:s)?\b", r"\bthe possibilities are endless\b",
    r"\bnot (?:just|only) [^.]{1,40}\bbut\b", r"\bisn(?:'|’)t just\b", r"\bit(?:'|’)s not [^.]{1,30}, it(?:'|’)s\b",
    r"\bfrom [^.,]{1,25} to [^.,]{1,25}, ", r"\bmore than just\b", r"\bwelcome to\b", r"\bget ready\b",
    r"\bstay tuned\b", r"\bjoin (?:us|the community)\b",
]

SMALL_WORDS = {"the", "a", "an", "it", "its", "it's", "this", "that", "there", "these", "they", "you", "your", "i",
               "we", "and", "but", "so", "if", "in", "on", "at", "of", "to", "for", "with", "is", "are", "one"}

ABBREV = re.compile(r"\b(?:e\.g|i\.e|etc|vs|Mr|Ms|Dr|St|approx|no)\.$", re.I)
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.\-]*")


def html_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|nav|footer|svg|head)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<!--.*?-->", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n\n", raw)
    raw = re.sub(r"(?i)</?(p|div|li|ul|ol|h[1-6]|section|article|header|tr|td|th|blockquote|dd|dt)\b[^>]*>",
                 "\n\n", raw)
    return html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))


def blocks(text: str) -> list[tuple[int, str, str]]:
    """(line, kind, text) per paragraph, list item or heading; code, frontmatter and tables are skipped."""
    text = re.sub(r"\A---\n.*?\n---\n", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    out, cur, start, fence = [], [], 0, False

    def flush():
        if cur:
            out.append((start, "p", " ".join(cur)))
            cur.clear()

    for n, line in enumerate(text.splitlines(), 1):
        s = re.sub(r"^(?:>\s?)+", "", line.strip())
        if s.startswith("```") or s.startswith("~~~"):
            flush()
            fence = not fence
            continue
        if fence or s.startswith("|") or s.startswith("<!--"):
            flush()
            continue
        if not s:
            flush()
            continue
        m = re.match(r"(#{1,6})\s+(.*)", s)
        if m:
            flush()
            out.append((n, "h", m.group(2)))
            continue
        m = re.match(r"(?:[-*+]|\d+[.)])\s+(.*)", s)
        if m:
            flush()
            out.append((n, "li", m.group(1)))
            continue
        if not cur:
            start = n
        cur.append(s)
    flush()
    return [(n, k, re.sub(r"[*_`]|\[([^\]]*)\]\([^)]*\)", r"\1", t).strip()) for n, k, t in out if t.strip()]


def sentences(text: str) -> list[str]:
    parts, buf = [], ""
    for piece in re.split(r"(?<=[.!?])\s+", text):
        buf = f"{buf} {piece}".strip() if buf else piece
        if not ABBREV.search(buf):
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    return [p for p in parts if words(p)]


def words(text: str) -> list[str]:
    return WORD.findall(text)


def near_equal(counts: list[int], spread: float) -> bool:
    return min(counts) > 0 and max(counts) / min(counts) - 1 <= spread


def opening(text: str, n: int = 2) -> str:
    w = [x.lower().strip("'’") for x in words(text)[:n]]
    return " ".join(w) if len(w) == n else ""


def check_text(text: str, name: str = "<copy>") -> list[str]:
    flags = []
    bl = blocks(text)
    prose = [(n, t) for n, k, t in bl if k == "p"]

    # Rhythm inside a paragraph: three sentences in a row of nearly the same length.
    for n, t in prose:
        lens = [len(words(s)) for s in sentences(t)]
        if any(near_equal(lens[i:i + MIN_SENTENCES], SENTENCE_SPREAD)
               for i in range(len(lens) - MIN_SENTENCES + 1)):
            flags.append(f"{name}:{n}: rhythm: sentences of {', '.join(map(str, lens))} words, three in a row "
                         f"nearly the same; vary them or cut one")

    # Rhythm across the copy: sentence lengths that barely vary (human copy runs well above this).
    lens = [len(words(s)) for _, t in prose for s in sentences(t)]
    if len(lens) >= MIN_VARIANCE_SENTENCES:
        cv = statistics.pstdev(lens) / statistics.mean(lens)
        if cv < MIN_CV:
            flags.append(f"{name}: rhythm: {len(lens)} sentences, length varies by {cv:.2f} of the mean "
                         f"(under {MIN_CV}); the copy has one cadence")

    # Rhythm across paragraphs: near-equal word counts.
    long_paras = [(n, len(words(t))) for n, t in prose if len(words(t)) >= PARAGRAPH_WORDS]
    if len(long_paras) >= MIN_PARAGRAPHS:
        counts = [c for _, c in long_paras]
        mean = statistics.mean(counts)
        close = [(n, c) for n, c in long_paras if abs(c - mean) <= mean * PARAGRAPH_SPREAD]
        if len(close) >= MIN_PARAGRAPHS and len(close) >= len(long_paras) * 0.6:
            flags.append(f"{name}:{','.join(str(n) for n, _ in close)}: rhythm: {len(close)} of {len(long_paras)} "
                         f"paragraphs are {min(c for _, c in close)}-{max(c for _, c in close)} words; "
                         f"they read as one template")

    # Parallel openings: within any OPENING_WINDOW sentences or list items in a row, three that start alike: the same
    # two words, or in prose the same first word unless it is a small one ("The", "It"). A list item's first word is
    # left alone: "Fixed ..." down a patch-notes list is the form, not a tell.
    units = sorted([(n, s, True) for n, t in prose for s in sentences(t)] +
                   [(n, t, False) for n, k, t in bl if k == "li"], key=lambda u: u[0])
    keys = []
    for _, s, is_prose in units:
        ks = {opening(s)} - {""}
        first = opening(s, 1)
        if is_prose and first and first not in SMALL_WORDS:
            ks.add(first)
        keys.append(ks)
    flagged: set[str] = set()
    for i in range(len(units)):
        window = keys[i:i + OPENING_WINDOW]
        for key in sorted(keys[i], key=len, reverse=True):
            hits = [units[i + j][0] for j, ks in enumerate(window) if key in ks]
            if key not in flagged and len(hits) >= MIN_OPENINGS:
                flagged.add(key)
                flags.append(f"{name}:{','.join(map(str, hits))}: parallel openings: {len(hits)} close together "
                             f"start with \"{key} ...\"")
                break

    # Explainer lines and stock phrases, on every block (a heading can be a tagline).
    for n, k, t in bl:
        for s in sentences(t) or [t]:
            for pat in EXPLAINER:
                if re.search(pat, s, re.I):
                    flags.append(f"{name}:{n}: explainer: \"{s}\" is about the page, not the game; cut it unless a "
                                 f"reader would miss it")
                    break
            for pat in STOCK:
                m = re.search(pat, s, re.I)
                if m:
                    flags.append(f"{name}:{n}: stock phrase \"{m.group(0).strip(' ,')}\" in \"{s}\"")

    total = sum(len(words(t)) for _, _, t in bl)
    dashes = sum(t.count("—") for _, _, t in bl)
    if dashes and dashes * EM_DASH_WORDS > total:
        flags.append(f"{name}: em dashes: {dashes} in {total} words; use a full stop or a comma")
    return flags


def read(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    p = Path(arg)
    raw = p.read_bytes().decode("utf-8", errors="replace")
    return html_text(raw) if p.suffix.lower() in (".html", ".htm") else raw


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    flags = [f for a in args for f in check_text(read(a), "<stdin>" if a == "-" else a)]
    for f in flags:
        print(f)
    if flags:
        print(f"copy_check: {len(flags)} flag(s). Fix or justify each, then the fresh critic still reads the copy.")
        return 1
    print("copy_check: no flags. This is not a pass: a fresh critic reads only the copy and quotes every line that "
          "sounds machine-written (checklists/public-copy.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
