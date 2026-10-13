#!/usr/bin/env python3
"""Check a release's draft patch notes against the game repo before they are committed or posted (w1264).

    python release_notes_check.py NOTES.md --repo <game clone> --range <previous release sha>..<release sha>
                                  [--accept PR]... [--lint PATH] [--verbose]
    python release_notes_check.py --help

Two kinds of line must stay out of player patch notes. Ben corrected both:

1. Dev workflow (2026-10-13, Build 101's notes, w1190): "please dont put that kind of specific workflow
   information in patch notes for users. like what the hell man? please remember this".
2. A change players cannot see (2026-10-13, Build 104, w1242): the draft listed "Mobile stations take their bots
   and barges with them" (w243, PR #1666), which ships behind the `inserters-ride-stations` feature toggle, off
   for every release player. Ben: "Mobile stations take their bots and barges with them / Isnt this behind a
   feature toggle?"

What it does:

* Dev workflow: runs the game repo's `scripts/release_notes_lint.py` as it is at the release commit (the one
  list of terms; a small built-in copy only when that file is missing there).
* Toggled-off changes: reads the toggles live at the release commit from
  `Assets/Scripts/FFCore/Features/FeatureToggles.cs` (a release player starts with EVERY toggle off, so a toggle
  that is still declared there hides what it gates, whatever its developer default), then for every pull request
  merged in the range reads the diff and finds the ones that
    - declare a toggle (an added `FeatureToggle` field), or
    - use one: `FeatureToggles.<Field>`, `IsOn(<Field>)`, the toggle's id in an item or research asset, a
      script or a scenario, or `ContentGates` / `FeatureArt` machinery, in code, assets or config (tests and
      docs do not count), or
    - say "feature toggle" / "-ffFeatures" in their commit messages.
  Each notes bullet is then matched to those pull requests (a `#1666` or `w243` it names, or enough words in
  common with the PR's commits, title and changed file names). A bullet that matches one FAILS: leave it out.

A toggle that a PR in the range REMOVES shipped the content, so its PRs do not count. A match is a prompt to
look, not a verdict: if the bullet is really about an ungated part of a mixed PR, reword it to say only that part
and pass `--accept <PR number>` for the PR (the report names who accepted it, so say why in the release report).
No file in the notes is edited by this script.

Exit 0: clean. Exit 1: a bullet matches a toggled-off PR, or the lint found a term. Exit 2: usage or git trouble.
Offline: it calls only `git` in the game clone (fetch first so the range exists).
"""
import argparse
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TOGGLES_PATH = "Assets/Scripts/FFCore/Features/FeatureToggles.cs"
LINT_PATH = "scripts/release_notes_lint.py"

# Paths whose changes say nothing about what a player sees.
_IGNORED = re.compile(
    r"(^|/)(Tests?|TestsSlow|PlayModeTests|Documentation|docs|specs|cicd|\.github|\.claude|\.codex)/"
    r"|(Tests?|Fixture|Fixtures)\.cs$|\.md$|\.meta$|(^|/)FeatureToggles\.cs$|(^|/)FeatureToggleLifecycleTest",
    re.I)
_GATE_MACHINERY = re.compile(r"\bContentGates\.|\bFeatureArt\.|\bFeatureArtVariant\b|\bFeatureArtSet\b|_featureToggle\b")
_SAYS_TOGGLE = re.compile(r"feature[\s-]*toggle|behind a toggle|-ffFeatures|FeatureToggles\.", re.I)

_STOP = set("""the and for with that this from into onto over under are was were has have had not no can may will
would could should their them they its it's you your our out off any all one two new now more most than then there
here when where which what while also only still just like each every both between after before again again about
after above below up down get gets got make makes made take takes took keeps keep kept now no longer instead
fixed fix fixes improved added adds add changed change changes updated update now""".split())


def git(repo, *args, check=True):
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if check and done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


# --- toggles -------------------------------------------------------------------------------------------------------

_TOGGLE_RX = re.compile(
    r"public\s+static\s+readonly\s+FeatureToggle\s+(\w+)\s*=\s*new\(\s*\"([^\"]+)\"\s*,\s*FeatureKind\.(\w+)(.*?)\)\s*;",
    re.S)


