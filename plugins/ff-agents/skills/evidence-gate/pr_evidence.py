#!/usr/bin/env python3
"""pr_evidence: check a pull request's "## Evidence" section before it merges.

The evidence-gate skill (checklists/merge.md) says what the section holds. This script checks the
part a script can check: every claim has a basis and none is a guess, nothing is pending, a visual
change names a built player, the event's place in the clip and the intended look, a simulation
change names its tests, its determinism audit and its save compatibility, a UI change names its content, its
full-content and style checks, its per-still notes and a real-rate clip (checklists/ui.md), and a change to a shader
or material lists everything that uses it ("## Used by", from the game repo's scripts/asset_usage.py)
with a basis for each. It cannot tell whether anyone looked carefully. Standard library only; `gh` for everything that reads GitHub.

    pr_evidence.py --repo OWNER/NAME --pr N               check one pull request (exit 1 on FAIL)
    pr_evidence.py --repo OWNER/NAME --pr N --comment     the same, and post the verdict on it
    pr_evidence.py --body-file F [--files-file G]         the same, offline (a description and a file list)
    pr_evidence.py --repo OWNER/NAME --audit --since 2026-10-01 [--base develop]
                                                          merged pull requests: the verdict now, and
                                                          whether a PASS was posted before the merge
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MARKER = "evidence-gate:"
KINDS = ("visual", "ui", "simulation", "other")
BASES = ("MEASURED", "SOURCED", "DECIDED", "GUESS")
PENDING = re.compile(r"\b(pending|not yet|tbd|todo|to be (done|verified|reviewed|recorded|checked)|"
                     r"will be (reviewed|verified|recorded|checked))\b", re.IGNORECASE)
VIDEO = re.compile(r"\.(mp4|webm|mov|mkv)\b", re.IGNORECASE)
# Where in a clip the event is: "frames 118-190", "at 2.4 s", "0:12". A bare number range is not enough (dates, sizes).
PLACE = re.compile(r"\bframes?\b[^\n]{0,20}\d|\b\d+(\.\d+)?\s*(s|sec|secs|seconds)\b|\b\d+:\d{2}(\.\d+)?\b", re.IGNORECASE)
VISUAL_PATH = re.compile(r"/(Presentation|UI|VFX|Vfx|Shaders?)/|\.(shader|shadergraph|shadersubgraph|vfx|hlsl|cginc|mat|anim|"
                         r"controller|uxml|uss)$", re.IGNORECASE)
# A screen, panel or HUD element (w718, checklists/ui.md): checked with full content, against the classic look, in motion.
UI_PATH = re.compile(r"/UI/|\.(uxml|uss)$|^Assets/Scenes/[^/]+\.unity$")
# "1 fps sequences of the tours' shots" (#1251): stills played as a video cannot show flicker.
SLIDESHOW = re.compile(r"\b[1-9]\s*fps\b|\b(sequences?|slide ?shows?)\s+of\s+(the\s+)?(\w+'?s?\s+)?(shots|stills|screenshots)\b",
                       re.IGNORECASE)
# A shared look: changing one changes everything that draws with it (w438, lessons/check-who-uses-a-shared-asset.md).
SHARED_ASSET = re.compile(r"\.(shader|shadergraph|shadersubgraph|hlsl|cginc|mat)$", re.IGNORECASE)
USAGE_LINE = re.compile(r"asset-usage:\s*`?([^`\s]+?)`?\s+has\s+(\d+)\s+users?\b", re.IGNORECASE)
MEDIA = re.compile(r"\.(png|jpe?g|gif|mp4|webm|mov|mkv)\b|built player", re.IGNORECASE)
SIMULATION_PATH = re.compile(r"^Assets/Scripts/(FFSystems|FFComponents|FFCore|FFNetcode|FFConfiguration|FFTechnology)/"
                             r"|NetworkOperations")
NOT_GAME_CODE = re.compile(r"^Assets/(Tests|TestsSlow|Editor)/|^Assets/Scripts/PlayModeTests/|\.(meta|md)$")


def evidence_section(body: str, heading: str = "Evidence") -> str | None:
    """The text under the heading, up to the next heading of the same or a higher level."""
    lines = body.replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        found = re.match(rf"^(#{{1,6}})\s*{heading}\b", line.strip(), re.IGNORECASE)
        if found:
            level = len(found.group(1))
            rest = []
            for later in lines[i + 1:]:
                if re.match(rf"^#{{1,{level}}}\s", later):
                    break
                rest.append(later)
            return re.sub(r"<!--.*?-->", "", "\n".join(rest), flags=re.DOTALL)
    return None


def field(section: str, name: str) -> tuple[str, str] | None:
    """`Name (who): value` on a line of its own -> (who, value); None when the line is missing."""
    found = re.search(rf"^\s*{re.escape(name)}\s*(?:\(([^)]*)\))?\s*:\s*(.*)$", section, re.IGNORECASE | re.MULTILINE)
    return ((found.group(1) or "").strip(), found.group(2).strip()) if found else None


def claims(section: str) -> list[tuple[str, str]]:
    """Rows of the claims table as (claim, basis), without the header and the separator."""
    rows = []
    for line in section.split("\n"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else []
        if len(cells) < 2 or set(cells[0]) <= set("-: ") or cells[0].lower() == "claim":
            continue
        rows.append((cells[0], cells[1]))
    return rows


def kinds_of(section: str) -> list[str]:
    declared = field(section, "Kind")
    words = re.split(r"[,\s]+|\band\b", declared[1].lower()) if declared else []
    return [w for w in words if w in KINDS]


def has_basis(basis: str) -> bool:
    return basis.split(":")[0].strip() in ("MEASURED", "SOURCED", "DECIDED") and len(basis.split(":", 1)[-1].strip()) >= 10


def applies(files: list[str]) -> bool:
    """Game code or assets a player can meet. Docs, tools and tests of existing behaviour need no section."""
    return any(f.startswith("Assets/") and not NOT_GAME_CODE.search(f) for f in files)


def shared_assets(files: list[str] | None) -> list[str]:
    return [f for f in files or [] if f.startswith("Assets/") and SHARED_ASSET.search(f) and not NOT_GAME_CODE.search(f)]


def usage_tables(section: str) -> dict[str, tuple[int, dict[str, str]]]:
    """{asset: (the user count the tool printed, {user: basis})} from the "## Used by" section."""
    tables, rows = {}, None
    for line in section.split("\n"):
        found = USAGE_LINE.search(line)
        if found:
            rows = {}
            tables[found.group(1)] = (int(found.group(2)), rows)
            continue
        if rows is None or not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= set("-: ") or cells[0].lower() == "user":
            continue
        rows[re.sub(r":\d+$", "", cells[0].strip("`"))] = cells[1]
    return tables


def user_basis_problem(basis: str) -> str | None:
    label, _, how = basis.partition(":")
    label, how = label.strip().upper(), how.strip()
    if label not in ("TARGET", "MEASURED", "SOURCED"):
        return "the basis starts with TARGET, MEASURED or SOURCED" + (" (a guess is not a basis)" if label == "GUESS" else "")
    if len(how) < 10:
        return f"{label} needs what was looked at or the source, after a colon"
    if label == "MEASURED" and not MEDIA.search(how):
        return "MEASURED needs a built-player before/after of this user: name the stills or the clip"
    return None


def used_by_problems(body: str, files: list[str] | None) -> list[str]:
    """A changed shader or material: every user the tool found has a row and a basis (w438)."""
    changed = shared_assets(files)
    if not changed:
        return []
    section = evidence_section(body or "", "Used by")
    if section is None:
        return [f"this PR changes {', '.join(changed[:3])}{' and more' if len(changed) > 3 else ''} with no '## Used by' "
                f"section: run `python3 scripts/asset_usage.py --changed origin/develop --markdown` in the game repo, "
                f"paste it, and give every user a basis. More users than the target: give the target its own "
                f"shader or material instead (lessons/check-who-uses-a-shared-asset.md)"]
    tables, problems = usage_tables(section), []
    for asset in changed:
        if asset not in tables:
            problems.append(f"'## Used by' has no 'asset-usage: `{asset}` has N users' line: run the tool on it")
            continue
        count, rows = tables[asset]
        if len(rows) != count:
            problems.append(f"{asset}: the tool found {count} users and the table has {len(rows)} rows: paste its table whole")
        for user, basis in rows.items():
            why = user_basis_problem(basis)
            if why:
                problems.append(f"{asset}: {user}: {why}")
    return problems


def ui_problems(section: str) -> list[str]:
    """A screen, panel or HUD change: full content, the classic look, a still-by-still look and a real-rate clip (w718)."""
    problems = []
    wanted = {
        "Content": "the save or world the stills were taken in and what fills it (a late-game save: techs, recipes, "
                   "blueprints, fleets, objectives). An empty tab is not verified",
        "Full content": "whether every screen shows its whole grid, list, tree and preview (ui_check.py fill per pane)",
        "Style": "every touched panel's colour and alpha against a classic reference panel, as the 'Style:' line "
                 "ui_layout.py check prints (delta E and alpha per panel)",
        "Shots": "where the one-line-per-still notes against the requester's words are (ui_check.py shots)",
    }
    for name, what in wanted.items():
        line = field(section, name)
        if not line or len(line[1]) < 15:
            problems.append(f"UI change with no '{name}:' line: {what} (checklists/ui.md)")
    clips = field(section, "Clips")
    if clips and SLIDESHOW.search(clips[1]):
        problems.append(f"'Clips' is a slideshow ('{SLIDESHOW.search(clips[1]).group(0)}'): record each screen at 30 fps "
                        f"or more, idle and while hovering and selecting, so flicker can show (DeckTour `record`)")
    problems += layout_problems(section)
    flick = field(section, "Flicker")
    if not re.search(r"flicker", (clips[1] if clips else "") + (flick[1] if flick else ""), re.IGNORECASE):
        problems.append("UI change with no flicker result: run ui_check.py flicker on the clip's frames and say how "
                        "many regions it found, on the 'Clips:' line or a 'Flicker:' line")
    return problems


INTENDED = re.compile(r"\bintended\s*\(([^)]+)\)\s*:", re.IGNORECASE)


def layout_problems(section: str) -> list[str]:
    """The rest of the screen (w733): no new overlap, no anchored cluster drifting, every touched panel's colour and
    alpha within reach of the classic panel's. The lines are the ones `unity-ui/ui_layout.py check` prints; a
    difference the requester asked for passes only with `intended (who): "their words"` on its line."""
    problems = []
    overlaps = field(section, "Overlaps")
    if not overlaps:
        problems.append("UI change with no 'Overlaps:' line: run the layout census before and after with the whole HUD "
                        "showing and every slide-out open, and paste ui_layout.py check's line (unity-ui, layout-census.md)")
    else:
        new = re.search(r"(\d+)\s+new\b", overlaps[1])
        if not new:
            problems.append("'Overlaps:' does not say how many overlaps are new: paste ui_layout.py check's line")
        elif int(new.group(1)) > 0 and not INTENDED.search(overlaps[1]):
            problems.append(f"'Overlaps:' has {new.group(1)} new overlap(s) between HUD blocks: fix them, or quote the "
                            f"requester asking for it as intended (who): \"...\"")
        kept = re.search(r"(\d+)\s+kept\b", overlaps[1])
        if not kept:
            problems.append("'Overlaps:' does not say how many overlaps were kept between blocks the change moved: "
                            "paste the line ui_layout.py (ff-agents 1.22.1 or later) prints")
        elif int(kept.group(1)) > 0 and not INTENDED.search(overlaps[1]):
            problems.append(f"'Overlaps:' keeps {kept.group(1)} overlap(s) between blocks the change moved: they were "
                            f"there before, but you moved them and left them overlapping (w733: 7f75224fa left the "
                            f"Blueprint slide-out over the hotbar). Fix them, or quote the requester as intended (who): \"...\"")
    alignment = field(section, "Alignment")
    if not alignment:
        problems.append("UI change with no 'Alignment:' line: the anchored clusters' drift before and after "
                        "(ui_layout.py check, hud-clusters.json)")
    else:
        drift = re.search(r"max drift\s+(\d+(?:\.\d+)?)\s*px", alignment[1], re.IGNORECASE)
        if not drift:
            problems.append("'Alignment:' does not give the max drift in px: paste ui_layout.py check's line")
        elif float(drift.group(1)) > 2 and not INTENDED.search(alignment[1]):
            problems.append(f"'Alignment:' drifts {drift.group(1)} px (more than 2): an anchored HUD piece moved against "
                            f"its anchor. Fix it, or quote the requester as intended (who): \"...\"")
    style = field(section, "Style")
    if style and len(style[1]) >= 15:
        deltas = [float(d) for d in re.findall(r"delta E\s+(\d+(?:\.\d+)?)", style[1], re.IGNORECASE)]
        if not deltas or not re.search(r"\balpha\b", style[1], re.IGNORECASE):
            problems.append("'Style:' has no measured delta E and alpha: compare every touched panel with a classic "
                            "reference panel (ui_layout.py check --touched <window> --shot/--ref-shot) and paste its line. "
                            "A sentence like 'keeps its translucent look' is not a measurement (w733: #1272)")
        elif max(deltas) > 10 and not INTENDED.search(style[1]):
            problems.append(f"'Style:' has a panel at delta E {max(deltas):.1f} from the classic panel (more than 10): "
                            f"restore the game's panel look, or quote the requester as intended (who): \"...\"")
    return problems


def check(body: str, files: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Every reason the evidence is not ready (empty = PASS), and notes that do not fail it."""
    used_by = used_by_problems(body, files)
    section = evidence_section(body or "")
    if section is None:
        return (["no '## Evidence' section: say what each claim of this pull request rests on "
                 "(the evidence-gate skill, checklists/merge.md)"] + used_by, [])
    problems, notes = used_by, []
    kinds = kinds_of(section)
    if not kinds:
        problems.append("no 'Kind:' line (visual, simulation, both, or other)")

    rows = claims(section)
    if not rows:
        problems.append("no claims table: one row per claim the title and TL;DR make, with its basis")
    for claim, basis in rows:
        label = basis.split(":")[0].strip()
        if label == "GUESS":
            problems.append(f"'{claim}' rests on a guess: verify it, or move it to 'Not verified' and take it out of "
                            f"the title and TL;DR")
        elif label not in BASES:
            problems.append(f"'{claim}': the basis starts with MEASURED or SOURCED, then says how or where")
        elif not has_basis(basis):
            problems.append(f"'{claim}': {label} needs what was measured or the source, after a colon")

    open_lines = [l for l in section.split("\n") if not re.match(r"^\s*Not verified\s*:", l, re.IGNORECASE)]
    pending = PENDING.search("\n".join(open_lines))
    if pending:
        problems.append(f"something is still '{pending.group(0)}': no merge before the review is finished. Finish it, "
                        f"or move the claim it supports to 'Not verified'")
    unverified = field(section, "Not verified")
    if not unverified or not unverified[1]:
        problems.append("no 'Not verified:' line: name what you could not check, or write 'nothing'")

    ui = "ui" in kinds or ("visual" in kinds and any(UI_PATH.search(f) for f in files or [] if not NOT_GAME_CODE.search(f)))
    if ui and "visual" not in kinds:
        kinds.append("visual")

    if "visual" in kinds:
        look = field(section, "Intended look")
        if not look or len(look[1]) < 15:
            problems.append("no 'Intended look (who): ...' line: quote the person's own description, or write yours "
                            "and say it is yours")
        elif not look[0]:
            problems.append("'Intended look' does not say whose words they are: Intended look (Ben): ...")
        built = field(section, "Built player")
        if not built or not built[1].lower().startswith("yes"):
            problems.append("'Built player: yes' is missing: a visual change is verified in a built player through the "
                            "real event, not an editor rig. Until then it is changed, not fixed")
        clips = field(section, "Clips")
        if not clips or not VIDEO.search(clips[1]):
            problems.append("no 'Clips:' line naming a before and an after clip")
        elif not PLACE.search(clips[1]):
            problems.append("'Clips' does not say where the event is (frames or seconds): a clip that does not contain "
                            "the event proves nothing")
        looked = field(section, "Looked")
        if not looked or not looked[1].lower().startswith("yes"):
            problems.append("'Looked: yes, ...' is missing: someone steps through the event's frames against the "
                            "intended look. A measurement or a watch_video verdict is not a look")

    if ui:
        problems += ui_problems(section)

    if "simulation" in kinds:
        tests = field(section, "Tests")
        if not tests or not re.search(r"\d", tests[1]):
            problems.append("no 'Tests:' line with the suite and its counts")
        audit = field(section, "Determinism audit")
        if not audit or not audit[1]:
            problems.append("no 'Determinism audit:' line: the result and how many heartbeats were compared")
        elif audit[1].lower().startswith("not needed"):
            notes.append(f"determinism audit skipped: {audit[1]}")
            if len(audit[1]) < 30:
                problems.append("'Determinism audit: not needed' has to say why")
        elif not re.search(r"\d[\d,]*\s*(shared\s+)?heartbeats", audit[1], re.IGNORECASE):
            problems.append("'Determinism audit' does not give the number of heartbeats compared")
        save = field(section, "Save compatibility")
        if not save or not save[1]:
            problems.append("no 'Save compatibility:' line (the repo's hard rule)")

    if files:
        code = [f for f in files if not NOT_GAME_CODE.search(f)]
        visual = [f for f in code if VISUAL_PATH.search(f)]
        if visual and not {"visual", "ui"} & set(kinds) and not any("no visible change" in c.lower() and has_basis(b) for c, b in rows):
            problems.append(f"the changed files look visual ({', '.join(visual[:3])}): say Kind: visual (ui for a screen), or add a claim "
                            f"row 'No visible change' with its basis")
        simulation = [f for f in code if SIMULATION_PATH.search(f) and "/Presentation/" not in f]
        if simulation and "simulation" not in kinds and not any("no simulation" in c.lower() and has_basis(b) for c, b in rows):
            problems.append(f"simulation code changed ({', '.join(simulation[:3])}): say Kind: simulation, or add a "
                            f"claim row 'No simulation state changes' with its basis")
    return problems, notes


