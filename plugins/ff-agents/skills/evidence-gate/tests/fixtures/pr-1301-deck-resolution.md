**TL;DR:** A screen size the game stored on its first launch is now checked at every launch, and one no display would want (portrait, too big, too narrow, zero) is replaced by the display's own size. A Steam Deck's first launch stores its landscape 1280x800 panel in a full screen window. Ben's Deck (Build 91) was stuck "on a weird ass resolution that makes no sense" after a reinstall; a player stuck like that now recovers by launching.

Request: w767

## Cause

- `DisplaySettingsController.SetInitialSettings` (first launch, no prefs) stored `Screen.currentResolution` as read on the first frame, with `ExclusiveFullScreen`, and `LoadFromPlayerPrefs` re-applied the stored size with `Screen.SetResolution` at every launch, overriding Unity's own startup size (`DisplaySettingsController.cs:43-79` before this change). Nothing ever checked the stored size again.
- The Deck runs the Windows build under Proton (Steam ships only `cicd/ff_windows_depot.vdf` and `cicd/ff_mac_depot.vdf`). Under Proton, early in startup a Unity Windows build can read the Deck's panel as portrait 800x1280, and a size asked for then can come back 800x600; a frame later it reads 1280x800 ([Unity Discussions, 2024-04-29](https://discussions.unity.com/t/steam-deck-at-1280x720/939619)); Unity issue [UUM-72969](https://issuetracker.unity.com/issues/19326/screen-values-are-incorrect-when-using-steam-deck-in-desktop-mode) has fullscreen on SteamOS under Proton at 800x800.
- Ben: the image filled only part of the screen (black bars left and right), the Early Access panel and the logo ran off both sides, taps missed; "it got worse" after a reinstall (a fresh Proton prefix is a first launch), and "somehow it goes stuck on a weird ass resolution that makes no sense. i finally was able to change it back to the default" through Settings > Display. Which size his Deck stored is not known (he could not get files off it).

## Change

- `ResolveStartupDisplay` (pure, tested): the display is read landscape (larger of `Screen.currentResolution` and `Display.main.systemWidth/Height`); a stored size is kept when it is landscape, fits the display (or is a listed display mode) and has the display's shape or one Settings offers (aspect >= 1.59); otherwise it becomes the display's size. A Deck being repaired or on its first launch gets `FullScreenWindow`; a Deck with a good stored size keeps its mode (Valve's Deck recommendations: per-device defaults yes, locking settings by hardware no).
- Every launch repairs and writes back the stored prefs before applying them; `RecheckAfterStartupAsync` checks again 10 frames later against the settled display and Steam's Deck answer (Steam starts in the same frame), and applies again when the game did not get its size. A player who changed Settings meanwhile is left alone.
- Player.log gets one `Display: stored ..., display ..., Steam Deck ...; resolved ... (repaired: ...)` line at launch and at the recheck when it repairs or re-applies, so the next Deck report settles itself.
- `Documentation/Display-Startup.md`: the path, the rules, the Deck facts, and where a Deck keeps its prefs and Player.log.

## Evidence

Kind: visual

| Claim | Basis | Where |
|---|---|---|
| A stored portrait size made Build 91 code render an 800x800 image on a 1280x800 screen, the logo and the Early Access panel running off both sides | MEASURED: Build 91 code (ea488da90) as a Linux player on a headless 1280x800 X display with a window manager, prefs seeded with ResolutionWidth 800 / ResolutionHeight 1280; Player.log `requesting fullscreen 800 x 800`; whole-screen grab | /srv/fff/review/w767-deck-resolution/before-stuck.png, /srv/fff/review/w767-deck-resolution/before-stuck.mp4 |
| The fix repairs that stored size at launch and the game fills the screen with the whole UI | MEASURED: the same seeded prefs with the fix (fab72fcb4); Player.log `repaired: 800x1280 is portrait`, `requesting fullscreen 1280 x 800`; prefs file afterwards holds 1280x800; window 1280x800+0+0; whole-screen grab | /srv/fff/review/w767-deck-resolution/after-stuck.png, /srv/fff/review/w767-deck-resolution/after-stuck.mp4 |
| A first launch from clean prefs stores and applies the display's 1280x800 | MEASURED: fix player, empty config folder; Player.log `stored 1280x800 ... applying 1280x800`; whole-screen grab | /srv/fff/review/w767-deck-resolution/after-clean.png, /srv/fff/review/w767-deck-resolution/after-clean.mp4 |
| A click on the drawn Continue button lands (the notice closes) | MEASURED: XTest click at Continue's drawn centre on the fix player, grab 5 s later shows the title menu | /srv/fff/review/w767-deck-resolution/after-stuck-click.png |
| First launch on a Deck that reads 800x1280 stores 1280x800 in a full screen window; five stuck sizes recover; good Deck and desktop sizes are kept | MEASURED: StartupDisplayResolutionTest, all cases passed in the batch run at bef3a6563 (17, 4 of them the refresh-rate cases removed since; 13 now), and CI Test in editmode passed at a4c160555 | Assets/Tests/UI/StartupDisplayResolutionTest.cs |
| A Deck under Proton can read its panel as portrait on the first frame | SOURCED: https://discussions.unity.com/t/steam-deck-at-1280x720/939619 (2024-04-29 post), Unity issue UUM-72969 | links |
| No simulation state changes | MEASURED: the diff touches DisplaySettingsController and PlayerSettingsController (FFSpaghetti MonoBehaviour settings), Screen and PlayerPrefs only | diff |

Intended look (Ben): a Deck screen the game fills "the whole width of the Steam Deck screen", not "all crunched", with the aspect ratio right (w767)
Built player: yes, Linux StandaloneLinux64 dev players of ea488da90 (before) and fab72fcb4 (after), run at 1280x800 on Xvfb + openbox
Clips: /srv/fff/review/w767-deck-resolution/before-stuck.mp4 (the stuck title notice from 20 s), after-stuck.mp4 (the whole notice from 22 s, the Continue click at 45 s, the title menu by 46 s) and after-clean.mp4 (the notice from about 22 s), 60 fps x11grab of the whole 1280x800 screen
Looked: yes, the one-per-second contact sheets of the before-stuck and after-stuck clips (before-stuck-sheet.png, after-stuck-sheet.png) and the full-size grabs at 45 and 50 s of all three runs
Review: no watch_video run; the change is a window size, not an effect

Tests: FFEditorTests selection (test_select.py, 297 classes) 2212 run, 2211 passed, 1 failed (Tests.Playtest.AuditWriteCommandTest.ActiveCapturePolicy_TwoWritesUseDistinctCheckpointPaths, a 600-frame timing test in a -nographics batch run that references no display code); CI Test in editmode at fab72fcb4 (run 37955668560): 9237 run, 9213 passed, 0 failed, 24 skipped, AuditWriteCommandTest included; after merging develop, at 5658e1175 (run 37956997343): 9220 passed, 0 failed

Not verified: the Windows build under Proton on a real Steam Deck (no Deck or Proton here; the first-frame portrait reading is sourced, not reproduced); whether Ben's Deck stored a portrait size or another one (he could not get files off it); the missed taps (an X11 stretch maps input along with the image, so they do not reproduce here; on a Deck they would come from gamescope's scaling); whether a Deck OLED lists 1280x800 in Settings > Display (its 90 Hz modes are filtered out; left unchanged here)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
