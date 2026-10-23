---
name: verify-ui-with-full-content-like-a-player
description: "A UI change is verified the way a player sees it: every screen and sub-view in a late-game save, in a built player at the target size, showing its whole content, on the classic panels' colours and art, still in a real-rate clip, each still checked against the requester's words. A tour that proves each tab opens and fits passes a broken screen. A Deck tour on a PC is a stand-in: a Deck-facing change is verified on a real Deck or reported 'not verified on a real Deck' (w770). Before any still goes to a person, every still is judged by eye on its own, one line each (stretched controls, mostly empty windows, overlapping labels, text dumps), apart from every before/after comparison and the census; a redesign goes out as 2-3 options built from the game's best dialogs (w1386, w1296). And no still reaches a person before a fresh critic that never saw the code or the worker's reasoning has graded it from a pack of crops, reference panels and the person's words, with the colour and shape checks clean against the before (w1399: three rejected screens all said Looked: yes)."
date: 2026-10-08
---

# Verify UI with full content, like a player

**Rule.** A screen is verified when a still of it, taken in a late-game save in a built player at
the target size, shows its whole content (every row of the grid, the tree, the preview), looks like
the classic panel it replaces, holds still in a real-rate clip, and has been described line by line
against what the requester asked for. "Opens", "fits" and "no text under 9 px" are necessary and
far from enough.

**Why.** The w644 hub (#1251, merged 2026-10-08, shipped in Build 89) passed a scripted Deck tour:
14 stills at 1280x800 and 14 at 1920x1080, 0 failures, "Looked: yes, every shot at full size". On
Ben's real Deck nearly every tab was broken: dark navy where the game's panels are teal-blue,
Crafting cut to one row, Technology with no tech grid, the Blueprints preview off the bottom with
flickering icons, Factory info using a fraction of its pane. Why the tour missed it (w718):

- **It checked the wrong claims.** MEASURED (#1251's Evidence): every row is "opens", "switches",
  "B closes", "fits above the hotbar", "no text under 9 px". No row says a tab shows its full
  content or matches the classic look.
- **The colour was typed into code and never compared.** MEASURED: `StructuredHub.Shade` fills
  the hub with `new Color(0.04f, 0.07f, 0.11f, 0.96f)` (`StructuredHub.cs:527`), #0a121c, nearly
  opaque. The classic Inventory panel, translucent over space, samples at #163a56 (its most common
  colour in a w524 still at 1920x1080): delta E 22.4 by `ui_check.py style`.
  The only classic check was "129 texts both times", a count.
- **The "before" had nothing to compare.** MEASURED: the before arm was develop, where the keys
  opened nothing new ("before-1280-b2-R1-no-tab.png: nothing open"), so no still showed the classic
  screen beside the hub.
- **Thin content, and sub-views never opened.** MEASURED: the PR says "The Info tab is the
  objectives list; the test save has none, so it shows only its header", and `tour/hub.json` only
  presses R1 and shoots: no blueprint is selected, so the preview that ran off Ben's screen never
  appeared. GUESS: a late-game save's longer recipe and tech lists are what cut Crafting to a row
  and emptied Technology on the Deck; w716 owns the cause.
- **Known cuts went to "Not verified" while the title said it works.** MEASURED: "WindowFit cut
  Crafting's list far more than needed when the pane was 17 px short ... the cut itself is
  unchanged", and Factory info's box "keeps a fixed height, so it gets the docked fit", against
  Ben's words for the hub: "the ui content should just fit in the whole pane of the hub panel".
- **The clips could not show flicker.** MEASURED: "Clips: ... 1 fps sequences of the tours'
  shots", with "Review: no watch_video: layout changes, no animation". The Deck tour has a `record`
  step that saves every frame (`DeckTour.cs`, `Record`); the hub's tour never used it. The hub's
  own code notes that two fits fighting over one list "made the window jump".
- **Fixed waits.** MEASURED: each shot follows a `wait` of 1.5 to 2.5 s, not a `waitFor` on the
  content. GUESS whether any still was taken before its screen had filled.
- **The census only reads text.** MEASURED: the tour's census counts texts under 9 px, clipped,
  off screen, overlapping, and covered controls. It has no measure of a grid's visible rows, a
  window's share of its pane, a background colour, or motion. Its "12 clipped blueprint names" were
  waved through as "the tiles' own ellipses".
- **It had happened before.** SOURCED: Ben's rule of 2026-09-22 (project-memory
  `ui-screenshot-worst-case-before-done`) already said "Render the WORST case, not the demo case".
  It lived in a memory nobody's checks read. This time the rule is in `pr_evidence.py`, which
  fails a UI pull request that does not name its content, style, stills and clip.
