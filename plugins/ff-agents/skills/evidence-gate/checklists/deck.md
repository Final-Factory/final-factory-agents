# Steam Deck changes: a simulated Deck is not a Deck

For any change a Steam Deck player meets: controller glyphs and prompts, Steam Input (the action
manifest, the official layouts under `StreamingAssets/SteamInput/`, the keyboard template), the
screen size and window mode at launch, Deck-sized UI, touch input, the Deck's launch options. The
[UI checklist](ui.md) covers what the Deck tour shows; this list covers what it cannot.

**The line that would have caught w684 -> w768 and w767:** before a Deck-facing change is called
done, the report says either **"verified on a real Deck"** (who, when, which Steam client and
SteamOS, what they looked at) or **"not verified on a real Deck"** and which of the four blind
spots below it leaves open. Never a silent "done", and never "verified on the Deck" for a tour on
a PC. `pr_evidence.py` fails a Deck-facing PR without a `Real Deck:` line.

## What the Deck tour (a scripted Deck in a Windows dev player) cannot show

1. **Steam Input: the template and the official layout.** The tour hands the game a scripted Deck
   (`SteamInputBridge.SourceOverride`, `SteamHardware.Override`). A real Deck may run Steam's
   "Keyboard (WASD) and Mouse" template, which gives the game no action set and sends every button
   as a real key. w684's fix passed the tour; on Ben's Deck (Build 91) no glyph showed. The
   template case is simulated since w768 (`-ffDeckTourFallback`, a `key` step,
   `specs/w768-deck-template-glyphs/template-tour.json` in the game repo); whether the official
   layout is *offered and applied* is only seen on a Deck.
2. **The first-frame resolution under Proton/gamescope.** Early in startup a Unity Windows build
   under Proton can read the panel as portrait 800x1280, and a size asked for then comes back
   wrong; a frame later it reads 1280x800 (`Documentation/Display-Startup.md`). The tour forces
   its own windowed size every second (`DeckTour.cs`, the `Update` and `HoldSize` that call
   `Screen.SetResolution`), and starts from clean prefs, so it never sees a stored bad size or a
   bad first frame. w767: black bars each side, UI running off the screen, taps missing.
3. **The Steam client and SteamOS version.** A Deck on an old client did not list our official
   layout at all; after Ben updated, "the controller layout shows". A passing check on an old
   client proves the old client.
4. **Touch input.** The tour presses scripted buttons and clicks with a mouse. A finger on the
   panel (tap targets, scrolling, the on-screen keyboard) is a different path, and under gamescope
   a scaling mismatch makes taps miss while an X11 stretch does not
   ([linux-headless-player-screen-check](../../project-memory/memories/linux-headless-player-screen-check.md)).

## Cheap stand-ins, so the real check is only for what is left

- **Keyboard template:** run the w768 template tour (keys arriving with no action set) and look
  for Deck glyphs, not keys, in the stills. Built, in the game repo.
- **Stored bad size:** seed the player's prefs with a bad size (portrait 800x1280, a size the
  display does not list) and a Deck-like display, and start it with **no** `-ffDeckTourSize`.
  The game's `StartupDisplayResolutionTest` pins the rules; the recipe for a native Linux player
  under Xvfb with its own `XDG_CONFIG_HOME` prefs is in the memory above. The tour itself cannot
  do this yet (see the proposals in lessons/verify-ui-with-full-content-like-a-player.md#a-simulated-deck-is-not-a-deck-w770).
- Neither replaces the Deck. They shrink what you ask the person to look at.

## The real-Deck check: what to ask, through the orchestrator

A worker never asks the person directly. Put the request in the report for the orchestrator, with
`waiting_on_person` declared, and write the steps so someone with a Deck and no context can do
them:

0. **First, update.** Steam client and SteamOS up to date (Steam button > Settings > System:
   update, restart; write down both version lines). This was the w768 worker's proposal; adopted,
   because Ben's out-of-date Deck hid the layout, and every later step is meaningless on an old
   client.
1. The build: the exact branch and version (`development` beta or the Steam build number) and how
   to get it.
2. The state: a fresh install or a wiped prefix when the change is about first launch (w767 got
   worse after a reinstall), otherwise the existing one; which controller layout is applied
   (game page > gear > Controller Settings: the layout name, and whether "Final Factory" is listed
   under Official Layouts).
3. The actions, each with what to look for: "open Settings > Controls; hints show the Deck's
   buttons (A, B, X, Y), not keyboard keys", "launch from the Steam library; the game fills the
   whole screen, no bars, nothing running off an edge", "tap the Inventory button; it opens".
4. What to send back: a photo of each screen, and `Player.log` (path in
   `Documentation/Display-Startup.md`, "Where a Deck keeps it") when the change is about launch.

When the person answers, the report records their words and the versions. When nobody can check
yet, say **"not verified on a real Deck: <what stays open>"** in the report and the PR's
`Real Deck:` line; the request stays open when it is a player's report from their own Deck, per
[the done list](done.md) (item 7).

## In the pull request

```markdown
Real Deck: verified (<person>, <date>; Steam client <build number>, SteamOS <version number>): Settings > Controls shows A/B/X/Y, launch fills 1280x800 on a fresh prefix
```

or

```markdown
Real Deck: not verified on a real Deck: the official layout being offered, and touch; the keyboard-template tour and the stored-bad-size test pass
```

A `verified` line names the person, the Steam client and the SteamOS version (the check wants digits where the example
has angle brackets), and what they saw.
`pr_evidence.py` fails a Deck-facing PR (changed files under `Assets/Scripts/Steam/`,
`StreamingAssets/SteamInput/`, the display settings controllers, `cicd/*.vdf`; or an Evidence
section that mentions the Deck, Steam Input, Proton, gamescope or SteamOS) without one of the two.
