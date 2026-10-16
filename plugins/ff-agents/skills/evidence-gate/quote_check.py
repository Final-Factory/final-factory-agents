#!/usr/bin/env python3
"""quote_check.py: is every quotation in a report word for word in the files it came from? (w1399)

    python quote_check.py <report.md> <source> [<source> ...]

A source is a file, or a folder whose .md, .txt, .json and .log files are read (the report itself is skipped). Every
double-quoted passage of three words or more in the report (straight or curly quotes; code spans are skipped) must be
in the sources: each piece between ellipses ("..." or "…") on its own, ignoring case, spacing, line breaks, quote
marks, apostrophes and markdown emphasis. A .json source is read as its string values. Prints each piece it cannot
find, with its line, and exits 1 when there is one. A miss is a misquote, or a phrase of your own in quote marks:
copy the source's words, or drop the quote marks.

Why (w1399): the draft proof had Ben asking for "making the add stop button look nicer". He never wrote it. His words
were "make the add stop button button stand out just a little more", close to the opposite. The same draft misquoted
two critic reports. Every quote had been typed from memory of the source, not copied from it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MIN_WORDS = 3
MAX_LEN = 600       # a "quotation" longer than this is two quotes paired across a paragraph
MIN_PIECE = 3       # characters; shorter pieces between ellipses carry nothing to check
SOURCE_TYPES = {".md", ".txt", ".json", ".log"}


def flat(text: str) -> str:
    """Case, spacing, quote marks, apostrophes, backslashes and markdown emphasis aside."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[*_`\"'\\]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def json_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in json_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in json_strings(v)]
    return []


def read_source(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        try:
            return "\n".join(json_strings(json.loads(raw)))
        except ValueError:
            pass
    return raw


def source_files(paths: list[str], report: Path) -> list[Path]:
    seen, out = {report.resolve()}, []
    for name in paths:
        p = Path(name)
        found = sorted(q for q in p.rglob("*") if q.is_file() and q.suffix.lower() in SOURCE_TYPES) if p.is_dir() else [p]
        for q in found:
            if q.resolve() not in seen:
                seen.add(q.resolve())
                out.append(q)
    return out


def quotations(report: str) -> list[tuple[int, str]]:
    """(line, text) of every double-quoted passage of MIN_WORDS words or more, paired within a paragraph."""
    text = report.replace("“", '"').replace("”", '"')
    out, line = [], 1
    for para in re.split(r"(\n\s*\n)", text):
        if not para.strip():
            line += para.count("\n")
            continue
        body = re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), para)  # code spans: commands and output
        for m in re.finditer(r'"([^"]{1,%d})"' % MAX_LEN, body):
            if len(m.group(1).split()) >= MIN_WORDS:
                out.append((line + body.count("\n", 0, m.start()), m.group(1)))
        line += para.count("\n")
    return out


def missing(quote: str, sources: str) -> list[str]:
    pieces = [p.strip() for p in re.split(r"\.\.\.|…", quote)]
    return [p for p in pieces if len(flat(p)) >= MIN_PIECE and flat(p) not in sources]


def check(report_path: Path, source_paths: list[str]) -> tuple[int, list[tuple[int, str, str]], int]:
    files = source_files(source_paths, report_path)
    sources = "\n".join(flat(read_source(f)) for f in files)
    quotes = quotations(report_path.read_bytes().decode("utf-8", errors="replace"))
    misses = [(line, q, piece) for line, q in quotes for piece in missing(q, sources)]
    return len(quotes), misses, len(files)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2 or args[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    report = Path(args[0])
    n, misses, n_files = check(report, args[1:])
    print(f"quote_check: {n} quotation(s) in {report.name}, {len(misses)} piece(s) not found word for word in "
          f"{n_files} source file(s)")
    for line, quote, piece in misses:
        shown = quote if len(quote) <= 160 else quote[:157] + "..."
        print(f"  line {line}: \"{piece}\"" + ("" if piece == quote.strip() else f"  (in \"{shown}\")"))
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