- **No Deck hardware.** MEASURED: listed under "Not verified". GUESS how much of the miss is the
  real Deck (Proton, real Steam Input, a multiplayer client) rather than content.

- **It happened again with every check in place (w764, 2026-10-09).** MEASURED: the next Build, 90, had the full tour
  and the rules above, and a player (Discord, "New Steam Deck GUI notes") posted ten photos of a real Deck with eight
  faults none of them listed: the Technology tab's tile list two rows and a bit ("too small to actually be useful"), the
  Fleet header "Count" cut to "Coun" over "t", the Info tab empty after a load, the objectives card drawn over a Command
  Core's fields, windows laid over one another, the Mass Driver's "Intermediates" cut by a scroll bar. The census had no
  count for a cut word or a list's visible rows, and the tours never loaded a save with completed objectives, never kept
  the objectives card up while a Command Core opened, and never hovered a station with the inventory open. Each fault
  reproduced in the dev player the first time the state the photo shows was set up; none needed Deck hardware.

**How to apply.** [The UI checklist](../checklists/ui.md), and the `unity-ui` skill for the recipe:

- **A player's photos are tests (w764).** Put each photo beside your still of the same screen in the same state before the
  first fix; reproduce it in the built player (set up the state it shows); where the census stays quiet about what the photo
  shows, add the count to the census in the same change (since w764: `midWord` and `shortLists` in `DeckTourChecks`, with
  the failing case as a test fixture).

- Write the requester's words per screen first, with what "full content" means for each.
- Tour a late-game save; open every sub-view; `waitFor` content.
- For each still: `ui_check.py fill` for the pane, `ui_check.py style` against the classic panel
  from the same save, and one written line against the requester's words (`ui_check.py shots`).
- Record each screen at 30 fps or more and run `ui_check.py flicker`.
- In the PR, the `Content:`, `Full content:`, `Style:` and `Shots:` lines; `pr_evidence.py` fails a
  UI change without them (its fixture `pr-1251-deck-hub.md` is this PR, and fails).

## A simulated Deck is not a Deck (w770)
**The rule.** A change a Steam Deck player meets is not "done" on a Deck tour alone. The report
says "verified on a real Deck" with who, the Steam client and SteamOS versions, and what they saw,
or says "not verified on a real Deck" and what that leaves open. The checklist is
[deck.md](../checklists/deck.md); `pr_evidence.py` fails a Deck-facing PR with neither.

### Why: two corrections from Ben, 2026-10-09

- **w684 -> w768 (controller glyphs).** w684 closed done with PR #1249 on a Deck tour; its worker
  "could not confirm on real Deck hardware". On his Deck, Build 91, Ben: "Why aren't the Steam UI
  buttons, like the controller buttons showing anywhere?" The Deck ran Steam's Keyboard (WASD) and
  Mouse template, so Steam gave the game no action set, and every Deck button arrived as a real key
  that switched the prompts back to keys. w703 had also removed the fallback. His Deck's Steam
  client was out of date too: "omg my steam firmware was just way out of date lol. the controller
  layout shows after i updated". Fixed in PR #1300 (w768).
- **w767 (startup resolution).** Ben: "it's not taking up the whole width of the Steam Deck
  screen... It just looks like it's not rendering properly, like the aspect ratio is all messed
  up." The game stored the first-frame screen size (portrait 800x1280 under Proton) and re-applied
  it on every launch. The Deck tour forces its own windowed size every second and starts from clean
  prefs, so it could never see it. Fixed in PR #1301 (w767).

Both were the second correction of one kind on the same day: a fix verified on a stand-in for the
Deck, whose blind spots nobody named. A tour that passes tells you the stand-in works.

### How to apply

1. Before you write "fixed" on a Deck-facing change, list the four things a simulated Deck cannot
   show (template vs official layout, first-frame resolution under Proton/gamescope, Steam client
   and SteamOS version, touch) and say which your change touches.