def _split_args(text):
    """Top-level comma-separated arguments of a C# call body, each as its joined string literals (or bare text)."""
    args, current, in_string, escaped = [], [], False, False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            else:
                current.append(char)
        elif char == '"':
            in_string = True
        elif char == ",":
            args.append("".join(current).strip())
            current = []
        elif not char.isspace() and char != "+":
            current.append(char)
    args.append("".join(current).strip())
    return args


def parse_toggles(text):
    """{id: {field, id, kind, description, dev_default, release}} for every toggle declared in FeatureToggles.cs text."""
    found = {}
    for match in _TOGGLE_RX.finditer(text):
        field, tid, kind, rest = match.groups()
        args = _split_args(rest)[1:]  # owner, created, removeBy, removalPlan, description, defaultOnInDev[, release]
        description = args[4] if len(args) > 4 else ""
        dev_default = len(args) > 5 and args[5] == "true"
        release = args[6] if len(args) > 6 and args[6] else None
        found[tid] = {"field": field, "id": tid, "kind": kind, "description": description,
                      "dev_default": dev_default, "release": release}
    return found


def toggles_at(repo, ref):
    return parse_toggles(git(repo, "show", f"{ref}:{TOGGLES_PATH}", check=False))


# --- pull requests in the range ------------------------------------------------------------------------------------

def merged_prs(repo, rng):
    """[{sha, number, title, base, tip}] first-parent entries of the range: merged PRs, and direct commits."""
    out = git(repo, "log", "--first-parent", "--format=%H%x1f%P%x1f%s%x1e", rng)
    prs = []
    for entry in out.split("\x1e"):
        entry = entry.strip()
        if not entry:
            continue
        sha, parents, subject = entry.split("\x1f")
        parents = parents.split()
        number = None
        found = re.search(r"Merge pull request #(\d+)", subject) or re.search(r"\(#(\d+)\)\s*$", subject)
        if found:
            number = int(found.group(1))
        if not parents:
            continue
        prs.append({"sha": sha, "number": number, "title": subject, "base": parents[0],
                    "tip": parents[1] if len(parents) > 1 else sha, "merge": len(parents) > 1})
    return prs


def pr_texts(repo, pr):
    """Commit subjects and bodies of the PR (its own commits for a merge, the commit itself otherwise)."""
    if pr["merge"]:
        return git(repo, "log", f"{pr['base']}..{pr['tip']}", "--format=%s%n%b", check=False) + "\n" + pr["title"]
    return git(repo, "log", "-1", "--format=%s%n%b", pr["sha"], check=False)


def added_lines(repo, pr):
    """{path: [added lines]} for the PR's diff against its first parent (no context, binary files skipped)."""
    out = git(repo, "diff", "-U0", "--no-color", "--no-ext-diff", pr["base"], pr["sha"], check=False)
    files, current = {}, None
    for line in out.splitlines():
        if line.startswith("+++ "):
            path = line[4:]
            current = path[2:] if path.startswith("b/") else None
            if current:
                files.setdefault(current, [])
        elif line.startswith("+") and current is not None:
            files[current].append(line[1:])
    return files


def analyse_pr(repo, pr, live, shipped_ids):
    """What the PR does with toggles that are live at the release commit: {id: why} and a flag for unknown gates."""
    files = added_lines(repo, pr)
    touched = {}
    by_field = {t["field"]: t for t in live.values()}

    if TOGGLES_PATH in files:
        before = parse_toggles(git(repo, "show", f"{pr['base']}:{TOGGLES_PATH}", check=False))
        after = parse_toggles(git(repo, "show", f"{pr['sha']}:{TOGGLES_PATH}", check=False))
        for tid in (set(after) - set(before)) & set(live):
            touched[tid] = "declares the toggle"

    machinery = False
    for path, lines in files.items():
        if _IGNORED.search(path):
            continue
        blob = "\n".join(lines)
        for field, toggle in by_field.items():
            if re.search(r"FeatureToggles\.%s\b|\bIsOn\(\s*%s\s*\)" % (field, field), blob):
                touched.setdefault(toggle["id"], f"uses it in {path}")
        for tid in live:
            if tid in touched:
                continue
            if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(tid), blob):
                touched[tid] = f"names it in {path}"
        if _GATE_MACHINERY.search(blob):
            machinery = True

    text = pr_texts(repo, pr)
    says = bool(_SAYS_TOGGLE.search(text))
    for tid in live:
        if tid not in touched and re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(tid), text):
            touched[tid] = "its commit messages name it"
    for tid in list(touched):
        if tid in shipped_ids:
            del touched[tid]
    return {"toggles": touched, "machinery": machinery, "says_toggle": says, "files": list(files)}


