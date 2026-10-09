# A simulated Deck is not a Deck

**The rule.** A change a Steam Deck player meets is not "done" on a Deck tour alone. The report
says "verified on a real Deck" with who, the Steam client and SteamOS versions, and what they saw,
or says "not verified on a real Deck" and what that leaves open. The checklist is
[deck.md](../checklists/deck.md); `pr_evidence.py` fails a Deck-facing PR with neither.

## Why: two corrections from Ben, 2026-10-09

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

## How to apply

1. Before you write "fixed" on a Deck-facing change, list the four things a simulated Deck cannot
   show (template vs official layout, first-frame resolution under Proton/gamescope, Steam client
   and SteamOS version, touch) and say which your change touches.
2. Run the cheap stand-ins ([deck.md](../checklists/deck.md)), then ask for the real Deck through
   your orchestrator with the steps written out, starting with "the Deck's Steam client and
   SteamOS are up to date" (the w768 worker's proposal, adopted).
3. If nobody can look yet, write "not verified on a real Deck" in the report and the PR's
   `Real Deck:` line, and keep the request open when it is a player's report from their own Deck (`wNNN: still open: waiting on <name> to check on the Deck`).

## What was built and what was left (w770)

| Check | Status | Why |
|---|---|---|
| `Real Deck:` line on a Deck-facing PR | **Built**: `pr_evidence.py` `deck_problems`, fixtures of both cases | Needs only the PR text and its file list, which this repo already reads. |
| Checklist and ask template | **Built**: [deck.md](../checklists/deck.md), linked from the done, merge and UI lists | What a person must look at cannot be a script. |
| Keyboard-template simulation | **Already in the game repo** (w768, PR #1300: `-ffDeckTourFallback`, the `key` step, `specs/w768-deck-template-glyphs/template-tour.json`) | Nothing to add here; the checklist points at it. |
| Deck tour that does not force the size and starts from stored prefs | **Not built: a game-repo change; proposal below** | `DeckTour.cs` calls `Screen.SetResolution` from `Update` and `HoldSize` for any size, default 1280x800. |
| Touch, Steam client version, whether the official layout is offered | **Checklist line only** | They exist only on the device. |

**Proposal for the game repo** (not made here):
`-ffDeckTourSize none` (or `-ffDeckTourNoResize`) skips the forced `Screen.SetResolution` in `Update`
and `HoldSize`; `-ffDeckTourPrefs <json>` writes `ResolutionWidth`, `ResolutionHeight` and
`FullscreenMode` (and a `DarkModeSkybox`-less first launch) before `PlayerSettingsController.Start`;
a tour step reads `Screen.width/height` at frame 1 and again after `StartupRecheckFrames`, and fails
when the window is not landscape or does not fill the display. The first-frame portrait read is
reported only under Proton (`Documentation/Display-Startup.md`), so a PC tour would test the repair,
not reproduce the Deck's first frame.