# ---------------------------------------------------------------------------------------------
# GitHub


def gh(*args: str) -> str:
    done = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if done.returncode:
        sys.exit(f"pr_evidence: gh {' '.join(args[:3])} failed: {done.stderr.strip()}")
    return done.stdout


PLUGIN_JSON = Path(__file__).resolve().parents[2] / ".claude-plugin" / "plugin.json"
RELEASED_JSON = "repos/Final-Factory/final-factory-agents/contents/plugins/ff-agents/.claude-plugin/plugin.json"


def own_version() -> str:
    try:
        return json.loads(PLUGIN_JSON.read_text(encoding="utf-8")).get("version", "unknown")
    except (OSError, ValueError):
        return "unknown"


def released_version() -> str | None:
    """The ff-agents version on the harness repo's master, or None when GitHub cannot be asked."""
    done = subprocess.run(["gh", "api", RELEASED_JSON, "-H", "Accept: application/vnd.github.raw"],
                          capture_output=True, text=True, encoding="utf-8")
    if done.returncode:
        return None
    try:
        return json.loads(done.stdout).get("version")
    except ValueError:
        return None


def version_tuple(v: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.+-]", v or "0"))


def stale_problem(mine: str, released: str | None) -> str | None:
    """w733: #1272 got a PASS at 22:47 from a copy older than the 1.21.0 that would have failed it (released 21:53)."""
    if released and mine != "unknown" and version_tuple(mine) < version_tuple(released):
        return (f"this pr_evidence.py is ff-agents {mine}, but {released} is released: its rules are older than the "
                f"team's. Update it (`claude plugin marketplace update final-factory-agents && claude plugin update "
                f"ff-agents@final-factory-agents`, or registerAgents.sh in your checkout) and run the newest copy, "
                f"found with `sort -V` (checklists/merge.md)")
    return None