# --- matching notes bullets to pull requests -----------------------------------------------------------------------

def _stem(word):
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return word


def tokens(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)  # split CamelCase names (MobileStationUndockingSystem)
    words = re.findall(r"[A-Za-z][A-Za-z']+", text)
    return {_stem(w.lower().replace("'s", "")) for w in words if len(w) >= 3} - {_stem(s) for s in _STOP}


def bullets(notes_text):
    return [(n, line.strip()[2:].strip()) for n, line in enumerate(notes_text.splitlines(), 1)
            if re.match(r"\s*[*-]\s+\S", line)]


def pr_tokens(subjects, toggle_ids, live):
    """Words that say what a PR does: its commit subjects, and the one-line description and id of each toggle it
    sits behind (written to say what the toggle hides). Bodies and file names are left out: a big PR would match
    every bullet."""
    text = subjects + " " + " ".join(live[t]["description"] + " " + t.replace("-", " ") for t in toggle_ids)
    return tokens(text)


def match_pr(bullet, pr, rare):
    """The words a bullet shares with a PR that few other PRs in the range use ("barge", not "open"), and whether
    the bullet names the PR itself (#1666, w243)."""
    named = {a or b for a, b in re.findall(r"#(\d+)|(w\d{3,4})", bullet)}
    request_ids = {r.lower() for r in re.findall(r"w\d{3,4}", pr["title"] + " " + pr["text"], re.I)}
    cites = str(pr["number"]) in named or bool(named & request_ids)
    shared = tokens(bullet) & pr["tokens"] & rare
    return cites, shared


def is_match(shared, wanted):
    """Three rare words in common that are a good part of what the bullet says, or two that are most of it."""
    share = len(shared) / max(len(wanted), 1)
    return (len(shared) >= 3 and share >= 0.5) or (len(shared) >= 2 and share >= 0.6)


def rare_tokens(prs, total):
    """Words that appear in at most three PRs of the range: sharing "barge" says something, sharing "open" or "show"
    does not."""
    count = {}
    for pr in prs:
        for word in pr["tokens"]:
            count[word] = count.get(word, 0) + 1
    limit = 3
    return {word for word, n in count.items() if n <= limit}


# --- the lint -----------------------------------------------------------------------------------------------------

_FALLBACK_TERMS = [
    ("master", r"master"), ("develop", r"develop"), ("branch", r"branch(?:es|ing)?"), ("git", r"git(?:hub)?"),
    ("merge queue", r"merge\s+queue"), ("CI", r"ci(?:/cd)?"), ("pull request", r"pull\s+requests?"),
    ("PR", r"prs?"), ("PR/issue number", r"#\d+"), ("worker", r"workers?"), ("agent", r"agents?"),
    ("FF Factory", r"ff[\s-]*factory"), ("FFBox", r"ffbox"), ("workflow", r"workflows?"),
    ("request id", r"w\d{3,4}"),
]


