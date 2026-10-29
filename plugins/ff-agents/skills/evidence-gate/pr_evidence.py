#!/usr/bin/env python3
"""pr_evidence: check a pull request's "## Evidence" section before it merges.

The evidence-gate skill (checklists/merge.md) says what the section holds. This script checks the
part a script can check: every claim has a basis and none is a guess, nothing is pending, a visual
change names a built player, the event's place in the clip and the intended look, a simulation
change names its tests, its determinism audit and its save compatibility, a UI change names its content, its
full-content and style checks, its per-still notes, a real-rate clip and every HUD element it moved at 1920x1080 and
1280x800, each asked for in the requester's words or justified (checklists/ui.md), and a change to a shader
or material lists everything that uses it ("## Used by", from the game repo's scripts/asset_usage.py)
with a basis for each, an enemy, combat or spawn change shows the game repo's balance stages before and after
("## Balance", checklists/balance.md, w1440), a new model or effect shows its 'Hero art:' line (concept stills and the pick,
the detail comparison with our best, how it differs from the existing weapons' and effects', what makes it distinctive,
the measured frame cost; checklists/visual.md 5e, w1497), a new or changed world model (an item, structure, ship,
projectile or pickup) names a built-player still of it beside its neighbours on its 'Scale:' line (checklists/visual.md
5k, w2204), a change to hide or visibility code counts what is still drawn where the hidden thing was on its
'Hidden census:' line (checklists/visual.md 5l, w2210), a claim that a visual defect is gone or an effect happens names
its 1:1 crop or slowed segment on 'Close-ups:' and, for occlusion, every surface on 'Surfaces:' (checklists/visual.md 5g,
w1567), and a Deck-facing change says 'Real Deck: verified ...' or 'not verified on a real Deck' (checklists/deck.md). It cannot tell whether anyone looked carefully. Standard library only; `gh` for everything that reads GitHub.

    pr_evidence.py --repo OWNER/NAME --pr N               check one pull request (exit 1 on FAIL)
    pr_evidence.py --repo OWNER/NAME --pr N --comment     the same, and post the verdict on it
    pr_evidence.py --body-file F [--files-file G]         the same, offline (a description and a file list; a line may be
                                                          `A<TAB>path` or `M<TAB>path<TAB>lines`, as git diff --name-status)
    pr_evidence.py --body-file F --repo R --pr N          a draft description against that PR's own changed files (w1684)
    ... [--brief B]                                       also: every 'Moved:' quote is in the request's brief (w826)
    pr_evidence.py --note N [--note-dir D] [--questions Q] a review note before publish_review: its close-ups (w1567),
                                                          each file beside it, the claims as questions for the critic
    pr_evidence.py --repo OWNER/NAME --audit --since 2026-10-01 [--base master]
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
# Effect art (w1332): a shader, material or VFX file that draws something in the world. Icons, sprites, UI, holograms
# and fog are indicators or screen art by design and are left to their own rules.
EFFECT_ART = re.compile(r"/(VFX|Vfx|Effects?)/|Vfx[^/]*\.(shader|shadergraph|hlsl|mat)$|\.(vfx|shader|shadergraph|"
                        r"shadersubgraph|mat)$|Particle", re.IGNORECASE)
NOT_EFFECT_ART = re.compile(r"/UI/|Icon|Sprite|Hologram|Font|/Fog|Outline", re.IGNORECASE)
NO_OVERLAY = re.compile(r"\b(no|without|none of|never)\b[^.;\n]{0,40}\b(rings?|circles?|halos?|indicators?|overlays?|ui[- ]like)\b",
                        re.IGNORECASE)
REFERENCE = re.compile(r"\b(compared|reference|beside|against|side by side|matches)\b", re.IGNORECASE)
ART_ASKED = re.compile(r"\(\s*[A-Z][\w ]*\)\s*:\s*\"", re.IGNORECASE)
VIDEO = re.compile(r"\.(mp4|webm|mov|mkv)\b", re.IGNORECASE)
# Where in a clip the event is: "frames 118-190", "at 2.4 s", "0:12". A bare number range is not enough (dates, sizes).
PLACE = re.compile(r"\bframes?\b[^\n]{0,20}\d|\b\d+(\.\d+)?\s*(s|sec|secs|seconds)\b|\b\d+:\d{2}(\.\d+)?\b", re.IGNORECASE)
VISUAL_PATH = re.compile(r"/(Presentation|UI|VFX|Vfx|Shaders?)/|\.(shader|shadergraph|shadersubgraph|vfx|hlsl|cginc|mat|anim|"
                         r"controller|uxml|uss)$", re.IGNORECASE)
# A screen, panel or HUD element (w718, checklists/ui.md): checked with full content, against the classic look, in motion.
UI_PATH = re.compile(r"/UI/|\.(uxml|uss)$|^Assets/Scenes/[^/]+\.unity$")
# A world-space mark drawn as a mesh, not a panel (w1181: the station route arrow, UI/World/StationRouteArrowView.cs, has
# no canvas, layout or HUD element, so the layout census reads nothing). A 'Not UI: <why>' line takes such a change off
# the UI rules, only when every UI-path file it touches is a script under UI/World/; a panel, prefab or scene never is.
NOT_UI_OK = re.compile(r"/UI/World/[^/]+\.cs(\.meta)?$")


def moved_to_ui_world(path: str, files: list[str] | None, changes: dict | None) -> bool:
    """A script the PR deletes from another UI path while it adds the same file name under UI/World/ is a move, not a
    panel change (w1767, #2292: UI/Circuits/CircuitWirePresenter.cs moved to UI/World/ and failed 'Not UI:'). Needs the
    change letters (gh or --files-file name-status); a plain file list keeps the old answer."""
    if (changes or {}).get(path, ("?", 0))[0] != "D" or not re.search(r"\.cs(\.meta)?$", path):
        return False
    name = path.rsplit("/", 1)[-1]
    return any(f.endswith("/UI/World/" + name) and NOT_UI_OK.search(f) and (changes or {}).get(f, ("?", 0))[0] in "AR"
               for f in files or [])
# "1 fps sequences of the tours' shots" (#1251): stills played as a video cannot show flicker.
SLIDESHOW = re.compile(r"\b[1-9]\s*fps\b|\b(sequences?|slide ?shows?)\s+of\s+(the\s+)?(\w+'?s?\s+)?(shots|stills|screenshots)\b",
                       re.IGNORECASE)
# A shared look: changing one changes everything that draws with it (w438, lessons/check-who-uses-a-shared-asset.md).
SHARED_ASSET = re.compile(r"\.(shader|shadergraph|shadersubgraph|hlsl|cginc|mat)$", re.IGNORECASE)
USAGE_LINE = re.compile(r"asset-usage:\s*`?([^`\s]+?)`?\s+has\s+(\d+)\s+users?\b", re.IGNORECASE)
# A change a Steam Deck player meets (w770, checklists/deck.md): a tour on a PC cannot show Steam's layout choice, the
# Proton first-frame resolution, the Steam client version or touch.
DECK_PATH = re.compile(r"^Assets/Scripts/Steam/|^Assets/StreamingAssets/SteamInput/|Settings/(Display|Player)SettingsController\.cs$|"
                       r"/Settings/DisplaySettings\.cs$|^cicd/.*\.vdf$|ControllerGlyphs")
DECK_WORDS = re.compile(r"\bDeck\b|Steam ?Input|SteamOS|Proton|gamescope")
MEDIA = re.compile(r"\.(png|jpe?g|gif|mp4|webm|mov|mkv)\b|built player", re.IGNORECASE)
SIMULATION_PATH = re.compile(r"^Assets/Scripts/(FFSystems|FFComponents|FFCore|FFNetcode|FFConfiguration|FFTechnology)/"
                             r"|NetworkOperations")
# Tutorial and objective cards (w918): an asset edit a player reads on the card, never a code path. PR #1408 added the
# Production tab's icon to a tip, passed as 'Kind: other' on editor play-mode stills, and was sent back for a built
# player. Such a change says 'Built player: yes ...' (a still of the card there is enough; no clip unless it moves).
OBJECTIVE_PATH = re.compile(r"^Assets/Resources/Objectives/.+\.asset$")
NOT_GAME_CODE = re.compile(r"^Assets/(Tests|TestsSlow|Editor)/|^Assets/Scripts/PlayModeTests/|\.(meta|md)$")
# Enemy, combat and spawn numbers (w1440, checklists/balance.md): they move the difficulty curve, so the PR shows the game
# repo's balance stages before and after (scripts/nightly/balance_lane.py compare). Ben, 2026-10-17: "you need to figure
# out how you can autonomously and intelligently figure out game balance for a smooth difficulty curve throughout the game".
BALANCE_PATH = re.compile(r"^Assets/Resources/GlobalConfig\.asset$|^Assets/Resources/WeaponConfig/|"
                          r"^Assets/Scripts/FFSystems/(EnemyAttacking|EnemyCamps)/|"
                          r"^Assets/Scripts/FFCore/GlobalConfig/CombatSettings\.cs$|"
                          r"^Assets/Resources/ItemConfig/[^/]*(Spawner|Cutter|Stinger|Trident|Razor|Urso|Turret|Railgun|Guardian)"
                          r"[^/]*\.asset$")
COMPARE_TABLE = re.compile(r"^\|\s*metric\s*\|\s*before\b", re.IGNORECASE | re.MULTILINE)
# A claim that a visual defect is gone or that an effect happens (w1567): each needs a 1:1 close-up still or a slowed
# clip segment of that moment on its 'Close-ups:' line, and an occlusion claim one per surface on 'Surfaces:'. w1470
# wrote "No z-fight with the Antimatter Nexus" and "ships spaghettify into the core"; Ben, twice: "still weird z fighting
# where the blakc hole isnt overtop of the terrain", "the units dont really spagettify". The words are guesses, checked
# on the w1470 body and the game PRs merged since 2026-10-01 (lessons/visual-fixes-are-verified-by-looking.md).
DEFECTS = (
    ("z-fight", r"\bz[- ]?fight\w*"),
    ("flicker", r"\bflicker\w*|\bshimmer\w*"),
    ("draws through", r"\b(clip(s|ped|ping)?|draws?|drew|drawn|poke[sd]?|poking|shows?|showing|bleed(s|ing)?)\s+through\b"),
    ("ghost", r"\bghost(s|ing|ed)?\b"),
    ("seam", r"\bseams?\b"),
    ("occlusion", r"\boccl(ude[sd]?|uding|usion)\b|\bz[- ]order\b|\bdepth[- ]sort\w*|\bdrawn\s+(over|under|behind|in front)"),
    ("pop", r"\bpop(s|ping)?\b"),
)
OCCLUSION_KEYS = ("z-fight", "draws through", "occlusion")
FIXED = re.compile(r"\b(no|not|never|without|gone|fixe[sd]|removed?|removes|no longer|free of|stable|clean|cured|"
                   r"eliminated|eliminates)\b", re.IGNORECASE)
EFFECTS = (
    ("spaghettify", r"\bspaghettif\w*|\bspag+et+if\w*"),
    ("stretch", r"\bstretch(es|ed|ing)?\s+(\w+\s+){0,2}?(into|toward|towards|along|out)\b|\bthin(s|ned|ning)?\s+out\b"),
    ("pulled in", r"\bpull(s|ed|ing)?\s+(\w+\s+){0,3}?(in|into|to|toward|towards)\b|\bsuck(s|ed|ing)?\b|\bdragged\b|"
                  r"\bfall(s|ing)?\s+(in|into)\b|\bfell\s+into\b"),
    ("lensing", r"\blens(es|ed|ing)\b|\bbent\s+(sky|light|stars)\b|\bbends?\s+(the\s+)?(sky|light|stars)\b"),
    ("wraps over", r"\bwrap(s|ped|ping)?\s+(over|around|in front)\b"),
    ("shatters", r"\bshatter\w*|\bcrumpl\w*|\bfold(s|ed|ing)?\s+(in|inward|inwards)\b"),
    # w1686: w1470 round 4 said "the Guardian stretches in about 4.0-5.6 s", "a slower swallow" and "seen as itself as
    # it stretches"; none matched a word above, so that round's close-ups were optional. Ben, 2026-10-21: "it just kind
    # of disappears".
    ("transition", r"\bswallow(s|ed|ing)?\b|\bdissolv\w*|\bmorph\w*|\bdisintegrat\w*|\bstretch(es|ed|ing)?\s+in\b|"
                   r"\b(stays?|stayed|remains?|remained|seen)\s+(lit\s+)?(as\s+)?(itself|themselves|whole|visible)\b|"
                   r"\bsmooth(ly)?\s+(\w+\s+)?(transition\w*|stretch\w*|shrink\w*|morph\w*|animation)\b|"
                   r"\b(one|a single)\s+(smooth|continuous|unbroken)\s+(animation|motion|stretch|transition)\b|"
                   r"\bshrinks?\s+(away|into\s+(the|its|a)\b)"),
)
# A transition (w1686): an object turning into its end state. Its close-up is every frame of the whole transition on the
# object (transition_strip.py), never a sheet every 0.2 or 0.5 s or a clip alone: at 60 fps a 0.2 s sheet shows 1 frame
# in 12, and the Guardian's vanish took about 0.1 s.
TRANSITION_KEYS = ("spaghettify", "stretch", "pulled in", "shatters", "transition")
STRIP = re.compile(r"every[-_ ]?[12]?[-_ ]?f(rames?)?\b|every[-_ ](other|2nd|second|two|2)[-_ ]frames?\b|every[-_ ]frame\b",
                   re.IGNORECASE)
COARSE = re.compile(r"every[-_ ]?(\d*\.\d+|\d+)[-_ ]?(s|sec|secs|seconds)\b|every[-_ ]?([3-9]|\d{2,})(th|rd)?[-_ ]?"
                    r"(f|frames?)\b", re.IGNORECASE)
# A second opinion that says the object vanishes (w1686: watch_video on w1470's round-4 take said "the Guardian
# disappears at once"; its author cleared it from a sheet every 0.2 s).
# Only beside a transition claim: in the 400 game PRs merged 2026-10-01..21, 9 explained a flagged snap (a teleport, a
# requested impact) and none of them claimed a transition. SNAP is watch_video's flag name, so only in capitals.
CRITIC = re.compile(r"second[- ]opinion|watch_video|\bcritic\b|gemini|blind (model )?review|model review|(?-i:\bSNAP\b)",
                    re.IGNORECASE)
VANISH = re.compile(r"\bdisappear\w*|\bvanish\w*|\bblinks?\s+out\b|\bpops?\s+(out|away|off)\b|\bat once\b|"
                    r"\bin (a|one) (single )?frame\b|(?-i:\bSNAP\b)", re.IGNORECASE)
STILL =re.compile(r"\.(png|jpe?g|webp)\b", re.IGNORECASE)
SLOWED = re.compile(r"\bslow\w*|\b0?\.\d+\s*x\b|\b1/\d+\s*x?\b|\bquarter[- ]speed|\bhalf[- ]speed|\bframe[- ]by[- ]frame\b",
                    re.IGNORECASE)
MEDIA_NAME = re.compile(r"[\w./\\-]+\.(?:png|jpe?g|webp|gif|mp4|webm|mov|mkv)\b", re.IGNORECASE)
# Lines that are not the worker's claims: the person's words, the gap list, the close-ups themselves, the artifact-hunt
# list (checklist 5b: "looked for ghosts ...: none" is a search, not a fixed defect).
NOT_A_CLAIM = re.compile(r"^\s*[-*]?\s*(Intended look|Not verified|Close-?ups|Surfaces|Looked for|Things I looked for|"
                         r"Not asked for|Shape|Flicker|Overlaps|Window overlaps|Alignment|Moved|Pinned|Colour|Eye|Critic|"
                         r"Covered text|Style|Content|Full content|Shots)\b", re.IGNORECASE)


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
                f"section: run `python3 scripts/asset_usage.py --changed origin/master --markdown` in the game repo, "
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


def ui_problems(section: str, brief: str | None = None) -> tuple[list[str], list[str]]:
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
    window, window_notes = window_overlap_problems(section, brief)
    problems += window
    covered, covered_notes = covered_text_problems(section)
    problems += covered
    moved, notes = moved_problems(section, brief)
    shape, shape_notes = shape_problems(section)
    problems += shape + eye_problems(section) + critic_problems(section)
    colour, colour_notes = colour_problems(section)
    problems += colour
    notes = window_notes + covered_notes + shape_notes + colour_notes + notes
    problems += moved + pinned_problems(section)
    flick = field(section, "Flicker")
    if not re.search(r"flicker", (clips[1] if clips else "") + (flick[1] if flick else ""), re.IGNORECASE):
        problems.append("UI change with no flicker result: run ui_check.py flicker on the clip's frames and say how "
                        "many regions it found, on the 'Clips:' line or a 'Flicker:' line")
    return problems, notes


def deck_problems(section: str, files: list[str] | None) -> tuple[list[str], list[str]]:
    """A Deck-facing change says 'verified' on a real Deck, with who and the versions, or 'not verified on a real Deck'."""
    touched = [f for f in files or [] if DECK_PATH.search(f) and not NOT_GAME_CODE.search(f)]
    if not touched and not DECK_WORDS.search(section):
        return [], []
    line = field(section, "Real Deck")
    if not line or not line[1]:
        return ([f"Deck-facing change with no 'Real Deck:' line: 'verified' (who, the Steam client and SteamOS versions, "
                 f"what they saw on the Deck) or 'not verified on a real Deck: <what stays open>'. A Deck tour on a PC "
                 f"cannot show Steam's layout choice, the Proton first-frame resolution, the Steam client or touch "
                 f"(checklists/deck.md; w684 -> w768, w767)"], [])
    who, value = line
    unverified = re.match(r"not verified on a real deck\b[\s:,-]*", value, re.IGNORECASE)
    if unverified:
        return [], [f"not verified on a real Deck: {value[unverified.end():][:160] or 'no reason given'}"]
    if not re.match(r"verified\b", value, re.IGNORECASE):
        return ([f"'Real Deck:' starts with 'verified' or 'not verified on a real Deck', not '{value[:30]}'"], [])
    problems = []
    text = f"{who} {value}"
    if not who and "(" not in value:
        problems.append("'Real Deck: verified' does not say who looked: Real Deck (Ben, date): verified ...")
    for what, pattern in (("Steam client", r"Steam client[^;,)\n]*\d"), ("SteamOS", r"SteamOS[^;,)\n]*\d")):
        if not re.search(pattern, text, re.IGNORECASE):
            problems.append(f"'Real Deck: verified' does not give the Deck's {what} version: an out-of-date Deck hid the "
                            f"layout in w768 (checklists/deck.md, step 0)")
    if len(value) < 60:
        problems.append("'Real Deck: verified' does not say what was looked at on the Deck")
    if re.search(r"\b(tour|simulat|emulat|scripted)", value, re.IGNORECASE) and not re.search(r"\breal\b|\bphoto", value, re.IGNORECASE):
        problems.append("'Real Deck: verified' reads like the Deck tour; a tour is a stand-in, not a real Deck")
    return problems, []


INTENDED = re.compile(r"\bintended\s*\(([^)]+)\)\s*:", re.IGNORECASE)


def opened_panel_problems(section: str, pairs: int) -> list[str]:
    """A panel the player opens on purpose may cover the HUD (Ben, w732 and w742: "the blueprint panel showing over
    objectives is fine since its a temporarily opened panel"), but it must be on top, take its clicks, stay on screen
    and give the HUD back when closed. These are the facts `ui_layout.py check` prints on its 'Opened panels:' line;
    there is no 'intended' way out of them."""
    line = field(section, "Opened panels")
    if not line:
        return [f"'Overlaps:' counts {pairs} opened-panel pair(s) over the HUD but there is no 'Opened panels:' line: "
                f"paste ui_layout.py check's line (panel on top, clickable, on screen, HUD back on close; "
                f"--closed <census taken after closing it>)"]
    text, problems = line[1], []
    for pattern, what in ((r"(\d+)\s+under the HUD", "drawn UNDER the HUD it covers"),
                          (r"(\d+)\s+not clickable", "leaving clicks to the HUD under it"),
                          (r"(\d+)\s+cut off", "cut off by the screen edge")):
        found = re.search(pattern, text, re.IGNORECASE)
        if not found:
            problems.append(f"'Opened panels:' does not say how many panels are {what}: paste ui_layout.py check's line")
        elif int(found.group(1)) > 0:
            problems.append(f"'Opened panels:' has {found.group(1)} panel(s) {what}: a panel the player opens may cover "
                            f"the HUD but must draw on top, be clickable and stay on screen (checklists/ui.md, item 11)")
    if re.search(r"NOT measured", text):
        problems.append("'Opened panels:' says the draw order was not measured: take the census in the editor "
                        "(layout-census.md records canvasOrder, depth and raycast), not from a tour log")
    if not re.search(r"restored on close:\s*yes", text, re.IGNORECASE):
        problems.append("'Opened panels:' does not show the HUD restored on close ('HUD restored on close: yes'): take a "
                        "census after closing the panel and pass it as --closed")
    return problems


# w826, w894: every element a UI change moved, as `ui_layout.py moves` lists it, asked for in the requester's words.
MOVE_ENTRY = re.compile(r"^\s*[-*]\s+(\d{3,4}\s*x\s*\d{3,4})(?:\s+(undocked|docked))?\s+(.+?):\s", re.IGNORECASE)
ASKED = re.compile(r"\basked\s*\(([^)]+)\)\s*:\s*[\"“](.{8,}?)[\"”]", re.IGNORECASE)
JUSTIFIED = re.compile(r"\bnot asked\s*:\s*justified\b", re.IGNORECASE)
REVERTED = re.compile(r"\bnot asked\s*:\s*reverted\b", re.IGNORECASE)
STATE = re.compile(r"\b(\d{3,4})\s*x\s*(\d{3,4})(?:\s+(undocked|docked))?", re.IGNORECASE)
# The screens every layout change is censused on (w894: the Deck's docked layout is where Station Info and the hover card
# were stacked top left, and no census looked at it).
REQUIRED_STATES = ("1920x1080", "1280x800 undocked", "1280x800 docked")
PINS = Path(__file__).resolve().parent.parent / "unity-ui" / "hud-pins.json"
STOP = ('Ben, 2026-10-10 (w895): "stop moving panels around that I don\'t ask you to move around. It\'s driving me crazy."')


def normalized(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def in_brief(quote: str, brief: str) -> bool:
    """Every piece of the quote between ellipses is in the brief, word for word (case and spacing aside), inside one of
    the brief's quotations: the person's own words, not the brief's around them (w826: "so nothing overlaps" and "the
    same on desktop" were the notes' words, and both moves Ben corrected came from them). A brief with no quotation
    marks counts whole (the person wrote it)."""
    text = normalized(brief)
    spoken = re.findall(r'"([^"]+)"', text) or [text]
    pieces = [normalized(p) for p in re.split(r"\.\.\.|…", quote)]
    return all(any(p in s for s in spoken) for p in pieces if len(p) >= 3)


def brief_in_body(body: str) -> str | None:
    """The requester's words the PR carries: its 'Brief (who): ...' lines and a '## Brief' section (w894)."""
    lines = [m.group(0) for m in re.finditer(r"^\s*Brief\s*(?:\([^)]*\))?\s*:.*$", body or "", re.IGNORECASE | re.MULTILINE)]
    section = evidence_section(body or "", "Brief")
    text = "\n".join(lines + ([section] if section else []))
    return text if text.strip() else None


def pins() -> list[dict]:
    try:
        return json.loads(PINS.read_text(encoding="utf-8")).get("pins", [])
    except (OSError, ValueError):
        return []


def states_of(text: str) -> set[str]:
    return {f"{m.group(1)}x{m.group(2)}" + (f" {m.group(3).lower()}" if m.group(3) else "") for m in STATE.finditer(text)}


def missing_states(text: str) -> list[str]:
    found = states_of(text)
    return [want for want in REQUIRED_STATES if not any(f == want or f.startswith(want + " ") for f in found)]


OUTER = re.compile(r"\(was (-?\d+),(-?\d+) (\d+)x(\d+), now (-?\d+),(-?\d+) (\d+)x(\d+)\)")
# The census calls an edge change over 4 px a move (ui_layout.py moves, move_px); the printed rects are rounded, so an
# edge computed from them is off by up to 1 px.
HELD_PX = 4 + 1


def resized_in_place(line: str, pin: dict) -> bool:
    """A pinned element that only got taller or shorter: its left and right edges kept (within the rounding), and the edge
    its pin holds against its anchor (the bottom, for an 'above' pin) within the census's move threshold. That is a
    resize, not a move: the pins are about where Ben put a panel (hud-pins.json: over the minimap, over the abilities),
    and every correction behind them was a panel taken somewhere else (w813, w894, w895). w1824: #2269's font fix made
    the hover card and Station Info 5 to 8 px shorter in ja/ko/zh/ru/uk, bottom edges and widths kept, which Ben had
    approved ("a few pixels shorter in those languages is fine"), and the gate asked him again because his words did not
    name each panel. The quote must still be the requester's words in the brief; any other change needs the name."""
    found = OUTER.search(line)
    if not found or pin.get("rule") != "above":
        return False
    x0, y0, w0, h0, x1, y1, w1, h1 = (int(v) for v in found.groups())
    if abs(h1 - h0) <= 1:
        return False  # the same size: a shift, which is a move
    return abs(x1 - x0) <= 1 and abs((x1 + w1) - (x0 + w0)) <= 1 and abs((y1 + h1) - (y0 + h0)) <= HELD_PX


def moved_problems(section: str, brief: str | None = None) -> tuple[list[str], list[str]]:
    """Nothing moved that the requester did not ask to move (w826; w894, Ben: "stop moving panels around that I don't ask
    you to move around"). The `Moved:` line is `ui_layout.py moves` at 1920x1080, 1280x800 undocked and 1280x800 docked;
    each list line names one element and carries `asked (who): "their words"`, found word for word inside the brief's
    quotations (--brief, or the PR's 'Brief (who):' lines), naming the element when it is pinned (hud-pins.json), unless
    the pinned element only changed height in place (resized_in_place, w1824). There
    is no other way to pass: `not asked: justified` was used for every unasked move it let through (#1397 moved Station
    Info and the hover card in the dock and passed). `not asked: reverted` does not count: re-take the after census."""
    lines = section.split("\n")
    head = next((i for i, l in enumerate(lines) if re.match(r"^\s*Moved\s*:", l, re.IGNORECASE)), None)
    if head is None:
        return (["UI change with no 'Moved:' line: census before and after at 1920x1080, 1280x800 (UI 0.8) and 1280x800 "
                 "docked, run ui_layout.py moves with the three pairs, paste its lines and mark every move asked (who): "
                 "\"their words\" from the brief, or put it back (checklists/ui.md, item 22; w826, w894)"], [])
    text = lines[head]
    problems = []
    count = re.search(r"Moved\s*:\s*(\d+)\s+element move", text, re.IGNORECASE)
    if not count:
        return (["'Moved:' does not say how many element moves the census found: paste ui_layout.py moves' line"], [])
    missing = missing_states(text)
    if missing:
        problems.append(f"'Moved:' does not cover {', '.join(missing)}: compare before and after on every standard screen "
                        f"and layout (ui_layout.py moves labels each pair; w894: the Deck's docked layout moved Station "
                        f"Info and the hover card to the top left and no census looked at it)")
    entries = []
    for line in lines[head + 1:]:
        if not line.strip():
            continue
        if not re.match(r"^\s*([-*]\s|\()", line):
            break
        found = MOVE_ENTRY.match(line)
        if found:
            state = re.sub(r"\s", "", found.group(1)).lower() + (f" {found.group(2).lower()}" if found.group(2) else "")
            entries.append((state, found.group(3).strip(), line))
    pinned = pins()
    accounted = 0
    for state, name, line in entries:
        bare = re.sub(r"\([^)]*\)", "", name)
        if "," in bare or re.search(r"\band\b", bare):
            problems.append(f"'Moved:' {state} {name}: one element per line, as ui_layout.py moves prints it (#1397 folded "
                            f"Station Info and the hover card into one line with the inventory)")
        asked = ASKED.search(line)
        if REVERTED.search(line) and not asked:
            continue
        if JUSTIFIED.search(line) and not asked:
            problems.append(f"'Moved:' {state} {name} is marked not asked: justified. A move nobody asked for is put back, "
                            f"then the after census is taken again; ask the requester first if it cannot be. {STOP}")
            continue
        if not asked:
            problems.append(f"'Moved:' {state} {name} is not marked: asked (who): \"their words\" when the requester asked "
                            f"for this element to move there, otherwise put it back and take the after census again")
            continue
        accounted += 1
        quote = asked.group(2)
        if not state.startswith("1280x800") and re.search(r"\bdeck\b", quote, re.IGNORECASE):
            problems.append(f"'Moved:' {state} {name}: the quote asks for the Deck (\"{quote[:60]}\"), not for this screen. "
                            f"A Deck request does not move the desktop HUD (w826)")
        if brief is None:
            problems.append(f"'Moved:' {state} {name}: no brief to check the quote against: put the requester's words in "
                            f"a 'Brief (who): \"...\"' line of the PR, or run with --brief <the brief from read_work> (w894: "
                            f"#1392 quoted words that are not in its brief)")
        elif not in_brief(quote, brief):
            problems.append(f"'Moved:' {state} {name}: the quote is not in the brief's quotations word for word: "
                            f"\"{quote[:80]}\". Only the requester's own words are a target (checklists/ui.md, item 1)")
        pin = next((pn for pn in pinned if re.search(rf"(^|/){re.escape(pn['element'])}\b", name)), None)
        if pin and not any(n in normalized(quote) for n in pin["names"]) and not resized_in_place(line, pin):
            problems.append(f"'Moved:' {state} {name} is pinned ({pin['name']}: {pin['where']}) and the quote does not name "
                            f"it ({' / '.join(pin['names'])}). A pinned element moves only when the requester says so by "
                            f"name, and then hud-pins.json changes with their words (only a height change that keeps its "
                            f"left, right and anchored edges is a resize the brief's words cover, w1824)")
    if accounted < int(count.group(1)):
        problems.append(f"'Moved:' counts {count.group(1)} move(s) but only {accounted} list line(s) are asked for: paste "
                        f"every line ui_layout.py moves prints and put back each one nobody asked for")
    return problems, []


def pinned_problems(section: str) -> list[str]:
    """The places Ben fixed himself (unity-ui hud-pins.json), checked on every screen and layout whatever the PR's parent
    showed (w894: the dock had stacked Station Info and the hover card top left since w772, so a before/after diff saw no
    move). The line is `ui_layout.py pins` over the after censuses. No way out in a PR: a pin changes only when the
    person asks, in a harness PR."""
    line = field(section, "Pinned")
    if not line:
        return ["UI change with no 'Pinned:' line: run ui_layout.py pins on the after censuses (1920x1080, 1280x800 "
                "undocked and docked, a station selected so Station Info and the hover card show) and paste its line "
                "(checklists/ui.md, item 22; w894)"]
    text, problems = line[1], []
    broken = re.search(r"(\d+)\s+broken", text)
    shown = re.search(r"(\d+)\s+not shown", text)
    if not broken or not shown:
        return ["'Pinned:' does not say how many pins are broken and not shown: paste ui_layout.py pins' line"]
    if int(broken.group(1)):
        problems.append(f"'Pinned:' has {broken.group(1)} broken pin(s): an element Ben placed himself is not where he put "
                        f"it (Station Info over the abilities, the hover card over the minimap, the Player Inventory off "
                        f"the left edge). Put it back. {STOP}")
    if int(shown.group(1)):
        problems.append(f"'Pinned:' has {shown.group(1)} pin(s) not shown: take the censuses with a station selected and "
                        f"the hover card up, so every pin is measured")
    missing = missing_states(text)
    if missing:
        problems.append(f"'Pinned:' does not cover {', '.join(missing)}: census every standard screen and layout")
    return problems


WINDOW_INTENDED = re.compile(r"\bintended\s*\(([^)]+)\)\s*:\s*[\"“](.{8,}?)[\"”]", re.IGNORECASE)


def window_overlap_problems(section: str, brief: str | None = None) -> tuple[list[str], list[str]]:
    """Window overlaps measured by the tool, not by eye (w981: on the Deck's classic layout the Station strip stood 11 px
    over the Player Inventory, `ui_layout.py overlaps` said 0 because it counted only always-on HUD blocks, and the w978
    worker measured the rects by hand). The `Window overlaps:` line is `ui_layout.py check`'s: every open window (the Player
    Inventory, a Cargo Hold, Station Core or Grid panel, the Station strip, a slide-out) against the other windows and the
    HUD, each pair allowed only by a quoted entry of hud-clusters.json `windowOverlaps`. A new or kept one fails; one that
    was there before and neither window moved is a note. The way out for an overlap the requester asked for is an
    `intended (who): "their words"` on the line, the words found word for word in the brief, or (for good) an allow-list
    entry in a harness PR."""
    line = field(section, "Window overlaps")
    if not line:
        return (["UI change with no 'Window overlaps:' line: run ui_layout.py check (ff-agents 1.26.25 or later) on the "
                 "before and after censuses with the windows in reach open (a Cargo Hold or Command Core selected, the "
                 "Player Inventory up) at 1280x800 classic, and paste its line: windows against the HUD and each other, "
                 "measured by the tool, not by eye (checklists/ui.md, item 11; w981)"], [])
    text, problems, notes = line[1], [], []
    counts = {}
    for name in ("new", "kept", "standing"):
        found = re.search(rf"(\d+)\s+{name}\b", text)
        if not found:
            return (["'Window overlaps:' does not say how many window overlaps are new, kept and standing: paste "
                     "ui_layout.py check's line"], [])
        counts[name] = int(found.group(1))
    bad = counts["new"] + counts["kept"]
    if bad:
        what = f"{counts['new']} new and {counts['kept']} kept"
        intended = WINDOW_INTENDED.search(text)
        if not intended:
            problems.append(f"'Window overlaps:' has {what} overlap(s) of an open window with the HUD or another window: "
                            f"fix them (the windows keep clear of each other), or quote the requester asking for it, "
                            f"intended (who): \"their words\"; the tool lists them as NEW / KEPT with both elements and "
                            f"the overlap rect (w981: the Station strip 11 px over the Player Inventory)")
        elif brief is None:
            problems.append("'Window overlaps:' is marked intended but there is no brief to check the quote against: run "
                            "with --brief <the brief from read_work>, or put the words in a 'Brief (who): \"...\"' line")
        elif not in_brief(intended.group(2), brief):
            problems.append(f"'Window overlaps:' intended quote is not in the brief's quotations word for word: "
                            f"\"{intended.group(2)[:80]}\"")
    if counts["standing"]:
        notes.append(f"{counts['standing']} window overlap(s) stand in the census before and after, between windows this "
                     f"change did not move: not this change's to fix, but say so in the report's first lines "
                     f"(ui_layout.py check prints them as STANDING; Ben: \"UI should be clean and flowy\")")
    return problems, notes


def covered_text_problems(section: str) -> tuple[list[str], list[str]]:
    """Text covered by its drawn bounds (w727: the Technology tab's "Excess Research 0.0" label ran half under the hub's tab
    bar and every check that compared RectTransform boxes read 0). The `Covered text:` line is `ui_layout.py check`'s: a text of
    an opened screen whose drawn glyphs lie under an opaque element above it. A new one fails; a census without `textRect`
    is a note ("not measured" is not "clean"). A missing line is a note until the Deck tour census carries `textRect` in every
    PR's tooling."""
    line = field(section, "Covered text")
    if not line:
        return [], ["no 'Covered text:' line: ui_layout.py check (ff-agents 1.26.39 or later) prints it from a census with "
                    "`textRect`; a label running under the hub's tab bar is invisible to every other check (w727)"]
    found = re.search(r"(\d+)\s+new\b", line[1])
    if not found:
        return (["'Covered text:' does not say how many covered texts are new: paste ui_layout.py check's line"], [])
    if re.search(r"not measured", line[1], re.IGNORECASE):
        return [], ["'Covered text:' was not measured (the census has no `textRect`): take it with the current census snippet "
                    "or the Deck tour's `setup:census:` step, and look at the hub tab stills at full size"]
    if int(found.group(1)):
        return ([f"'Covered text:' has {found.group(1)} new text(s) drawn under an opaque element of an opened screen: "
                 f"fix the layout so the text clears it (the tool lists each as NEW with the element over it; w727)"], [])
    return [], []


def shape_problems(section: str) -> tuple[list[str], list[str]]:
    """What a player calls obviously broken, judged on each after census (w1396; Ben, 2026-10-16, on stills a worker and an
    orchestrator had passed: "the light panel is really messed up obviously"). The `Shape:` line is `ui_layout.py shape`'s:
    a stretched sprite fails unless the requester asked for it (`intended (who): "..."`); a mostly empty window or a wall of
    text fails until the line says what was looked at and decided (`looked: ...`)."""
    line = field(section, "Shape")
    if not line:
        return (["UI change with no 'Shape:' line: run ui_layout.py shape over the after censuses (every size and layout) "
                 "and paste its line: stretched controls, mostly empty windows, walls of text (w1396: the Light Structure's "
                 "On/Off switch drawn as a 485x23 bar in the dock reached Ben)"], [])
    value = line[1]
    counts = {}
    for name, pattern in (("stretched", r"(\d+)\s+stretched"), ("mostly empty", r"(\d+)\s+mostly empty"),
                          ("walls", r"(\d+)\s+wall")):
        found = re.search(pattern, value, re.IGNORECASE)
        if not found:
            return ([f"'Shape:' does not say how many are {name}: paste ui_layout.py shape's line"], [])
        counts[name] = int(found.group(1))
    problems, notes = [], []
    if counts["stretched"] and not INTENDED.search(value):
        problems.append(f"'Shape:' has {counts['stretched']} stretched sprite(s): a control or icon drawn 2x or more off its "
                        f"own shape (the tool lists each STRETCHED with its sprite and drawn size). Give it its own size in "
                        f"the layout (a LayoutElement, preserveAspect, a fixed-size slot), as the game's other panels do")
    looked = re.search(r"\blooked\s*:\s*(.+)", value, re.IGNORECASE)
    soft = counts["mostly empty"] + counts["walls"]
    if soft and not (looked and len(looked.group(1).strip()) >= 20) and not INTENDED.search(value):
        problems.append(f"'Shape:' has {counts['mostly empty']} mostly empty window(s) and {counts['walls']} wall(s) of text: "
                        f"look at each at full size and either fix it (reuse the layout of the game's best panel of that kind) "
                        f"or say on the line what you saw and why it stands ('looked: ...')")
    elif soft and looked:
        notes.append(f"'Shape:' findings judged by eye: {looked.group(1).strip()[:160]}")
    if re.search(r"not measured", value, re.IGNORECASE):
        notes.append("'Shape:' measured only part of it (walls of text need `lines` in the census; the Deck tour's census has "
                     "them since w1396): look at every dialog's still for a dense block of text")
    return problems, notes


def eye_problems(section: str) -> list[str]:
    """The person's eye, before the person's (w1396). Every still is looked at full size and judged as a player would see it:
    anything stretched or squashed, a large empty area, overlapping labels, a dense text dump, anything obviously broken or
    poor. Ben, 2026-10-16: "looks terrible. you can do better" (w1296, round 3 of a dialog whose spacing alone had changed)
    and "the light panel is really messed up obviously" (w1386, stills described only as "same both sides")."""
    line = field(section, "Eye")
    if not line:
        return ["UI change with no 'Eye:' line: 'Eye: N stills looked at full size, M look broken or poor (<the per-still "
                "lines>)'. Judge each still as a player would, apart from the census: stretched or squashed controls, large "
                "empty areas, overlapping labels, text dumps (checklists/ui.md item 27; w1296, w1386)"]
    value = line[1]
    stills = re.search(r"(\d+)\s+stills?\b", value, re.IGNORECASE)
    poor = re.search(r"(\d+)\s+looks?\s+broken", value, re.IGNORECASE)
    if not stills or not poor:
        return ["'Eye:' says how many stills were looked at and how many look broken or poor: 'Eye: 12 stills looked at "
                "full size, 0 look broken or poor (proofs/shots.md)'"]
    if int(poor.group(1)) and not re.search(r"\bw\d{3,}\b", value):
        return [f"'Eye:' has {poor.group(1)} still(s) that look broken or poor: fix them before anyone sees them, or, when "
                f"it is not this change's (standing on master), name the request it was filed as (wNNN) on the line"]
    return []


def critic_problems(section: str) -> list[str]:
    """An independent look before the person's (w1399). Ben rejected three screens on 2026-10-16 whose pull requests all said
    "Looked: yes": the worker that built a screen sees what it meant. A fresh `ff-agents:ui-critic`, given only the pack
    `unity-ui/ui_look.py pack` builds (the stills, crops at the panel's own pixels, the game's reference panels, the person's
    words), grades every still; its broken or ugly findings are fixed, filed or answered with the person's words. The line:
    `Critic: <critic.md> (pack <id>, run R): N stills, M broken or ugly found, F fixed, 0 open, K minor`."""
    line = field(section, "Critic")
    if not line:
        return ["UI change with no 'Critic:' line: build the pack (unity-ui ui_look.py pack), run a fresh ff-agents:ui-critic "
                "on it, fix or answer every broken or ugly finding, and paste 'Critic: <critic.md> (pack <id>, run R): N "
                "stills, M broken or ugly found, F fixed, 0 open' (unity-ui critic.md; w1399: three screens passed their "
                "workers' own look and Ben rejected each at a glance)"]
    value = line[1]
    problems = []
    if not re.search(r"\bpack\s+[0-9a-f]{6,}", value, re.IGNORECASE):
        problems.append("'Critic:' names no pack id: the critic's input comes from ui_look.py pack, which prints it, so "
                        "the worker's own account of the change never reaches the critic")
    stills = re.search(r"(\d+)\s+stills?\b", value, re.IGNORECASE)
    found = re.search(r"(\d+)\s+broken or ugly", value, re.IGNORECASE)
    still_open = re.search(r"(\d+)\s+open\b", value, re.IGNORECASE)
    if not stills or not found or not still_open:
        problems.append("'Critic:' says how many stills it graded, how many broken or ugly findings it made and how many are "
                        "still open: 'Critic: proofs/critic.md (pack 3f2a91ab, run 2): 8 stills, 3 broken or ugly found, "
                        "3 fixed, 0 open, 2 minor'")
    elif int(still_open.group(1)) and not (re.search(r"\bw\d{3,}\b", value) or ANSWERED.search(value)):
        problems.append(f"'Critic:' has {still_open.group(1)} broken or ugly finding(s) open: fix each, file a standing one "
                        f"(wNNN on the line), or answer it with the person's words asking for exactly that "
                        f"(answered (who): \"...\"); the answer goes to the person with the stills")
    standing = re.search(r"(\d+)\s+standing", value, re.IGNORECASE)
    if standing and int(standing.group(1)) and not re.search(r"\bw\d{3,}\b", value):
        problems.append(f"'Critic:' lists {standing.group(1)} standing finding(s) (the before still shows them too): file "
                        f"them and name the request on the line (filed as wNNN); they are not this change's to fix")
    return problems


ANSWERED = re.compile(r"\banswered\s*\(([^)]+)\)\s*:\s*[\"“].{8,}?[\"”]", re.IGNORECASE)


def colour_problems(section: str) -> tuple[list[str], list[str]]:
    """How the colours look, measured on the stills (w1399; unity-ui `ui_look.py colour`): a large fill bright and saturated
    enough to outshout a dark panel (w1334's "+ Add stop": "the add stop bright blue is also painful on the eyes"), a
    selected row whose colour the controls inside it take on (w1334: "the active stop color is bleeding into a bunch of the
    panel's elements ... washing everything out"), text under 3:1 against what is behind it. A finding passes only with
    the requester's words asking for it (`intended (who): "..."`)."""
    line = field(section, "Colour") or field(section, "Color")
    if not line:
        return (["UI change with no 'Colour:' line: run unity-ui ui_look.py colour on every after still with its census and "
                 "paste its line: loud fills, state tints bleeding into controls, low-contrast text (w1399)"], [])
    value = line[1]
    counts = {}
    for name, pattern in (("loud", r"(\d+)\s+loud fill"), ("bleed", r"(\d+)\s+state tints?"),
                          ("contrast", r"(\d+)\s+low-contrast")):
        found = re.search(pattern, value, re.IGNORECASE)
        if not found:
            return ([f"'Colour:' does not say how many {name} findings it has: paste ui_look.py colour's line"], [])
        counts[name] = int(found.group(1))
    problems, notes = [], []
    if any(counts.values()) and not INTENDED.search(value):
        problems.append(f"'Colour:' has {counts['loud']} loud fill(s), {counts['bleed']} state tint(s) bleeding into "
                        f"controls and {counts['contrast']} low-contrast text(s): fix them (the game's quieter fill for a "
                        f"large area, a state shown by an accent edge or a lit number with the controls opaque, text that "
                        f"stands clear), or quote the requester asking for exactly that: intended (who): \"...\"")
    if re.search(r"not measured", value, re.IGNORECASE):
        notes.append("'Colour:' measured only part of it (state tints need a census with the list rows or --same pairs, "
                     "contrast a census): look at the selected rows and the small text at full size")
    return problems, notes


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
        opened = re.search(r"(\d+)\s+opened-panel", overlaps[1])
        if opened and int(opened.group(1)) > 0:
            problems += opened_panel_problems(section, int(opened.group(1)))
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


def art_language_problems(section: str, art_files: list[str]) -> list[str]:
    """w1241, w1332: Ben turned down a highlight drawn as "a world space UI indicator" and then rings round a comet:
    "again I don't like the unnatural circle effect that looks like UI. The vfx should be part of the game world in
    its appearance." An effect names what it was compared with and says it draws no ring, circle, halo or other
    UI-like overlay, or quotes the person asking for one (checklists/visual.md 5c)."""
    line = field(section, "Art language")
    where = ", ".join(art_files[:3])
    if not line or not line[1]:
        return [f"effect art changed ({where}) and no 'Art language:' line: name the reference it was compared with "
                "(the Railgun, a powered building, an existing effect) and say it draws no ring, circle, halo or other "
                "UI-like overlay, only in-world light, debris, sparks or the object's own material, or quote the "
                "person asking for an indicator (checklists/visual.md 5c; Ben, w1332: \"I don't like the unnatural "
                "circle effect that looks like UI\")"]
    text = line[1]
    if text.lower().startswith("n/a"):
        return [] if len(text) >= 25 else ["'Art language: n/a' has to say why (an indicator the person asked for, "
                                           "in their words)"]
    found = []
    if not REFERENCE.search(text):
        found.append("'Art language' does not name what the effect was compared with (a reference asset in the same "
                     "still)")
    if not NO_OVERLAY.search(text) and not ART_ASKED.search(text):
        found.append("'Art language' does not say the effect draws no ring, circle, halo or UI-like overlay, nor "
                     "quote the person asking for one: an effect is in-world light, debris, sparks or the object's own "
                     "material (w1241, w1332)")
    return found


def art_language_notes(section: str) -> list[str]:
    line = field(section, "Art language")
    return [f"art language: {line[1][:160]}"] if line and line[1] else []


def field_block(text: str, name: str) -> list[str]:
    """`Name: value` plus the indented or bulleted lines under it, one string per line (empty when missing)."""
    lines = text.replace("\r\n", "\n").split("\n")
    head = re.compile(rf"^\s*[-*]?\s*{re.escape(name)}\s*(?:\([^)]*\))?\s*:\s*(.*)$", re.IGNORECASE)
    for i, line in enumerate(lines):
        found = head.match(line)
        if not found:
            continue
        block = [found.group(1).strip()]
        for later in lines[i + 1:]:
            if later.strip() and (later.startswith((" ", "\t")) or re.match(r"^\s*[-*]\s", later)) \
                    and not re.match(r"^\s*[-*]?\s*[A-Z][\w -]{1,30}\s*(\([^)]*\))?\s*:", later):
                block.append(later.strip().lstrip("-* ").strip())
            else:
                break
        return [b for b in block if b]
    return []


def visual_claims(text: str) -> dict[str, list[str]]:
    """w1567: the sentences that say a visual defect is gone ("no z-fight") or that an effect happens ("ships
    spaghettify"), by kind of claim. The person's quoted words, comments and the gap and close-up lines are not claims."""
    text = re.sub(r"<!--.*?-->", "", text or "", flags=re.DOTALL)
    text = re.sub(r"\"[^\"]*\"|“[^”]*”", "\"\"", text)
    text = re.sub(r"\bpull\s+requests?\b", "PR", text, flags=re.IGNORECASE)
    found: dict[str, list[str]] = {}
    for line in text.split("\n"):
        if NOT_A_CLAIM.match(line) or not line.strip():
            continue
        for sentence in re.split(r"(?<=[.!?;])\s+", line):
            for key, pattern in DEFECTS:
                # ui_check.py flicker finds the regions that change (checklists/ui.md); a whole-frame mean does not
                # (w1470's "median of 2.1/255" passed a z-fight at the hole's edge).
                if key == "flicker" and "ui_check.py flicker" in sentence:
                    continue
                if re.search(pattern, sentence, re.IGNORECASE) and FIXED.search(sentence):
                    found.setdefault(key, []).append(sentence.strip(" |-*"))
            for key, pattern in EFFECTS:
                if re.search(pattern, sentence, re.IGNORECASE):
                    found.setdefault(key, []).append(sentence.strip(" |-*"))
    return found


def is_strip(entry: str) -> bool:
    """w1686: a 'Close-ups:' entry that is every frame (or every 2nd) of a transition, with its file and its seconds."""
    return bool(STRIP.search(entry) and not COARSE.search(entry) and PLACE.search(entry) and MEDIA_NAME.search(entry))


def vanish_flags(text: str) -> list[str]:
    """w1686: where a second opinion (watch_video, a critic, the blind review, a SNAP flag) says something vanishes or
    pops ("the Guardian disappears at once"), its quoted words or the sentence. The person's words and the close-up
    lines are left out."""
    text = re.sub(r"<!--.*?-->", "", text or "", flags=re.DOTALL)
    found = []
    for line in text.split("\n"):
        if NOT_A_CLAIM.match(line) or not CRITIC.search(line):
            continue
        for sentence in re.split(r"(?<=[.!?;])\s+", line):
            if VANISH.search(sentence):
                quoted = [a or b for a, b in re.findall(r"\"([^\"]*)\"|“([^”]*)”", sentence) if VANISH.search(a or b)]
                found.append(quoted[0] if quoted else sentence.strip(" |-*"))
    return found


def closeup_problems(text: str, folder: Path | None = None, claims_text: str | None = None) -> tuple[list[str], list[str]]:
    """w1567, Ben on w1470 twice, after the notes said the defect was gone and the effect was there: "its z fighting in
    the screenshot with the antimatter nexus or something, and its not pulling in the boss", then "the units dont
    really spagettify when they get pulled in and also theres still weird z fighting where the blakc hole isnt overtop
    of the terrain". Each such claim names, on the 'Close-ups:' line, a 1:1 crop or a slowed clip segment of that
    moment; an occlusion claim one per surface on the 'Surfaces:' line (terrain, structures, other effects).
    With a folder (a review note's), every file named there must be in it. Returns (problems, the critic's questions)."""
    claimed = visual_claims(text if claims_text is None else claims_text)
    entries = [e.strip() for line in field_block(text, "Close-ups") for e in line.split(";") if e.strip()]
    flagged = vanish_flags(text if claims_text is None else claims_text)
    flag_problem = None
    if flagged and any(k in TRANSITION_KEYS for k in claimed) and not any(is_strip(e) for e in entries):
        flag_problem = (f"a second opinion says the object vanishes ('{flagged[0][:100]}'): clear it only with every frame "
                        f"of that moment cropped on the object (transition_strip.py), named on the 'Close-ups:' line and "
                        f"asked of a fresh critic, never with your reading of a coarser sheet (checklists/visual.md 5h; "
                        f"w1470 round 4 cleared \"the Guardian disappears at once\" from a sheet every 0.2 s, and Ben saw "
                        f"it disappear)")
    if not claimed:
        return ([flag_problem] if flag_problem else []), []
    keys = dict(DEFECTS + EFFECTS)
    surfaces = [s.strip() for line in field_block(text, "Surfaces") for s in re.split(r",|;|\band\b", line) if s.strip()]
    questions = [f"From the close-ups, is this true: {s}? Say what you see at that moment, frame or crop by name."
                 for sentences in claimed.values() for s in sentences[:2]]
    questions += [f"From the every-frame strip, is the object's own model on screen in every frame until its end state "
                  f"({s[:80]})? Name the first frame where it is gone or replaced, and what the frame before it shows."
                  for k in claimed if k in TRANSITION_KEYS for s in claimed[k][:1]]
    # w1816: Ben on w1685, after a clip passed with "no vanish, pop, swap or jump": "i dont like that it suddenly jumps
    # to the center of the black hole and then also becomes that purple".
    if any(k in TRANSITION_KEYS for k in claimed):
        questions += ["From the every-frame strip, does the object move about as far each frame as in the frames around "
                      "it, all the way in, or does it jump (to the centre, across the hole) in one frame, or creep and then "
                      "lunge? Name the frame "
                      "and where it was in the frame before.",
                      "From the every-frame strip, does the object keep the colours it has in its first frame (its own "
                      "hull and lights), or does it turn another colour (purple, the hole's colour, a tint over it)? Name "
                      "the first frame and the colour."]
    problems = []
    said = ", ".join(f"'{claimed[k][0][:70]}'" for k in list(claimed)[:3])
    if not entries:
        return [f"the evidence claims a defect is gone or an effect happens ({said}) and has no 'Close-ups:' line: "
                f"for each claim, a 1:1 crop (png) of that exact moment or a slowed clip segment (0.25x, its seconds), "
                f"and for a transition (spaghettify, stretch, swallow) every frame of it (transition_strip.py), "
                f"e.g. 'Close-ups: z-fight: edge-over-terrain.png, edge-over-nexus.png; spaghettify: "
                f"pull-strip-2.00-3.10s-every1f.png' (checklists/visual.md 5g, 5h; Ben, w1470: \"the units dont really "
                f"spagettify when they get pulled in\")"] + ([flag_problem] if flag_problem else []), questions
    for key in claimed:
        family = OCCLUSION_KEYS if key in OCCLUSION_KEYS else (key,)
        mine = [e for e in entries if any(re.search(keys[k], e, re.IGNORECASE) or k.split()[0][:4].lower() in e.lower()
                                          for k in family)]
        if key in TRANSITION_KEYS:
            if not any(is_strip(e) for e in mine):
                coarse = next((e for e in mine if COARSE.search(e)), None)
                problems.append(f"'{claimed[key][0][:90]}' ({key}) is a transition: its close-up is every frame (every "
                                f"2nd at 50 fps or more) of the whole transition, cropped on the object, from the frame "
                                f"before it starts to its end state, with its seconds, e.g. '{key}: guardian-swallow-"
                                f"strip-3.40-6.20s-every1f.png' from transition_strip.py"
                                + (f"; '{coarse[:70]}' steps too coarsely (at 60 fps a 0.2 s sheet shows 1 frame in 12)"
                                   if coarse else "; a still or a slowed clip alone is not one")
                                + " (checklists/visual.md 5h; Ben, w1470, after a sheet every 0.2 s: \"the guardian "
                                  "especially doesn't really smoothly transition to the spaghetti state it just kind of "
                                  "disappears\")")
            continue
        shown = [e for e in mine if STILL.search(e) or (VIDEO.search(e) and SLOWED.search(e) and PLACE.search(e))]
        if not shown:
            problems.append(f"'{claimed[key][0][:90]}' ({key}) has no close-up on the 'Close-ups:' line: an entry naming "
                            f"'{key}' with a 1:1 crop (png, jpg) or a slowed clip segment (0.25x and its seconds)")
            continue
        if key in OCCLUSION_KEYS:
            if not surfaces:
                problems.append(f"'{key}' is claimed fixed and there is no 'Surfaces:' line: list every surface the "
                                f"effect overlaps (terrain, structures, hulls, other effects) and give each its close-up "
                                f"(Ben, w1470: \"theres still weird z fighting where the blakc hole isnt overtop of the "
                                f"terrain\", after a check against the Nexus ring alone)")
            for surface in surfaces:
                words = [w for w in re.findall(r"[a-z]{4,}", surface.lower()) if w not in ("other", "over", "with")]
                if words and not any(any(w in e.lower() for w in words) and MEDIA_NAME.search(e) for e in shown):
                    problems.append(f"'{key}' over '{surface}' has no close-up: name the surface in its entry "
                                    f"('{key} over {surface}: <crop>.png')")
    if flag_problem:
        problems.append(flag_problem)
    if folder is not None:
        for e in entries:
            for name in MEDIA_NAME.findall(e):
                if not (folder / name).exists() and not (folder / Path(name).name).exists():
                    problems.append(f"'Close-ups:' names {name}, which is not in {folder}")
    return problems, questions


# ---------------------------------------------------------------------------------------------
# Hero art (w1497): new models and VFX are creative, detailed and different, and the PR shows it.
#
# Ben corrected generic, low-quality new art three times on 2026-10-18: the Singularity Lance VFX (w1470, "just like a
# black disc sitting on top of the purple accretion disc ... be creative with this"), the Urso Ballista (w1466, "so
# explicitly like a bow and arrow ... the model itself is not detailed enough ... it looks samey with all the other
# effects, especially the railgun effeect") and the Station Shield Battery effect (w1475, "make it more subtle and tighter
# to the ship itself ... be creative and be more high quality (but performant)"). The rule is in
# lessons/visual-fixes-are-verified-by-looking.md and checklists/visual.md 5e; this is the part a script can check.
#
# What counts (guesses, calibrated on the game repo's merged pull requests of 2026-10-01..18, see HeroArtTest):
#  - a model file (fbx, obj, blend, glb, gltf, dae) that is added, or whose status is unknown (a plain file list);
#    an edited model is a re-export or a fix and is not counted;
#  - effect art (EFFECT_ART: VFX or Effects folders, .vfx, .shader, .shadergraph, .mat, Particle) that is added, or
#    edited by HERO_EDIT_LINES changed lines or more (a small material tweak or a bug fix stays under it);
#  - not counted: third-party asset packs, tests and editor code, UI, icons, sprites, holograms, fog, outlines, textures.
HERO_MODEL = re.compile(r"\.(fbx|obj|blend|glb|gltf|dae)$", re.IGNORECASE)
THIRD_PARTY = re.compile(r"^Assets/(ExternalAssets|GabrielAguiarProductions|SineVFX|Vefects|Plugins|Tayx|EasyIconMaker|"
                         r"Graph And Chart|UiRoundedCorners|TextMesh Pro|Samples)\b")
HERO_EDIT_LINES = 40
HERO_ART_LABELS = re.compile(r"\b(concepts?(?:\s+stills?)?|detail(?:\s+comparison)?|differs?(?:\s+from)?|"
                             r"distinct(?:\s+because)?|(?:frame\s+)?cost)\s*:", re.IGNORECASE)
HERO_PLACEHOLDER = re.compile(r"<[^>]*>|\b(tbd|todo|pending|n/?a|xxx|lorem|placeholder|fill in|to come)\b", re.IGNORECASE)
HERO_MEDIA = re.compile(r"[^\s,;()]+\.(?:png|jpe?g|gif|webp|mp4|webm)\b|https?://[^\s,;()]+|!\[|publish_review", re.IGNORECASE)
HERO_PICK = re.compile(r"\b(picked|chose|chosen|selected|approved|decided|went with|go(?:ing)? with)\b", re.IGNORECASE)
HERO_WHO = re.compile(r"\((?:[A-Z]\w*)[^)]*\)|\b(Ben|Lothsahn|orchestrator|requester|the person)\b")
HERO_COMPARE = re.compile(r"\b(compar\w+|beside|next to|against|side by side)\b", re.IGNORECASE)
HERO_NAMED = re.compile(r"\b(with|against|beside|next to|vs\.?|from|than|and)\s+(the\s+)?[A-Z0-9]|[,:]\s*(the\s+)?[A-Z0-9]")
HERO_REUSE = re.compile(r"\bre-?us(e|es|ed|ing)\b", re.IGNORECASE)
HERO_COST = re.compile(r"\d+(?:\.\d+)?\s*(?:ms|µs|us|fps|%|k?\s*tris|triangles|draw calls?|batches|particles|MB)\b", re.IGNORECASE)
HERO_ESTIMATED = re.compile(r"\b(estimate[sd]?|expected|should be|guess|approx\w*)\b", re.IGNORECASE)
HERO_NA_REASON = re.compile(r"\b(bug ?fix\w*|fix(es|ed)?|tweak\w*|retun\w*|re-?tint\w*|re-?colou?r\w*|icons?|re-?export\w*|"
                            r"renam\w+|moved?|import\w*|third[- ]party|asset pack|refactor\w*|optimi[sz]\w*|performance|"
                            r"no new (model|effect|look|art|visual))\b", re.IGNORECASE)
HERO_NA_NEW_OK = re.compile(r"\b(re-?export\w*|renam\w+|moved?|third[- ]party|asset pack|import\w*)\b", re.IGNORECASE)
HERO_FORMAT = ("`Hero art: concepts: <2-3 still files> shown to <who>, <which one> picked; detail: compared with <the "
               "game's best models or effects of the class> in one still <file>; differs: from <Railgun, Plasma Bolt, ...>, "
               "no reuse of their effects (or: reuses <what>); distinct: <what makes it distinctive>; cost: <measured ms or "
               "fps in a built player>`")


def hero_art_files(files: list[str] | None, changes: dict | None = None) -> list[str]:
    """The changed files that make this a hero-art change (see the block comment above)."""
    found = []
    for f in files or []:
        if not f.startswith("Assets/") or NOT_GAME_CODE.search(f) or THIRD_PARTY.search(f) or f.endswith(".cs"):
            continue
        status, lines = (changes or {}).get(f, ("?", 0))
        if HERO_MODEL.search(f) and not NOT_EFFECT_ART.search(f):
            if status in ("A", "?"):
                found.append(f)
        elif EFFECT_ART.search(f) and not NOT_EFFECT_ART.search(f):
            if status == "A" or (status == "M" and lines >= HERO_EDIT_LINES):
                found.append(f)
    return found


def hero_text(section: str) -> tuple[str, str] | None:
    """The `Hero art:` line plus the indented or bulleted lines under it -> (who, text)."""
    found = field(section, "Hero art")
    if not found:
        return None
    lines = section.split("\n")
    start = next(i for i, l in enumerate(lines) if re.match(r"^\s*Hero art\s*(?:\([^)]*\))?\s*:", l, re.IGNORECASE))
    text = [found[1]]
    for later in lines[start + 1:]:
        if later.strip() and (later.startswith((" ", "\t")) or re.match(r"^\s*[-*]\s", later)):
            text.append(later.strip().lstrip("-* ").strip())
        else:
            break
    return found[0], " ".join(t for t in text if t)


def hero_parts(text: str) -> dict[str, str]:
    marks = list(HERO_ART_LABELS.finditer(text))
    parts = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        label = re.split(r"\s", m.group(1).lower())[0].rstrip("s")
        label = "differ" if label.startswith("differ") else "cost" if label in ("frame", "cost") else label
        parts.setdefault(label, text[m.end():end].strip(" ;,.\n"))
    return parts


def hero_art_problems(section: str, hero_files: list[str], changes: dict | None = None) -> tuple[list[str], list[str]]:
    """w1497: new models and effect art carry a filled `Hero art:` line, or `Hero art: n/a (<reason>)` that a reviewer sees
    in the verdict. The line names the concept stills and the pick, the detail comparison with our best, how it differs
    from the existing weapons' and effects', what makes it distinctive, and the measured frame cost."""
    where = ", ".join(hero_files[:3])
    found = hero_text(section)
    if not found or not found[1]:
        return ([f"new model or effect art ({where}) and no 'Hero art:' line (checklists/visual.md 5e; Ben, w1470: \"this is "
                 f"the end game weapon that needs to look really cool ... be creative with this\"; w1466: \"the model itself "
                 f"is not detailed enough\"). Add {HERO_FORMAT}, or 'Hero art: n/a (<why: a bug fix, a re-tint, an icon, "
                 f"a re-export, a third-party import>)' when nothing new is drawn"], [])
    text = found[1]
    na = re.match(r"^n/?a\b\s*[(:\-–—]?\s*(.*?)\)?\s*$", text, re.IGNORECASE)
    if na:
        reason = na.group(1)
        added = [f for f in hero_files if (changes or {}).get(f, ("?", 0))[0] == "A"]
        if len(reason) < 25 or not HERO_NA_REASON.search(reason):
            return (["'Hero art: n/a' has to say why in a sentence: a bug fix, a tweak, a re-tint, an icon, a re-export or "
                     "a third-party import (the reviewer reads it in the verdict)"], [])
        if added and not HERO_NA_NEW_OK.search(reason):
            return ([f"'Hero art: n/a' for added files ({', '.join(added[:3])}): a new model or effect file is new art; n/a "
                     f"holds only for a rename, move, re-export or third-party import"], [])
        return ([], [f"HERO ART SKIPPED for {where}: {reason[:200]}"])

    problems = []
    parts = hero_parts(text)
    for label, need in (("concept", "concepts: the 2-3 concept stills shown and which one was picked"),
                        ("detail", "detail: compared with the game's best models or effects of the class, in one still"),
                        ("differ", "differs: from the existing weapons' and effects' (Railgun, Plasma Bolt ...), with 'no "
                                   "reuse' or what it reuses"),
                        ("distinct", "distinct: what makes it distinctive"),
                        ("cost", "cost: the measured frame cost")):
        if label not in parts:
            problems.append(f"'Hero art' has no '{need.split(':')[0]}:' part ({need})")
        elif len(parts[label]) < (8 if label == "cost" else 25) or HERO_PLACEHOLDER.search(parts[label]):
            problems.append(f"'Hero art' part '{label}' is empty or a placeholder: {need}")
    if problems:
        return problems, []
    concepts = parts["concept"]
    if len(set(m.group(0).lower() for m in HERO_MEDIA.finditer(concepts))) < 2:
        problems.append("'Hero art' concepts: name at least two concept still files or links (2-3 clearly different "
                        "concepts, published before the build)")
    if not (HERO_PICK.search(concepts) and HERO_WHO.search(concepts)):
        problems.append("'Hero art' concepts: say which concept was picked and by whom (Ben picked B)")
    detail = parts["detail"]
    if not (HERO_COMPARE.search(detail) and HERO_NAMED.search(detail)
            and re.search(r"\bstill\b|" + HERO_MEDIA.pattern, detail, re.IGNORECASE)):
        problems.append("'Hero art' detail: say what it was compared with (name the game's best existing models or effects "
                        "of the class) and the one side-by-side still")
    differ = parts["differ"]
    if not (HERO_REUSE.search(differ) and HERO_NAMED.search(differ)):
        problems.append("'Hero art' differs: name the existing weapons or effects it was compared with and say 'no reuse' "
                        "or what it reuses (w1470 reused the Plasma Bolt orb)")
    cost = parts["cost"]
    if not HERO_COST.search(cost):
        problems.append("'Hero art' cost: give the measured frame cost with its unit (ms, fps, %, tris, draw calls)")
    elif HERO_ESTIMATED.search(cost) and not re.search(r"\bmeasured\b", cost, re.IGNORECASE):
        problems.append("'Hero art' cost is measured in a built player, not estimated")
    return problems, ([] if problems else [f"hero art: {text[:200]}"])


# ---------------------------------------------------------------------------------------------
# Scale (w2204): a new or changed world model is shown in a built game beside the objects it sits among.
#
# Ben, 2026-10-25, after #1596's Repair Pack shipped far too big on connectors: "the repair pack connector item is
# comically large. make sure you test these visually when you add new models to the game in the future". #1596 added
# no fbx (its mesh is Assets/Art/Content/RepairPack/RepairPack.asset), so the Hero art rule never saw it. The rule is
# lessons/visual-fixes-are-verified-by-looking.md (w2204) and checklists/visual.md 5k; this is the part a script can check.
#
# What counts (calibrated on the game repo's 600 pull requests merged 2026-10-01..25, see ScaleTest):
#  - a model file (HERO_MODEL) or a mesh asset under Assets/Art/{Content,Models,ItemArt}/, added or changed (a re-export
#    can change its size; a re-tint says so on 'Scale: n/a (...)');
#  - an added world prefab: an item on connectors (Resources/ConnectorEntities), a structure, ship or pickup
#    (Resources/ItemEntities), a projectile (Prefabs/EffectsEntities/Projectiles). Edited prefabs are not counted:
#    #1987 alone edited 70 for map icons, and a file list cannot tell a scale edit from those;
#  - not counted: third-party packs, effects and VFX folders, UI, icons, sprites, textures, scripts and tests.
SCALE_MESH_ASSET = re.compile(r"^Assets/Art/(Content|Models|ItemArt)/.*\.asset$", re.IGNORECASE)
SCALE_PREFAB = re.compile(r"^Assets/(Resources/(ConnectorEntities|ItemEntities)|Prefabs/EffectsEntities/Projectiles)/"
                          r"[^/]+\.prefab$", re.IGNORECASE)
SCALE_NOT_WORLD = re.compile(r"/Effects?/|Vfx|/UI/|Icon|Sprite|Hologram|Font|/Fog|Outline", re.IGNORECASE)
SCALE_ITEM = re.compile(r"/ConnectorEntities/|/ConnectorItems/|/ItemArt/|ConnectorItem", re.IGNORECASE)
SCALE_BUILT = re.compile(r"\bbuilt\b|\bplayer build\b|\bbuild \d+", re.IGNORECASE)
SCALE_BESIDE = re.compile(r"\b(beside|next to|among|alongside|between|side by side)\b", re.IGNORECASE)
SCALE_VERDICT = re.compile(r"\b(match(es|ed)?|in scale|same (size|scale|height)|fits?|in proportion|proportionate|"
                           r"consistent)\b|\d+(?:\.\d+)?\s*(x|%)(?!\w)", re.IGNORECASE)
SCALE_NA_REASON = re.compile(r"\b(re-?tint\w*|re-?colou?r\w*|materials?|textures?|colou?rs?|unused|concepts?|renam\w+|moved?|"
                             r"not (drawn|used|shown|placed|spawned|in the world)|same (size|bounds)|"
                             r"(size|bounds|scale) (is )?unchanged|unchanged (size|bounds|scale))\b", re.IGNORECASE)
SCALE_NA_NEW_OK = re.compile(r"\b(unused|concepts?|renam\w+|moved?|not (drawn|used|shown|placed|spawned|in the world))\b",
                             re.IGNORECASE)
SCALE_FORMAT = ("`Scale: <still.png>: <the model> beside <its neighbours: ordinary items on the same connector and in the "
                "same inserter hand, or the structures, ships or projectiles around it> at gameplay zoom in a built "
                "player; its size matches theirs (or: <ratio>)`")


def scale_files(files: list[str] | None, changes: dict | None = None) -> list[str]:
    """The changed files that put a new or resized model in the world (see the block comment above)."""
    found = []
    for f in files or []:
        if not f.startswith("Assets/") or NOT_GAME_CODE.search(f) or THIRD_PARTY.search(f) or SCALE_NOT_WORLD.search(f):
            continue
        status = (changes or {}).get(f, ("?", 0))[0]
        if status == "D":
            continue
        if HERO_MODEL.search(f) or SCALE_MESH_ASSET.search(f):
            found.append(f)
        elif SCALE_PREFAB.search(f) and status == "A":
            found.append(f)
    return found


def scale_problems(section: str, model_files: list[str], changes: dict | None = None) -> tuple[list[str], list[str]]:
    """w2204: a new or changed world model names a built-game still of it beside its neighbours at gameplay zoom, with a
    size verdict; an item's still shows it on a connector and in an inserter hand. `Scale: n/a (<why>)` is a note."""
    where = ", ".join(model_files[:3]) + (f" and {len(model_files) - 3} more" if len(model_files) > 3 else "")
    item = any(SCALE_ITEM.search(f) for f in model_files)
    found = field(section, "Scale")
    if not found or not found[1]:
        return ([f"a new or changed world model ({where}) and no 'Scale:' line (checklists/visual.md 5k; Ben, w2204: "
                 f"\"the repair pack connector item is comically large. make sure you test these visually when you add "
                 f"new models to the game in the future\"). Add {SCALE_FORMAT}"
                 + ("; for an item, the still shows it on a connector and in an inserter hand next to ordinary items"
                    if item else "")
                 + ". A still of the model on its own, or an editor preview, does not count. Or 'Scale: n/a (<why: a "
                   "re-tint, a material or texture only, size unchanged, not drawn in the world>)'"], [])
    text = found[1]
    if re.match(r"n/?a\b", text, re.IGNORECASE):
        reason = text[3:].strip(" ():-")
        added = [f for f in model_files if (changes or {}).get(f, ("?", 0))[0] == "A"]
        if len(reason) < 25 or not SCALE_NA_REASON.search(reason):
            return (["'Scale: n/a' has to say why in a sentence: a re-tint, a material or texture only, the size is "
                     "unchanged, or the model is not drawn in the world"], [])
        if added and not SCALE_NA_NEW_OK.search(reason):
            return ([f"'Scale: n/a' for added files ({', '.join(added[:3])}): a new model in the world is checked beside "
                     f"its neighbours; n/a fits only a model that is not drawn in the world, an unused concept, a rename "
                     f"or a move"], [])
        return ([], [f"SCALE SKIPPED for {where}: {reason[:200]}"])
    problems = []
    if HERO_PLACEHOLDER.search(text) or len(text) < 40:
        problems.append(f"'Scale' is empty or a placeholder: {SCALE_FORMAT}")
    if not STILL.search(text):
        problems.append("'Scale' names no still (png, jpg, webp) of the model in the game beside its neighbours")
    if not SCALE_BUILT.search(text):
        problems.append("'Scale' does not say the still is from a built player: an editor preview or a prefab view "
                        "shows no neighbours at the size the player sees them")
    if not SCALE_BESIDE.search(text):
        problems.append("'Scale' does not say what the model is beside: name the existing items, structures, ships or "
                        "projectiles in the same still (a still of the model on its own does not count)")
    if not re.search(r"\bzoom", text, re.IGNORECASE):
        problems.append("'Scale' does not say the zoom: at gameplay zoom, as a player sees it")
    if not SCALE_VERDICT.search(text):
        problems.append("'Scale' gives no verdict on its size: 'its size matches theirs', or the ratio you measured")
    if item:
        for place, shown in (("connector", "on a connector"), ("inserter", "in an inserter hand")):
            if not re.search(rf"\b{place}", text, re.IGNORECASE):
                problems.append(f"'Scale' for an item does not show it {shown}: an item is checked on a connector "
                                f"and in an inserter hand next to ordinary items (w2204, the Repair Pack)")
    return problems, ([] if problems else [f"scale: {text[:200]}"])


SCALE_NOTE = re.compile(r"^\s*Scale\s*:|\b(models?|meshe?s?|fbx|prefabs?)\b", re.IGNORECASE | re.MULTILINE)


def scale_questions(note: str) -> list[str]:
    """w2204: a review note about a model asks the fresh critic about its size beside its neighbours."""
    if not SCALE_NOTE.search(note):
        return []
    return ["Is it in scale with its neighbours? In each still of the model in the game, name the objects beside it (the "
            "ordinary items on the same connector and in the same inserter hand, the structures, ships or projectiles "
            "around it) and say whether its size matches theirs, or how many times bigger or smaller it looks. A still "
            "of the model on its own cannot answer this: say so."]


# ---------------------------------------------------------------------------------------------
# Hidden census (w2210): a change to what hides, culls or shows a thing in the world proves, in a built game, that
# nothing it carries is still drawn where the hidden thing was.
#
# Ben fixed Hide Flying Stations (F7, w1320 #1766, re-landed w1365 #1790) one leftover at a time: the belt items (w1435
# #1861), the hover field and beams (w1909 #2345: "also the visual effect on floating stations, the hovering wispy
# effect, doesnt disappear when you hide mobile stations, they should also disappear, it looks weird to show that wispy
# outline and theres no ship there"), then w2209: "hiding mobile stations should hide any shielding they have and the
# rocket engine effects. and anything else, you keep missing stuff". Each PR listed what it hid by hand; none counted
# what was still drawn. The rule is lessons/check-every-kind-of-object-shared-presentation-draws.md (w2210) and
# checklists/visual.md 5l; this is the part a script can check.
#
# What counts (calibrated on the game repo's 947 pull requests merged 2026-10-01..25, see HiddenCensusTest): a game
# script under Assets/Scripts whose file name says it hides, shows or culls (…Visibility…, …Hide…, …Hidden…, …Cull…),
# added or changed. Not counted: UI (a panel's hide), the lobby's visibility, diagnostics, probes and audits, tests.
HIDE_CODE = re.compile(r"^Assets/Scripts/(?:.*/)?[^/]*(Visibility|Hide|Hidden|Cull)[^/]*\.cs$", re.IGNORECASE)
HIDE_NOT_WORLD = re.compile(r"/(UI|Lobby|Diagnostics)/|Audit|Probe", re.IGNORECASE)
CENSUS_EVIDENCE = re.compile(r"[^\s,;()]+\.(?:png|jpe?g|webp|mp4|webm|mov|json|log|txt|csv)\b|publish_review",
                             re.IGNORECASE)
CENSUS_PLACE = re.compile(r"\b(bounds|inside|within|around|where)\b", re.IGNORECASE)
CENSUS_COUNT = re.compile(r"\b(\d+|zero|none|nothing)\b(?:\s+[\w-]+){0,5}?\s+(drawn|renderers?|left|remain\w*|visible|"
                          r"showing|shown|enabled)\b", re.IGNORECASE)
CENSUS_KINDS = re.compile(r"\b(child(?:ren)?|vfx|particles?|particle systems?|shields?|engines?|thrusters?|lights?|"
                          r"trails?|outlines?|labels?|icons?|items?|beams?|fields?|glows?|effects?|decals?|markers?|"
                          r"bars?|lines?|rings?|projectiles?|cargo|turrets?|lamps?)\b", re.IGNORECASE)
CENSUS_NA_REASON = re.compile(r"\b(revert\w*|release|selection|select\w*|input|click\w*|hover card|drag|setting|own(s|er|"
                              r"ership)?|per[- ]player|save\w*|join\w*|renam\w+|moved?|refactor\w*|comment\w*|doc\w*|"
                              r"log\w*|tests? only|nothing (drawn|shown|visible) changes|no (drawn|visible|rendering) "
                              r"change|draws? nothing|not (drawn|rendered|in the world))\b", re.IGNORECASE)
CENSUS_FORMAT = ("`Hidden census: <clip, still or census log>: with <the thing> hidden in a built player, 0 renderers, "
                 "particle systems and VFX still drawn inside its bounds; it carries <every visual it can carry: its "
                 "children, VFX, particles, shields, engines, lights, trails, outlines, labels, icons, attached items>`")


def hide_files(files: list[str] | None, changes: dict | None = None) -> list[str]:
    """The changed game scripts that hide, show or cull a thing in the world (see the block comment above)."""
    return [f for f in files or [] if HIDE_CODE.search(f) and not NOT_GAME_CODE.search(f)
            and not HIDE_NOT_WORLD.search(f) and (changes or {}).get(f, ("?", 0))[0] != "D"]


def census_problems(section: str, code_files: list[str]) -> tuple[list[str], list[str]]:
    """w2210: a hide or visibility change counts, in a built game, what is still drawn inside the hidden thing's bounds
    (expect 0) and lists every visual the thing carries. `Hidden census: n/a (<why>)` is a note."""
    where = ", ".join(code_files[:3]) + (f" and {len(code_files) - 3} more" if len(code_files) > 3 else "")
    found = field(section, "Hidden census")
    if not found or not found[1]:
        return ([f"a change to hide or visibility code ({where}) and no 'Hidden census:' line (checklists/visual.md 5l; "
                 f"Ben, w2209: \"hiding mobile stations should hide any shielding they have and the rocket engine "
                 f"effects. and anything else, you keep missing stuff\"). Add {CENSUS_FORMAT}. A list of what you hid "
                 f"does not count: count what is still drawn. Or 'Hidden census: n/a (<why: a revert, selection or "
                 f"input only, who owns the setting, nothing drawn changes>)'"], [])
    text = found[1]
    if re.match(r"n/?a\b", text, re.IGNORECASE):
        reason = text[3:].strip(" ():-")
        if len(reason) < 25 or not CENSUS_NA_REASON.search(reason):
            return (["'Hidden census: n/a' has to say why in a sentence: a revert, a selection or input change only, "
                     "who owns the setting, or nothing that is drawn changes"], [])
        return ([], [f"HIDDEN CENSUS SKIPPED for {where}: {reason[:200]}"])
    problems = []
    if HERO_PLACEHOLDER.search(text) or len(text) < 40:
        problems.append(f"'Hidden census' is empty or a placeholder: {CENSUS_FORMAT}")
    if not CENSUS_EVIDENCE.search(text):
        problems.append("'Hidden census' names no clip, still or census log of the hidden thing")
    if not SCALE_BUILT.search(text):
        problems.append("'Hidden census' does not say it was taken in a built player: a hide that works in the editor "
                        "can leave a VFX graph or a GameObject drawn in the build")
    if not CENSUS_PLACE.search(text):
        problems.append("'Hidden census' does not say where it counted: inside the hidden thing's bounds")
    counts = [m.group(1).lower() for m in CENSUS_COUNT.finditer(text)]
    if not counts:
        problems.append("'Hidden census' gives no count of what is still drawn there: '0 renderers, particle systems "
                        "and VFX still drawn inside its bounds'")
    elif not any(c in ("0", "zero", "none", "nothing") for c in counts):
        problems.append(f"'Hidden census' counts {counts[0]} still drawn: hide each one, or name it and why it stays")
    if len({k.lower().rstrip("s") for k in CENSUS_KINDS.findall(text)}) < 3:
        problems.append("'Hidden census' does not list what the thing carries: its children and the separate entities "
                        "and GameObjects that follow it (VFX, particles, shields, engines, lights, trails, outlines, "
                        "labels, icons, attached items)")
    return problems, ([] if problems else [f"hidden census: {text[:200]}"])


HIDE_NOTE = re.compile(r"^\s*Hidden census\s*:|\b(hid(e|es|den|ing)|visibility|cull\w*|invisible)\b",
                       re.IGNORECASE | re.MULTILINE)


def census_questions(note: str) -> list[str]:
    """w2210: a review note about a hide asks the fresh critic what is still drawn where the hidden thing was."""
    if not HIDE_NOTE.search(note):
        return []
    return ["Is anything still drawn where the hidden thing was? In each frame after the hide, look where it stood: "
            "name any glow, particle, shield, engine flame, light, trail, outline, label, icon, beam or item left there "
            "(Ben, w2209: \"you keep missing stuff\"). A frame that does not show that place cannot answer this: say so."]


def balance_problems(body: str, files: list[str] | None) -> list[str]:
    """Enemy, combat or spawn numbers changed: a '## Balance' section with the stages run, the before/after table, the
    lane's flags and what became of the baselines, or 'No curve change: <why>' (w1440, checklists/balance.md)."""
    changed = [f for f in files or [] if BALANCE_PATH.search(f)]
    if not changed:
        return []
    section = evidence_section(body or "", "Balance")
    if section is None:
        return [f"this PR changes {', '.join(changed[:3])}{' and more' if len(changed) > 3 else ''} (enemy, combat or "
                f"spawn numbers) with no '## Balance' section: run the balance stages on a player of the base and of "
                f"this branch and paste `python scripts/nightly/balance_lane.py compare <before> <after>`, or write "
                f"'No curve change: <why>' (checklists/balance.md)"]
    unchanged = field(section, "No curve change")
    if unchanged and len(unchanged[1]) >= 20:
        return []
    problems = []
    stages = field(section, "Stages")
    if not stages or "BAL-" not in stages[1]:
        problems.append("'## Balance' has no 'Stages:' line naming the BAL- stages run on both builds")
    if not COMPARE_TABLE.search(section):
        problems.append("'## Balance' has no before/after table: paste `balance_lane.py compare <before> <after>`")
    flags = field(section, "Flags")
    if not flags or not flags[1]:
        problems.append("'## Balance' has no 'Flags:' line: the lane's flags on the after build, or 'none'")
    baseline = field(section, "Baseline")
    if not baseline or not baseline[1]:
        problems.append("'## Balance' has no 'Baseline:' line: which baselines in balance-curve.json moved and why, "
                        "or 'unchanged'")
    return problems


def check(body: str, files: list[str] | None = None, brief: str | None = None,
          changes: dict | None = None) -> tuple[list[str], list[str]]:
    """Every reason the evidence is not ready (empty = PASS), and notes that do not fail it."""
    used_by = used_by_problems(body, files) + balance_problems(body, files)
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
    unlabelled = 0
    for claim, basis in rows:
        label = basis.split(":")[0].strip()
        unlabelled += label not in BASES and label != "GUESS"
        if label == "GUESS":
            problems.append(f"'{claim}' rests on a guess: verify it, or move it to 'Not verified' and take it out of "
                            f"the title and TL;DR")
        elif label not in BASES:
            problems.append(f"'{claim}': the basis starts with MEASURED or SOURCED, then says how or where")
        elif not has_basis(basis):
            problems.append(f"'{claim}': {label} needs what was measured or the source, after a colon")
    if unlabelled >= 2:
        # w1648: a table of measurements inside the section reads as claims with no basis, one problem per row
        problems.append("several table rows carry no MEASURED/SOURCED basis: a measurement table is not the claims table; "
                        "put it under its own '## ' heading after the Evidence section and cite it from one claim")

    open_lines = [l for l in section.split("\n") if not re.match(r"^\s*Not verified\s*:", l, re.IGNORECASE)]
    pending = PENDING.search("\n".join(open_lines))
    if pending:
        problems.append(f"something is still '{pending.group(0)}': no merge before the review is finished. Finish it, "
                        f"or move the claim it supports to 'Not verified'")
    unverified = field(section, "Not verified")
    if not unverified or not unverified[1]:
        problems.append("no 'Not verified:' line: name what you could not check, or write 'nothing'")

    ui_files = [f for f in files or [] if UI_PATH.search(f) and not NOT_GAME_CODE.search(f)]
    ui = "ui" in kinds or ("visual" in kinds and bool(ui_files))
    not_ui = field(section, "Not UI")
    if not_ui and not_ui[1] and ui:
        others = [f for f in ui_files if not NOT_UI_OK.search(f) and not moved_to_ui_world(f, files, changes)]
        if "ui" in kinds:
            problems.append("'Not UI:' and 'Kind: ui' contradict each other: a screen, panel or HUD change keeps the UI rules")
        elif others:
            problems.append(f"'Not UI:' covers only scripts under UI/World/ (a world-space mark drawn as a mesh), not "
                            f"{', '.join(others[:3])}: a panel, prefab or scene keeps the UI rules (checklists/ui.md)")
        elif len(not_ui[1]) < 30:
            problems.append("'Not UI:' has to say why: what draws it (a mesh, a line, a world-space marker) and that no "
                            "canvas, panel or HUD element changes")
        else:
            ui = False
            notes.append(f"not UI (the layout census does not apply): {not_ui[1][:160]}")
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
        art_files = [f for f in files or [] if EFFECT_ART.search(f) and not NOT_EFFECT_ART.search(f)]
        if art_files and not ui:
            problems += art_language_problems(section, art_files)
            notes += art_language_notes(section)
        told = re.sub(r"^#{1,6}\s*Used by\b.*?(?=^#{1,6}\s|\Z)", "", body, flags=re.DOTALL | re.MULTILINE | re.IGNORECASE)
        problems += closeup_problems(section, claims_text=told)[0]

    hero_files = hero_art_files(files, changes)
    if hero_files:
        hero_found, hero_notes = hero_art_problems(section, hero_files, changes)
        problems += hero_found
        notes += hero_notes

    model_files = scale_files(files, changes)
    if model_files:
        scale_found, scale_notes = scale_problems(section, model_files, changes)
        problems += scale_found
        notes += scale_notes

    hidden_code = hide_files(files, changes)
    if hidden_code:
        census_found, census_notes = census_problems(section, hidden_code)
        problems += census_found
        notes += census_notes

    if ui:
        ui_found, ui_notes = ui_problems(section, brief if brief is not None else brief_in_body(body))
        problems += ui_found
        notes += ui_notes

    deck, deck_notes = deck_problems(section, files)
    problems += deck
    notes += deck_notes

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
        # w2487: "1,596 of 1,596 compared heartbeats matched" names the count too: allow up to two words
        # (compared, shared, matched) between the number and "heartbeats".
        elif not re.search(r"\d[\d,]*\s*(?:[a-z-]+\s+){0,2}heartbeats", audit[1], re.IGNORECASE):
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
        cards = [f for f in files if OBJECTIVE_PATH.search(f)]
        built = field(section, "Built player")
        if (cards and not {"visual", "ui"} & set(kinds) and not (built and built[1].lower().startswith("yes"))
                and not any("no visible change" in c.lower() and has_basis(b) for c, b in rows)):
            problems.append(f"tutorial or objective cards changed ({', '.join(cards[:3])}): a player reads them, so show the "
                            f"card in a built player and say 'Built player: yes, <how you reached it>' (w918), or add a claim "
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


def comment_refused(problems: list[str]) -> bool:
    """w807: --comment posts nothing from a copy older than the released one (its FAIL is about the copy, not the PR)."""
    return any(p.startswith("this pr_evidence.py is ff-agents") for p in problems)


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
        problems, _ = check(pr.get("body") or "", files, changes=changes_of(pr.get("files") or []))
        rows.append({"number": pr["number"], "title": pr["title"], "verdict": "FAIL" if problems else "PASS",
                     "before_merge": "yes" if passed_before_merge(pr) else "no", "why": problems[0] if problems else ""})
    return rows


def changes_of(gh_files: list[dict]) -> dict:
    """`gh pr view --json files` -> {path: (status letter, lines changed)}; changeType is ADDED, MODIFIED, RENAMED, DELETED."""
    letters = {"ADDED": "A", "MODIFIED": "M", "RENAMED": "R", "DELETED": "D", "COPIED": "A"}
    return {f["path"]: (letters.get(f.get("changeType", ""), "?"), int(f.get("additions") or 0) + int(f.get("deletions") or 0))
            for f in gh_files}


def every_file(repo: str, number, first: list[dict]) -> list[dict]:
    """`gh pr view --json files` stops at 100 files (w2204: #1596 has 108, #1987 153), so a model past the 100th went
    unseen. At 100, read them all from the REST API, in the same shape."""
    if len(first) < 100:
        return first
    status = {"added": "ADDED", "removed": "DELETED", "renamed": "RENAMED", "copied": "COPIED"}
    rows = gh("api", "--paginate", f"repos/{repo}/pulls/{number}/files", "--jq",
              ".[] | {path: .filename, status: .status, additions: .additions, deletions: .deletions}")
    found = [json.loads(line) for line in rows.splitlines() if line.strip()]
    return [{"path": f["path"], "changeType": status.get(f["status"], "MODIFIED"), "additions": f["additions"],
             "deletions": f["deletions"]} for f in found] or first


def parse_files_file(text: str) -> tuple[list[str], dict]:
    """One path per line; optionally git's name-status form `A<TAB>path` or `M<TAB>path<TAB>lines changed`."""
    files, changes = [], {}
    for line in text.splitlines():
        cells = line.split("\t")
        if len(cells) >= 2 and re.fullmatch(r"[AMDRC]\d*", cells[0].strip()):
            path = cells[-1] if cells[0].startswith(("R", "C")) else cells[1]
            lines = int(cells[2]) if len(cells) > 2 and cells[2].strip().isdigit() and not cells[0].startswith(("R", "C")) else 0
            changes[path] = ("A" if cells[0][0] == "C" else cells[0][0], lines)
            files.append(path)
        elif line.strip():
            files.append(line.strip())
    return files, changes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="OWNER/NAME")
    ap.add_argument("--pr", type=int)
    ap.add_argument("--comment", action="store_true", help="post the verdict on the pull request")
    ap.add_argument("--body-file", help="check this description instead of asking GitHub")
    ap.add_argument("--files-file", help="with --body-file: the changed paths, one per line")
    ap.add_argument("--brief", help="the request's brief (read_work's text): every asked (who): \"...\" quote on the "
                                     "'Moved:' list must be in it word for word (w826)")
    ap.add_argument("--audit", action="store_true", help="list merged pull requests and their verdicts")
    ap.add_argument("--offline", action="store_true", help="skip the check that this copy is the released version")
    ap.add_argument("--since", help="--audit: merged on or after this date (YYYY-MM-DD)")
    ap.add_argument("--base", default="master", help="--audit: the base branch (default master)")
    ap.add_argument("--limit", type=int, default=100, help="--audit: at most this many pull requests")
    ap.add_argument("--note", help="check a review note (the markdown you hand publish_review) instead: every claim that a "
                                   "defect is gone or an effect happens names its close-up, and each file is beside it")
    ap.add_argument("--note-dir", help="--note: the folder its files are in (default: the note's own folder)")
    ap.add_argument("--questions", help="--note: write the claims as questions for the fresh critic to this file")
    args = ap.parse_args(argv)

    if args.note:
        note = Path(args.note)
        problems, questions = closeup_problems(note.read_text(encoding="utf-8"), Path(args.note_dir) if args.note_dir
                                               else note.resolve().parent)
        questions += scale_questions(note.read_text(encoding="utf-8"))
        questions += census_questions(note.read_text(encoding="utf-8"))
        if args.questions:
            Path(args.questions).write_text("".join(f"- {q}\n" for q in questions), encoding="utf-8")
        print(verdict_text(problems, [f"{len(questions)} claim(s) for the critic, as questions"
                                      + (f" in {args.questions}" if args.questions else " (--questions FILE writes them)")]
                           if questions else []))
        return 1 if problems else 0

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
        if args.files_file:
            files, changes = parse_files_file(Path(args.files_file).read_text(encoding="utf-8"))
        elif args.repo and args.pr:
            # w1684: a draft description checked against the PR's own files; with no file list the Balance and Used by
            # rules never ran, the draft passed, and the PR's posted verdict failed on a missing '## Balance'.
            pr = json.loads(gh("pr", "view", str(args.pr), "--repo", args.repo, "--json", "files"))
            all_files = every_file(args.repo, args.pr, pr.get("files") or [])
            files, changes = [f["path"] for f in all_files], changes_of(all_files)
        else:
            files, changes = None, None
            print("note: no file list (--files-file, or --repo and --pr): the rules that read the changed files "
                  "(Balance, Used by, Deck, UI paths) did not run", file=sys.stderr)
    elif args.repo and args.pr:
        pr = json.loads(gh("pr", "view", str(args.pr), "--repo", args.repo, "--json", "body,files"))
        all_files = every_file(args.repo, args.pr, pr.get("files") or [])
        body, files = pr.get("body") or "", [f["path"] for f in all_files]
        changes = changes_of(all_files)
        if not applies(files):
            print("PASS: no game code or assets changed, so no Evidence section is needed")
            return 0
    else:
        ap.error("give --repo and --pr, or --body-file, or --audit")

    brief = Path(args.brief).read_text(encoding="utf-8") if args.brief else None
    problems, notes = check(body, files, brief, changes)
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
        if comment_refused(problems):
            # w807: a FAIL for "your copy is old" was posted on a PR twice and deleted by hand; it says nothing about the PR.
            print("not posted: update ff-agents first (claude plugin marketplace update final-factory-agents && "
                  "claude plugin update ff-agents@final-factory-agents), then run the newest copy")
            return 1
        gh("pr", "comment", str(args.pr), "--repo", args.repo, "--body", text)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