def verdict_text(problems: list[str], notes: list[str], version: str | None = None) -> str:
    lines = [f"{MARKER} {'FAIL' if problems else 'PASS'} (pr_evidence.py, ff-agents {version or own_version()}, "
             f"the evidence-gate skill)"]
    lines += [f"- {p}" for p in problems] + [f"- note: {n}" for n in notes]
    return "\n".join(lines)


def passed_before_merge(pr: dict) -> bool:
    """A PASS verdict posted on the pull request before it merged."""
    merged = pr.get("mergedAt") or ""
    return any(MARKER + " PASS" in (c.get("body") or "") and (c.get("createdAt") or "") <= merged
               for c in pr.get("comments") or [])


def audit_rows(prs: list[dict]) -> list[dict]:
    rows = []
    for pr in prs:
        files = [f["path"] for f in pr.get("files") or []]
        if not applies(files):
            rows.append({"number": pr["number"], "title": pr["title"], "verdict": "n/a", "before_merge": "", "why": ""})
            continue
        problems, _ = check(pr.get("body") or "", files)
        rows.append({"number": pr["number"], "title": pr["title"], "verdict": "FAIL" if problems else "PASS",
                     "before_merge": "yes" if passed_before_merge(pr) else "no", "why": problems[0] if problems else ""})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="OWNER/NAME")
    ap.add_argument("--pr", type=int)
    ap.add_argument("--comment", action="store_true", help="post the verdict on the pull request")
    ap.add_argument("--body-file", help="check this description instead of asking GitHub")
    ap.add_argument("--files-file", help="with --body-file: the changed paths, one per line")
    ap.add_argument("--audit", action="store_true", help="list merged pull requests and their verdicts")
    ap.add_argument("--offline", action="store_true", help="skip the check that this copy is the released version")
    ap.add_argument("--since", help="--audit: merged on or after this date (YYYY-MM-DD)")
    ap.add_argument("--base", default="develop", help="--audit: the base branch (default develop)")
    ap.add_argument("--limit", type=int, default=100, help="--audit: at most this many pull requests")
    args = ap.parse_args(argv)

    if args.audit:
        if not (args.repo and args.since):
            ap.error("--audit needs --repo and --since")
        prs = json.loads(gh("pr", "list", "--repo", args.repo, "--state", "merged", "--base", args.base,
                            "--search", f"merged:>={args.since}", "--limit", str(args.limit),
                            "--json", "number,title,mergedAt,body,files,comments"))
        rows = audit_rows(prs)
        for r in rows:
            print(f"#{r['number']:<5} {r['verdict']:<4} {'PASS before merge: ' + r['before_merge'] if r['before_merge'] else '':<22} "
                  f"{r['title'][:70]}" + (f"\n       {r['why']}" if r["why"] else ""))
        counted = [r for r in rows if r["verdict"] != "n/a"]
        print(f"pr_evidence audit: {len(rows)} merged since {args.since}, {len(counted)} with game changes, "
              f"{sum(r['verdict'] == 'FAIL' for r in counted)} fail now, "
              f"{sum(r['before_merge'] == 'no' for r in counted)} merged without a PASS")
        return 0

    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
        files = Path(args.files_file).read_text(encoding="utf-8").splitlines() if args.files_file else None
    elif args.repo and args.pr:
        pr = json.loads(gh("pr", "view", str(args.pr), "--repo", args.repo, "--json", "body,files"))
        body, files = pr.get("body") or "", [f["path"] for f in pr.get("files") or []]
        if not applies(files):
            print("PASS: no game code or assets changed, so no Evidence section is needed")
            return 0
    else:
        ap.error("give --repo and --pr, or --body-file, or --audit")

    problems, notes = check(body, files)
    if not args.offline:
        released = released_version()
        stale = stale_problem(own_version(), released)
        if stale:
            problems.insert(0, stale)
        elif released is None:
            notes.append("could not ask GitHub for the released ff-agents version")
    text = verdict_text(problems, notes)
    print(text)
    if args.comment:
        if not (args.repo and args.pr):
            ap.error("--comment needs --repo and --pr")
        gh("pr", "comment", str(args.pr), "--repo", args.repo, "--body", text)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