def run_lint(repo, release_ref, notes_text, lint_path):
    """[(line, term, text)] from the game repo's own lint (at the release commit), else a built-in short list."""
    source = None
    if lint_path:
        source = Path(lint_path).read_text(encoding="utf-8")
    else:
        shown = git(repo, "show", f"{release_ref}:{LINT_PATH}", check=False)
        source = shown or None
    if source:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "release_notes_lint.py"
            path.write_text(source, encoding="utf-8")
            spec = importlib.util.spec_from_file_location("release_notes_lint_ref", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.lint_text(notes_text), "the game repo's scripts/release_notes_lint.py"
    hits = []
    allowed = re.compile(r"\(Live on the \w[\w -]* branch\)|Restart Steam to pick up the update on the \w[\w -]* branch\.?", re.I)
    for number, line in enumerate(notes_text.splitlines(), 1):
        scan = allowed.sub(" ", line)
        for label, pat in _FALLBACK_TERMS:
            if re.search(r"(?<![\w-])(?:%s)(?![\w-])" % pat, scan, re.I):
                hits.append((number, label, line.strip()))
    return hits, "the built-in short list (scripts/release_notes_lint.py is not at the release commit)"


# --- the check ----------------------------------------------------------------------------------------------------

def check(repo, rng, notes_text, accept=(), lint_path=None):
    """Returns (problems, gated, report lines). problems: [(kind, line number, text, detail)]."""
    release_ref = rng.split("..")[-1] or "HEAD"
    base_ref = rng.split("..")[0]
    live = toggles_at(repo, release_ref)
    if not live:
        raise RuntimeError(f"no toggles read from {TOGGLES_PATH} at {release_ref} (wrong clone or ref?)")
    previous = toggles_at(repo, base_ref)
    shipped_ids = set(previous) - set(live)  # removed in the range: the content ships

    prs = merged_prs(repo, rng)
    for pr in prs:
        pr.update(analyse_pr(repo, pr, live, shipped_ids))
        pr["text"] = pr_texts(repo, pr)
        subjects = git(repo, "log", f"{pr['base']}..{pr['tip']}", "--format=%s", check=False) if pr["merge"] else ""
        pr["tokens"] = pr_tokens(subjects + " " + pr["title"], pr["toggles"], live)
    rare = rare_tokens(prs, len(prs))
    gated = [pr for pr in prs if pr["toggles"] or (pr["says_toggle"] and pr["machinery"])]

    problems = []
    for number, bullet in bullets(notes_text):
        for pr in gated:
            if pr["number"] in accept:
                continue
            cites, shared = match_pr(bullet, pr, rare)
            if cites or is_match(shared, tokens(bullet)):
                ids = ", ".join(sorted(pr["toggles"])) or "an unnamed gate"
                why = "; ".join(f"{t}: {w}" for t, w in sorted(pr["toggles"].items())) or "gate machinery in its diff"
                branch = pr["title"].split(" from ")[-1]
                problems.append(("toggled-off", number, bullet,
                                 f"matches PR #{pr['number']} (branch {branch}), behind toggle {ids} ({why}); "
                                 f"words in common: {', '.join(sorted(shared)) or 'it names the PR'}"))

    lint_hits, lint_source = run_lint(repo, release_ref, notes_text, lint_path)
    for number, label, line in lint_hits:
        problems.append(("dev workflow", number, line, f"internal term '{label}'"))

    report = [f"toggles live at {release_ref}: {', '.join(sorted(live)) or 'none'}",
              f"dev-workflow terms checked with {lint_source}",
              f"pull requests in {rng}: {len(prs)}, behind a live toggle: {len(gated)}"]
    for pr in gated:
        num = f"#{pr['number']}" if pr["number"] else pr["sha"][:9]
        mark = " (accepted)" if pr["number"] in accept else ""
        report.append(f"  {num} {', '.join(sorted(pr['toggles'])) or 'gate machinery'}{mark}")
    return problems, gated, report


def main(argv):
    parser = argparse.ArgumentParser(description="Check draft patch notes for toggled-off changes and dev workflow.")
    parser.add_argument("notes", help="the draft notes file (Temp/release-notes-<version>.md)")
    parser.add_argument("--repo", default=".", help="the game repo clone (fetched)")
    parser.add_argument("--range", required=True, dest="rng",
                        help="<previous release sha>..<release sha or origin/master>: what ships")
    parser.add_argument("--accept", type=int, action="append", default=[], metavar="PR",
                        help="a toggled PR you checked: the bullet is about an ungated part")
    parser.add_argument("--lint", help="path of release_notes_lint.py when the release commit lacks it")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    try:
        text = Path(args.notes).read_text(encoding="utf-8")
        problems, gated, report = check(args.repo, args.rng, text, set(args.accept), args.lint)
    except (RuntimeError, OSError) as error:
        print(f"release_notes_check: {error}", file=sys.stderr)
        return 2
    for line in report:
        print(line)
    for kind, number, text_, detail in problems:
        print(f"{args.notes}:{number}: {kind}: {text_}\n    {detail}")
    if problems:
        print("\nPlayers must not read about a change that is off for them (a feature toggle) or about our "
              "workflow. Leave the line out (Ben, 2026-10-13, w1190 and w1242), or, for a mixed PR, reword it "
              "to the ungated part and pass --accept <PR>.")
        return 1
    print("release notes: no toggled-off change and no internal term")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main(sys.argv[1:]))