2. Run the cheap stand-ins ([deck.md](../checklists/deck.md)), then ask for the real Deck through
   your orchestrator with the steps written out, starting with "the Deck's Steam client and
   SteamOS are up to date" (the w768 worker's proposal, adopted).
3. If nobody can look yet, write "not verified on a real Deck" in the report and the PR's
   `Real Deck:` line, and keep the request open when it is a player's report from their own Deck (`wNNN: still open: waiting on <name> to check on the Deck`).

### What was built and what was left (w770)

| Check | Status | Why |
|---|---|---|
| `Real Deck:` line on a Deck-facing PR | **Built**: `pr_evidence.py` `deck_problems`, fixtures of both cases | Needs only the PR text and its file list, which this repo already reads. |
| Checklist and ask template | **Built**: [deck.md](../checklists/deck.md), linked from the done, merge and UI lists | What a person must look at cannot be a script. |
| Keyboard-template simulation | **Already in the game repo** (w768, PR #1300: `-ffDeckTourFallback`, the `key` step, `specs/w768-deck-template-glyphs/template-tour.json`) | Nothing to add here; the checklist points at it. |
| Deck tour that does not force the size and starts from stored prefs | **Built in the game repo (w771, PR #1304)**: `-ffDeckTourSize none`, `-ffDeckTourPrefs <json>` | Measured on a Mac dev player: 800x1280 stays stuck before #1301, repaired to full screen on develop. The first-frame portrait read stays Deck-only. |
| Touch, Steam client version, whether the official layout is offered | **Checklist line only** | They exist only on the device. |

**The proposal for the game repo, as made (w771; the first-frame step was not built):**
`-ffDeckTourSize none` (or `-ffDeckTourNoResize`) skips the forced `Screen.SetResolution` in `Update`
and `HoldSize`; `-ffDeckTourPrefs <json>` writes `ResolutionWidth`, `ResolutionHeight` and
`FullscreenMode` (and a `DarkModeSkybox`-less first launch) before `PlayerSettingsController.Start`;
a tour step reads `Screen.width/height` at frame 1 and again after `StartupRecheckFrames`, and fails
when the window is not landscape or does not fill the display. The first-frame portrait read is
reported only under Proton (`Documentation/Display-Startup.md`), so a PC tour would test the repair,
not reproduce the Deck's first frame.

## Judge every still by eye before the person sees it (w1386, w1296, 2026-10-16)

**Rule.** Before a UI still goes to a person, look at each one at full size, as a player would on first sight, and
write one line per still: does anything look broken or poor? A control stretched or squashed out of its shape, a
window that is mostly empty space, labels running into each other or into a title, a dialog that is a dense block of
text, anything a player would call obviously broken. Write it as its own line, apart from the comparison with the
before still and apart from the census numbers: "same as before" is not "looks right", and a clean census is not a
look. A still that looks broken or poor is fixed before anyone sees it. When the problem is standing on master and not
yours to fix, say so in the first lines of the report and file it (or ask your orchestrator to). An orchestrator that
relays stills looks at them first, the same way.

Design work (a new dialog, a new panel, a redesign the person asked for) goes to the person as 2 or 3 clearly
different layouts, each built from the game's best existing dialogs and components (their title row, list rows,
buttons, spacing, fonts), as built-game stills. It does not go as the same layout with nudged spacing.

### Why

Two corrections from Ben on 2026-10-16, on stills that had passed their workers' checks:

- **w1386 (Discord triage, game PR #1813, the Circuit view leftovers).** In the Deck dock the review stills showed the
  Light Structure panel's On/Off switch drawn as a green bar across the whole panel (sprite 225x150, drawn 485x23). At
  1920x1080 the panel was mostly empty, with a tiny switch and swatch in one corner. The worker's shots sheet said "the
  lamp window on Main before any circuit press. Same both sides". That was true: the bar was on master too. The
  orchestrator relayed the stills without noticing either. Ben: "the light panel is really messed up obviously."
- **w1296 (mods per save, game PR #1744).** Round 2 of the "Content removed" dialog drew "ok looks better but the
  content removed panel could be formatted nicer. like theres the description then a list but it all bleeds
  together". Round 3 nudged the spacing and sent it again. It was still a tiny, narrow box in the middle of a 1920
  screen, with a nested bullet list and a heavy footer paragraph. Ben: "looks terrible. you can do better". The
  orchestrator's note to the worker passed on Ben's "reuse components when you can damnit".

Every check the workers ran compared two things: before against after, or one panel's colour against another's. None
asked whether the screen looked right on its own, so a defect present on both sides, or a design that was poor from
the start, passed every line.

### How to apply


- **One line per still, judged on its own** ([UI checklist](../checklists/ui.md) item 27). For each still, answer:
  is anything stretched or squashed? Is a window mostly empty space, or crammed into one corner? Do labels or texts
  overlap each other or the title? Is a dialog a dense block of text with no hierarchy? Would a player call it broken
  or ugly? Write the answer even when it is "nothing". The PR carries
  `Eye: N stills looked at full size, M look broken or poor (<where the lines are>)`; `pr_evidence.py` fails a UI PR
  without it, and fails M above 0 unless the line names the request a standing problem was filed as.
- **The census measures shape too.** `ui_layout.py shape <after censuses> [--repo <game repo>]` (unity-ui) prints the
  `Shape:` line. STRETCHED means a sprite drawn 2x or more off its own aspect. MOSTLY EMPTY means a window or dialog
  under 40 % covered, with one empty rectangle of 35 % or more of it. WALL OF TEXT means 8 or more lines in a box
  under 40 % of the screen wide. MEASURED on the w1386 tour's censuses, it flags the docked switch (14.1x) and the
  Light Structure panel at 1920x1080 and 1280x800 (30 % and 27 % covered, 37 % hole), and passes the Cargo Hold
  (24 % covered, 25 % hole), the hover cards and the HUD. `pr_evidence.py` fails a stretched sprite unless the
  requester asked for it (`intended (who): "..."`), and fails a mostly-empty window or a wall of text until the line
  says what you looked at and decided (`looked: ...`). The tool is a floor. A still it passes can still look poor:
  the eye line is the check.
- **A redesign is 2-3 options built from what the game already has.** Before drawing, list the game's best existing
  dialogs and panels of the same kind (for a dialog: the mod-mismatch dialog, the research and unlock popups, the save
  and load panel), and build each option from their components. Show each option as built-game stills at 1920x1080 and
  1280x800 with realistic content (the long list, the long name). Let the person pick. When the person says the
  same screen still looks wrong after a change, the next round is a redesign, not more spacing.
- **An orchestrator looks before it relays.** Open each still and answer the same questions. A worker's "Same both
  sides" or "PASS" is a claim about a comparison, not about how the screen looks.

## A fresh critic, not the author, judges the design (w1399, 2026-10-16)

**Rule.** No UI still or mock reaches a person until it has passed the design gate (checklist `ui.md`, at its top):
- It is built from the game's own components and colours (the game repo's `docs/UI-Style.md`).
- The worker has graded every still with the unity-ui `design-rubric.md`.
- `ui_look.py colour` and `ui_layout.py shape` show nothing new against the before.
- A **fresh** `ff-agents:ui-critic`, given only the pack `ui_look.py pack` builds, has graded it, and every broken or ugly
  finding is fixed, filed or answered with the person's own words.

The orchestrator relaying the stills opens each one before it reads the worker's words about it, and relays only with the
critic's report (FF Factory `read_rules ui`).

### Why

The same day as w1396, Ben rejected a third screen and said: "you make bad UI mistakes constantly". On w1334's round 2
(#1817): "the active stop color is bleeding into a bunch of the panel's elements, it looks bad, like its washing
everything out" and "the add stop bright blue is also painful on the eyes".

All three rejected PRs said "Looked: yes" (#1744, #1813, #1817), and #1817 had even fixed two text faults by eye. The
look happened. The judgement failed: each worker judged its own screen, against what it meant and against before/after
numbers. What w1399 measured:

- **Round 2 made the controls see-through** (the condition chip white at alpha 0.09; round 1's was opaque #CCCCCC) over
  the same see-through orange row. In Ben's own still, the chip in the active row is drawn delta E 13.6 from the same chip
  in a plain row; in round 1 the difference is 0.0. "+ Add stop" became a pale fill, #57B2D0 at L* 68, under a white
  label at 2.13:1 (round 1's blue bar: 4.6:1).
- **This game blends UI alpha in linear space.** A 25 % orange row draws #6A555C, where the HTML mock's sRGB mix shows
  #454F56 (delta E 14.2). A see-through colour looks far stronger in the game than in the mock it was picked from.
- **The comparison checks could not see it.** `Style:` passed #1813's broken panel at delta E 4.2 and took #1817's
  delta E 24.2 as proof that a menu "reads apart". The new colour came from the mock (`#5FC3E4`: 0 uses on master),
  though the code called it "the game's own".
- **The orchestrator's brief had no rule to look,** and an orchestrator loads no plugin, so the "orchestrator looks too"
  line in this lesson never reached it.
- **Research:**
  - Models favour their own work and the framing they are given.
  - Tint and opacity bugs have the lowest VLM recall (14 % in one study), so the numbers go to the critic as text.
  - Claude Code re-encodes an image over 500 KB as a lower-quality JPEG, so crops at the panel's own pixels show what a
    whole still hides.
  - All of it: `/srv/fff/review/w1399-ui-harness/research.md`.

### How to apply

- **Run the gate in order:** components, the rubric, the measurements, then the critic (checklist `ui.md` items 27, 28, 30
  and 31). The PR carries the `Eye:`, `Shape:`, `Colour:` and `Critic:` lines; `pr_evidence.py` fails one that is missing,
  or a `Critic:` line with a broken or ugly finding still open.
- **Give the critic the pack, nothing else:** `ui_look.py pack` builds it from the stills, censuses, the reference panels
  and the brief's quotes. Never brief it with what you changed, what you meant, or the PR. Use a new critic for each round.
- **Pick colours from the built pixel, not the mock.** Controls get opaque fills. A selected row shows its state on an
  edge or the number; the controls inside it keep their colours. A secondary action gets the game's quiet fill, not an
  accent.
- **The proof** (w1399, `/srv/fff/review/w1399-ui-harness/proof.md`):
  - The checks flag both w1334 complaints and the stretched w1386 switch, and fire on none of master's 15 panels for
    bleed.
  - In a blind trial, scored by an agent that did not know which method wrote which report, the critic named Ben's own
    defect on 4 of 4 rejected screens. Workers' looking as it is today did so on 1 of 3.
  - The critic is strict on old panels too: findings the before still also shows are STANDING and get filed, not fixed,
    unless the person's words ask for that kind of fix. w1386's words were "fix the ones that are clearly bugs", and the
    panel it fixed still showed its On/Off switch stretched 14x, as on master.
  - Rerun its cases (`/srv/fff/review/w1399-ui-harness/`) when the critic's role, the rubric or the model changes.

## A standing finding is filed with its wNNN or fixed, and the critic's coverage gap is shot (w1546, 2026-10-19)

w1546 was a bubble in the FF Factory portal for messages between people. Round 2 of its critic left one UGLY finding,
marked STANDING: on the phone, the header's model chip overlapped the title. The report said "handed to the orchestrator
to file". The orchestrator, for lothsahn, sent it back: "The critic's one UGLY finding still has no answer. ... 'Handed on
to be filed' doesn't count. Either fix it here (it's a small layout change on a screen you're already shooting), or file
it and give me the wNNN." The critic had also noted that no still showed many messages. That was exactly lothsahn's case:
"we're missing chat messages to each other when there's a lot of stuff from you and we haven't checked our messages in a
while". So the stills came back for a third round. The fix was 20 lines of CSS. Round 3 had 0 broken or ugly (#455).

### How to apply

- **Every BROKEN or UGLY finding, STANDING included, ends in one of two ways before you report:**
  - fixed in this change;
  - filed as a request, with its wNNN in the report and on the PR's `Critic:` line.
  - "Handed on", "to be filed" or "pre-existing" alone is an open finding. It does not count as filed.
- **Fix it here** when the fix is small and the screen is one your stills already shoot. Filing it costs the person a
  round as well.
- **When the critic names a coverage gap that is the person's own case, shoot that state before anyone sees the
  stills.** For example: many items, long text, the busy day the request is about. Then have a new critic judge it. A
  missing still of the requester's scenario is a gap in the proof, not a minor finding.

## A window is judged beside the game's other windows: corners, header, padding (w1818, 2026-10-23)

**Rule.** A new or changed window is compared with one of the game's existing windows, at the same size, on three things a
player sees only side by side: the corner radii are one family, with no rounded shape tight inside one of another radius;
the header has the size and weight of the other windows' titles and fits on one line; the padding at each edge matches,
with nothing against the top or the bottom. `ui_look.py family` measures what it can, and the critic always gets a
reference window and answers rubric item 9 against it.

### Why: two corrections from Ben, the second after a fresh critic passed the window

- w1296, the mods-per-save dialog (game PR #1744, 2026-10-15). The worker's own stills showed it and nobody flagged it:
  "the header for Content removed from this save looks bad since it's on too lines. The header should say something
  shorter that fits on one line so its not pushing up against the top of the panel".
- w1761, the circuit Calculations window (2026-10-22). A fresh critic "found nothing broken or ugly". Ben: "i dont like
  the differing border-radius values all smashed together. theres a circle around each letter, which is right next to
  the rounded border of the item, and the add calculation button has another separate radius. this needs to look
  cleaner and more unified, also the header font seems smaller than other headers. the UI needs to be consistent and
  clean", and "make the bottom padding a few more pixels too it feels crammed".

The rubric judged each window on its own (hierarchy, colour, state, shape, space, grouping, legibility, "like the same
game"), and the critic's side-by-side look asked only "does it look as finished": nothing named radii, header size or
edge padding, so a model looking at one window found nothing. Each of these defects is relative. A 19 pt title or a 4 px
bottom gap is only wrong beside a 24 pt title and a 14 px gap.

### How to apply

- Take a reference window's still and census at the same size and UI scale (`docs/UI-Style.md` lists the panels nobody
  asked to change), or open one beside the new window. `ui_look.py pack` refuses to build without a reference.
- Run `ui_look.py family <after>::<census>#<window> --ref <ref>::<census>#<window>` and paste its `Family:` line
  (checklist `ui.md` item 33). What it measures:
  - corner radii, fitted to the pixels of each drawn shape's corners, within 1 px on synthetic shapes of radius 0 to 14;
  - the nesting of one rounded shape inside another;
  - the header's font size and line count, from the census;
  - each edge's gap from the content (texts, controls and drawn images) to the window's box, from the census.
- What it leaves to the eye: a corner too close in colour to what is behind it to read, the header's weight and style,
  and how the room feels.
- Thresholds, measured on w1761's round-6 built player (build 610661760e, after Ben's notes; 10 Calculations stills at
  1920x1080 and 10 at 1280x800, against the Station Core and Station Grid windows from the same build):
  - Corner radii: a shape's radius is the lower median of its readable corners, read from the drawn edge. Round 6's
    window frame, rows, letter tiles, buttons and fields read 2.2 to 5 px (the code draws them all at 5 units, scale
    0.9), the Station Core window 3.3 to 6, the Station Grid window 2.75 to 5.5. Two fixes came from this run: the rows'
    sprite draws 1-3 px inside its census rect (read as 6.5-7.9 px before the snap), and two row corners over the
    nebula read 11-12 px (the median took them; the lower median does not). Icons are not shapes: the Station Grid
    window's power icons read as 8-10 px corners.
  - MIXED CORNERS: more radii than the most a reference uses (2 at least), or a radius none of them uses (within
    1.5 px or 20 %). Round 6: 1 or 2 radii in every still, all within the references'.
  - NESTED CORNERS: a circle, or a shape rounder than its parent by over 2.5 px (or 35 %), within 4 px (or the
    parent's radius) of the parent's edge. The game nests the same radius a few px in (round 6's 4 px tiles 7 px
    inside 4.5 px rows, the Station Grid window's tabs): the first rule, "about the parent's radius less the gap",
    flagged those, so only a rounder inner shape counts, which is what Ben named.
  - SMALL HEADER: under 0.9x the reference title's font. Round 6 18 pt and the Station Core window 18 pass; round 3's
    15 pt (the connector window's type, w1761 commit 9d54a3c116) is 0.83x and is flagged; the Station Grid window's
    16 pt is 0.89x and would be.
  - CRAMPED: the top and sides under 0.75x the references' lower median and 3 px or more less; the bottom the same
    against the window's own side padding. Every window measured has 11.7 px over its title and 14.4 at its sides
    at 1920x1080; their bottoms are 7.2 (Station Grid, its columns) and 19.2 (Station Core, its slot grid), so a
    reference sets no bottom. Round 6's bottom 12.6 passes; round 3's 7.2 (8 units, commit 9dc22a2517) is flagged.
  - Real-data fixture: `test_w1761s_round_6_window_matches_the_station_core_window` (unity-ui tests): round 6 gives 0
    findings, and the same window with round 3's title and bottom gives SMALL HEADER and CRAMPED BOTTOM.
